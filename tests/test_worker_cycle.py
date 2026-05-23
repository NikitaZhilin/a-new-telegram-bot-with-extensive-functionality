"""Tests for one safe reminder worker cycle."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest, NetworkError

from src.db.models import Reminder, ReminderStatus, RepeatRule, User
from src.repositories.reminder_repo import ReminderRepository
from src.worker.reminder_worker import ReminderWorkerService, WorkerCycleResult


class FakeBot:
    def __init__(self, fail_with=None):
        self.messages = []
        self.fail_with = fail_with

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        if self.fail_with:
            raise self.fail_with
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
            }
        )


class FakeSession:
    def __init__(self):
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self):
        self.committed = True


class FakeReminderRepository:
    def __init__(self, session, reminders):
        self.session = session
        self.reminders = reminders
        self.marked = []
        self.statuses = []
        self.next_occurrences = []

    async def get_due_reminders_locked(self, now, limit=100):
        return self.reminders[:limit]

    async def mark_as_notified(self, reminder_id, notified_at):
        self.marked.append((reminder_id, notified_at))
        return None

    async def mark_status(self, reminder_id, status):
        self.statuses.append((reminder_id, status))
        return None

    async def create_next_occurrence(self, reminder, next_time):
        self.next_occurrences.append((reminder.id, next_time))
        return None


@pytest.mark.asyncio
async def test_worker_process_cycle_sends_and_marks_without_telegram_api():
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot()
    reminder = SimpleNamespace(
        id=42,
        user_id=7,
        title="Test reminder",
        text="Check worker tick",
        remind_at_utc=now,
        repeat_rule=RepeatRule.NONE,
        list_id=None,
        medication_id=None,
        medication=None,
        todo_list=None,
        user=SimpleNamespace(telegram_id=123456),
    )
    repo = FakeReminderRepository(session, [reminder])

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert session.committed is True
    assert repo.marked == [(42, now)]
    assert len(bot.messages) == 1
    assert bot.messages[0]["chat_id"] == 123456
    assert bot.messages[0]["parse_mode"] == "HTML"
    assert "<b>Test reminder</b>" in bot.messages[0]["text"]
    assert "Check worker tick" in bot.messages[0]["text"]
    assert "22.05.2026 15:00 (Europe/Moscow)" in bot.messages[0]["text"]
    assert bot.messages[0]["reply_markup"] is None


@pytest.mark.asyncio
async def test_worker_sends_open_list_button_for_linked_reminder():
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot()
    reminder = SimpleNamespace(
        id=43,
        user_id=7,
        title=None,
        text="Напомнить про список: Groceries",
        remind_at_utc=now,
        repeat_rule=RepeatRule.NONE,
        list_id=99,
        medication_id=None,
        medication=None,
        todo_list=SimpleNamespace(id=99, title="Groceries"),
        user=SimpleNamespace(telegram_id=123456),
    )
    repo = FakeReminderRepository(session, [reminder])

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert "📋 Список: Groceries" in bot.messages[0]["text"]
    button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
    assert button.text == "📋 Открыть список"
    assert button.callback_data == "list_view:99"


@pytest.mark.asyncio
async def test_worker_sends_medication_actions_for_linked_reminder():
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot()
    reminder = SimpleNamespace(
        id=44,
        user_id=7,
        title="💊 Приём лекарства",
        text="Принять лекарство: Vitamin D",
        remind_at_utc=now,
        repeat_rule=RepeatRule.NONE,
        list_id=None,
        todo_list=None,
        medication_id=77,
        medication=SimpleNamespace(id=77, name="Vitamin D"),
        user=SimpleNamespace(telegram_id=123456, timezone="Europe/Moscow"),
    )
    repo = FakeReminderRepository(session, [reminder])

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert "💊 Лекарство: Vitamin D" in bot.messages[0]["text"]
    buttons = bot.messages[0]["reply_markup"].inline_keyboard
    assert buttons[0][0].callback_data == "med_taken:77"
    assert buttons[0][1].callback_data == "med_snooze:77"
    assert buttons[1][0].callback_data == "med_skip:77"
    assert buttons[2][0].callback_data == "med_view:77"


@pytest.mark.asyncio
async def test_worker_skips_daily_medication_reminder_when_slot_already_marked():
    now = datetime(2026, 5, 22, 6, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot()
    reminder = SimpleNamespace(
        id=45,
        user_id=7,
        title="💊 Приём лекарства",
        text="Принять лекарство: L-thyroxine",
        remind_at_utc=now,
        repeat_rule=RepeatRule.DAILY,
        list_id=None,
        todo_list=None,
        medication_id=78,
        medication=SimpleNamespace(id=78, name="L-thyroxine"),
        user=SimpleNamespace(telegram_id=123456, timezone="Europe/Moscow"),
    )
    repo = FakeReminderRepository(session, [reminder])

    async def already_marked_checker(db_session, checked_reminder, checked_now):
        assert db_session is session
        assert checked_reminder is reminder
        assert checked_now == now
        return True

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
        medication_action_checker=already_marked_checker,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert bot.messages == []
    assert repo.marked == [(45, now)]
    assert repo.next_occurrences


@pytest.mark.asyncio
async def test_worker_retries_transient_telegram_errors_without_marking_notified():
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot(fail_with=NetworkError("temporary network failure"))
    reminder = SimpleNamespace(
        id=46,
        user_id=7,
        title="Retry me",
        text="Temporary failure",
        remind_at_utc=now,
        repeat_rule=RepeatRule.NONE,
        list_id=None,
        medication_id=None,
        medication=None,
        todo_list=None,
        user=SimpleNamespace(telegram_id=123456),
    )
    repo = FakeReminderRepository(session, [reminder])

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=0, failed=1)
    assert repo.marked == []
    assert repo.statuses == []


@pytest.mark.asyncio
async def test_worker_closes_permanent_telegram_errors_without_retry_loop():
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    session = FakeSession()
    bot = FakeBot(fail_with=BadRequest("chat not found"))
    reminder = SimpleNamespace(
        id=47,
        user_id=7,
        title="Close me",
        text="Permanent failure",
        remind_at_utc=now,
        repeat_rule=RepeatRule.DAILY,
        list_id=None,
        medication_id=None,
        medication=None,
        todo_list=None,
        user=SimpleNamespace(telegram_id=123456),
    )
    repo = FakeReminderRepository(session, [reminder])

    worker = ReminderWorkerService(
        bot=bot,
        batch_size=10,
        poll_interval=1,
        session_factory=lambda: session,
        repository_factory=lambda db_session: repo,
        clock=lambda: now,
    )

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert repo.marked == []
    assert repo.statuses == [(47, ReminderStatus.MISSED)]
    assert repo.next_occurrences == []


@pytest.mark.asyncio
async def test_mark_as_notified_closes_current_occurrence(db_session):
    """A notified occurrence should leave the active reminder list."""
    now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
    user = User(telegram_id=7001, timezone="Europe/Moscow")
    db_session.add(user)
    await db_session.flush()
    reminder = Reminder(
        user_id=user.id,
        text="Daily check",
        remind_at_utc=now,
        repeat_rule=RepeatRule.DAILY,
        status=ReminderStatus.ACTIVE,
    )
    db_session.add(reminder)
    await db_session.flush()

    repo = ReminderRepository(db_session)
    updated = await repo.mark_as_notified(reminder.id, now)

    assert updated is not None
    assert updated.notified_at.replace(tzinfo=timezone.utc) == now
    assert updated.status == ReminderStatus.DONE
