"""Worker must not loop forever, hammer Telegram, or resend a whole batch."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from telegram.error import NetworkError, RetryAfter

from src.db.models import RepeatRule
from src.worker.reminder_worker import ReminderWorkerService, WorkerCycleResult
from tests.test_worker_cycle import FakeBot, FakeReminderRepository, FakeSession


def _reminder(reminder_id, remind_at):
    return SimpleNamespace(
        id=reminder_id,
        user_id=7,
        title="Test",
        text="Text",
        remind_at_utc=remind_at,
        repeat_rule=RepeatRule.NONE,
        list_id=None,
        medication_id=None,
        medication=None,
        todo_list=None,
        user=SimpleNamespace(telegram_id=1000 + reminder_id, timezone="Europe/Moscow"),
    )


def _worker(bot, session, repo, now):
    return ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )


@pytest.mark.asyncio
async def test_temporary_failure_is_given_up_after_a_day():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    repo = FakeReminderRepository(session, [_reminder(1, now - timedelta(hours=25))])
    worker = _worker(FakeBot(fail_with=NetworkError("down")), session, repo, now)

    result = await worker.process_cycle()

    assert result.failed == 1
    assert repo.notification_errors == []
    assert repo.failed_notifications and "Gave up" in repo.failed_notifications[0][1]


@pytest.mark.asyncio
async def test_recent_temporary_failure_stays_pending():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    repo = FakeReminderRepository(session, [_reminder(1, now - timedelta(minutes=5))])
    worker = _worker(FakeBot(fail_with=NetworkError("down")), session, repo, now)

    await worker.process_cycle()

    assert repo.notification_errors
    assert repo.failed_notifications == []


class FloodBot(FakeBot):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.calls += 1
        if self.calls == 2:
            raise RetryAfter(30)
        await super().send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)


@pytest.mark.asyncio
async def test_flood_control_stops_batch_and_pauses_worker():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    repo = FakeReminderRepository(session, [_reminder(i, now) for i in range(1, 6)])
    bot = FloodBot()
    worker = _worker(bot, session, repo, now)

    result = await worker.process_cycle()

    assert bot.calls == 2, "after 429 the rest of the batch waits"
    assert result == WorkerCycleResult(total=5, processed=1, failed=1)
    assert worker._retry_after_seconds == 30


class SavepointSession(FakeSession):
    """Fake session that records SAVEPOINT rollbacks like SQLAlchemy does."""

    def __init__(self):
        super().__init__()
        self.rolled_back = 0

    def begin_nested(self):
        session = self

        @asynccontextmanager
        async def savepoint():
            try:
                yield
            except Exception:
                session.rolled_back += 1
                raise

        return savepoint()


class BrokenDbRepo(FakeReminderRepository):
    async def mark_notification_sent(self, notification_id, sent_at):
        if notification_id == 2:
            raise RuntimeError("database error")
        return await super().mark_notification_sent(notification_id, sent_at)


@pytest.mark.asyncio
async def test_database_error_on_one_notification_keeps_the_rest_of_batch():
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    session = SavepointSession()
    repo = BrokenDbRepo(session, [_reminder(i, now) for i in range(1, 4)])
    worker = _worker(FakeBot(), session, repo, now)

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=3, processed=2, failed=1)
    assert [item[0] for item in repo.sent_notifications] == [1, 3]
    assert session.rolled_back == 1
    assert session.committed is True
