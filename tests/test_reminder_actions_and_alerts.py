"""Buttons under ordinary reminders, web feedback, analytics domains, daily admin alert."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models import Reminder, ReminderStatus, RepeatRule, User, UserFeedback
from src.services.reminder_service import ReminderService

TZ = "Europe/Moscow"


@pytest.fixture
async def shared_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    from src.bot.handlers import reminders as reminder_handlers

    monkeypatch.setattr(reminder_handlers, "async_session_maker", maker)
    yield maker
    await engine.dispose()


class _Query:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.markups = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append(text)

    async def edit_message_reply_markup(self, reply_markup=None):
        self.markups.append(reply_markup)


def _update(data, telegram_id=66001):
    return SimpleNamespace(
        callback_query=_Query(data),
        effective_user=SimpleNamespace(id=telegram_id, username=None, first_name="U", last_name=None),
    )


async def _reminder(maker, repeat=RepeatRule.NONE, telegram_id=66001):
    async with maker() as session:
        user = User(telegram_id=telegram_id, timezone=TZ)
        session.add(user)
        await session.flush()
        reminder = await ReminderService(session).create_reminder(
            user_id=user.id,
            text="Позвонить маме",
            remind_at_utc=datetime.now(timezone.utc) + timedelta(minutes=10),
            repeat_rule=repeat,
            notify_offsets_minutes=[15],
        )
        await session.commit()
        return user.id, reminder.id


@pytest.mark.asyncio
async def test_snooze_creates_a_new_reminder_later(shared_db):
    from src.bot.handlers.reminders import reminder_snooze_callback

    user_id, reminder_id = await _reminder(shared_db)
    update = _update(f"rem_snooze:{reminder_id}:60")
    await reminder_snooze_callback(update, SimpleNamespace(user_data={}))

    async with shared_db() as session:
        rows = (await session.execute(select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.id))).scalars().all()
    assert len(rows) == 2
    original, snoozed = rows
    assert original.status == ReminderStatus.DONE  # pre-reminder snoozed → replaced
    assert snoozed.status == ReminderStatus.ACTIVE and snoozed.text == "Позвонить маме"
    remind_at = snoozed.remind_at_utc if snoozed.remind_at_utc.tzinfo else snoozed.remind_at_utc.replace(tzinfo=timezone.utc)
    assert timedelta(minutes=58) < remind_at - datetime.now(timezone.utc) < timedelta(minutes=61)
    assert update.callback_query.answers[0].startswith("⏰ Напомню")


@pytest.mark.asyncio
async def test_snooze_of_a_repeating_reminder_keeps_the_series(shared_db):
    from src.bot.handlers.reminders import reminder_snooze_callback

    user_id, reminder_id = await _reminder(shared_db, RepeatRule.DAILY, telegram_id=66002)
    await reminder_snooze_callback(_update(f"rem_snooze:{reminder_id}:15", 66002), SimpleNamespace(user_data={}))
    async with shared_db() as session:
        series = await session.get(Reminder, reminder_id)
    assert series.status == ReminderStatus.ACTIVE


@pytest.mark.asyncio
async def test_done_button_closes_and_shows_time(shared_db):
    from src.bot.handlers.reminders import reminder_ack_callback

    _, reminder_id = await _reminder(shared_db, telegram_id=66003)
    update = _update(f"rem_ack:{reminder_id}", 66003)
    await reminder_ack_callback(update, SimpleNamespace(user_data={}))
    async with shared_db() as session:
        assert (await session.get(Reminder, reminder_id)).status == ReminderStatus.DONE
    button = update.callback_query.markups[0].inline_keyboard[0][0]
    assert button.text.startswith("✅ Сделано в ") and button.callback_data == "noop"


def test_reminder_action_buttons_are_registered():
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in ("rem_ack:5", "rem_snooze:5:15", "rem_snooze:5:60", "rem_snooze:5:1440"):
        assert _is_registered(callback, patterns), callback


def test_new_events_are_not_unknown_in_analytics():
    from src.services.activity_service import infer_domain

    assert infer_domain("bc_toggle:{id}:{id}") == "admin"
    assert infer_domain("fb_kind:{id}") == "feedback"
    assert infer_domain("feedback_start") == "feedback"
    assert infer_domain("rem_snooze:{id}:{id}") == "reminders"
    assert infer_domain("free_note") == "notes"


@pytest.mark.asyncio
async def test_web_feedback_is_stored_and_sent_to_admins(db_session, monkeypatch):
    from src.api.app import create_application
    from src.api.routes import me as me_routes
    from src.api.user_auth import get_current_web_user
    from src.db.session import get_db

    user = User(telegram_id=66101, timezone=TZ, first_name="Аня")
    db_session.add(user)
    await db_session.flush()
    sent = []

    async def fake_notify(item, recent_errors):
        sent.append(item.text)

    monkeypatch.setattr(me_routes, "_notify_admins_about_web_feedback", fake_notify)
    app = create_application()

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_web_user] = override_user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.post("/me/feedback", json={"kind": "idea", "text": "Тёмная тема"})
        bad = await client.post("/me/feedback", json={"kind": "spam", "text": "x"})

    assert ok.status_code == 201 and bad.status_code == 422
    rows = (await db_session.execute(select(UserFeedback))).scalars().all()
    assert [(r.kind, r.text) for r in rows] == [("idea", "Тёмная тема")]
    assert sent == ["Тёмная тема"]


def test_daily_health_run_alerts_admins_only():
    from pathlib import Path

    health = Path("scripts/server-health.sh").read_text(encoding="utf-8")
    assert 'NOTIFY_ADMINS' in health and "notify-admins.py" in health
    workflow = Path(".github/workflows/server-health.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'schedule'" in workflow
    sender = Path("scripts/notify-admins.py").read_text(encoding="utf-8")
    assert "MAX_RECIPIENTS = 3" in sender
