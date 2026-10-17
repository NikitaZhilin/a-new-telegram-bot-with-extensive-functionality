"""Plan for the day, feedback reply from the web admin, small fixes."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from src.db.models import Reminder, ReminderStatus, User
from src.services.medication_service import MedicationService
from src.services.reminder_service import ReminderService

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)


@pytest.mark.asyncio
async def test_daily_plan_lists_today_reminders_and_medications(db_session):
    from src.services.digest_service import build_daily_plan

    user = User(telegram_id=67001, timezone=TZ, daily_digest=True)
    db_session.add(user)
    await db_session.flush()
    now = datetime.combine(date(2026, 10, 20), time(8, 0), tzinfo=MSK).astimezone(timezone.utc)
    reminders = ReminderService(db_session)
    await reminders.create_reminder(
        user_id=user.id, text="Позвонить маме",
        remind_at_utc=datetime.combine(date(2026, 10, 20), time(18, 30), tzinfo=MSK).astimezone(timezone.utc),
    )
    await reminders.create_reminder(  # tomorrow: not in today's plan
        user_id=user.id, text="Завтрашнее",
        remind_at_utc=datetime.combine(date(2026, 10, 21), time(9, 0), tzinfo=MSK).astimezone(timezone.utc),
    )
    meds = MedicationService(db_session)
    magnesium = await meds.create_medication(user_id=user.id, name="Магний")
    await meds.replace_daily_reminders(
        magnesium.id, user.id,
        [datetime.combine(date(2026, 10, 21), time(9, 0), tzinfo=MSK).astimezone(timezone.utc)],
    )
    paused = await meds.create_medication(user_id=user.id, name="Хофитол")
    await meds.replace_daily_reminders(
        paused.id, user.id,
        [datetime.combine(date(2026, 10, 21), time(10, 0), tzinfo=MSK).astimezone(timezone.utc)],
    )
    await meds.pause_course(paused.id, user.id, date(2027, 1, 20), TZ, now_utc=now)

    text = await build_daily_plan(db_session, user, TZ, now)
    assert text.startswith("🌅 План на сегодня, 20.10")
    assert "• 18:30 Позвонить маме" in text and "Завтрашнее" not in text
    assert "💊 Магний — 09:00" in text and "Хофитол" not in text


@pytest.mark.asyncio
async def test_empty_day_sends_nothing(db_session):
    from src.services.digest_service import build_daily_plan

    user = User(telegram_id=67002, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    assert await build_daily_plan(db_session, user, TZ) is None


def test_digest_buttons_are_registered():
    from src.bot.keyboards import get_settings_keyboard
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in ("settings_digest", "digest_on", "digest_off", "digest_preview"):
        assert _is_registered(callback, patterns), callback
    assert "settings_digest" in [b.callback_data for row in get_settings_keyboard().inline_keyboard for b in row]


# --- Small fixes ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_double_press_does_not_start_two_checklists(db_session):
    from src.services.checklist_service import ChecklistService
    from src.services.list_service import ListService

    user = User(telegram_id=67101, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    lists = ListService(db_session)
    todo = await lists.create_list(user.id, "Поездка")
    await lists.add_item(todo.id, user.id, "Паспорт")
    service = ChecklistService(db_session)
    first = await service.create_run_from_list(todo.id, user.id)
    second = await service.create_run_from_list(todo.id, user.id)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_expired_document_gets_no_misleading_reminder(db_session):
    from src.services.driver_service import DriverService

    user = User(telegram_id=67102, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    driver = DriverService(db_session)
    await driver.create_document(
        user.id, "Старая страховка", document_type="insurance",
        expires_at_utc=datetime.now(timezone.utc) - timedelta(days=3), remind_before_days=30,
    )
    late = await driver.create_document(
        user.id, "ОСАГО", document_type="insurance",
        expires_at_utc=datetime.now(timezone.utc) + timedelta(days=5, hours=1), remind_before_days=30,
    )
    active = (await db_session.execute(
        select(Reminder).where(Reminder.user_id == user.id, Reminder.status == ReminderStatus.ACTIVE)
    )).scalars().all()
    assert [r.driver_document_id for r in active] == [late.id]  # nothing for the expired one
    assert "осталось 5 дн." in active[0].text  # real days left, not «30»


@pytest.mark.asyncio
async def test_readiness_is_503_without_database(monkeypatch):
    from src.api.app import create_application
    from src.api.routes import health

    class BrokenEngine:
        def connect(self):
            raise OSError("db down")

    monkeypatch.setattr(health, "engine", BrokenEngine())
    app = create_application()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503 and response.json()["database"] == "unreachable"


@pytest.mark.asyncio
async def test_admin_can_reply_to_feedback_from_the_web(db_session, monkeypatch):
    from src.api.app import create_application
    from src.api.routes import admin as admin_routes
    from src.config import settings
    from src.db.session import get_db
    from src.services.feedback_service import FeedbackService

    item = await FeedbackService(db_session).create(telegram_id=67201, kind="idea", text="Тёмная тема")
    await db_session.flush()
    delivered = []

    async def fake_send(telegram_id, feedback_id, text):
        delivered.append((telegram_id, feedback_id, text))

    monkeypatch.setattr(admin_routes, "_send_feedback_reply", fake_send)
    app = create_application()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.post(
            f"/admin/feedback/{item.id}/reply", json={"text": "Сделаем!"}, headers={"X-Admin-Token": settings.ADMIN_TOKEN}
        )
    assert ok.status_code == 200
    assert delivered == [(67201, item.id, "Сделаем!")]
    assert (await FeedbackService(db_session).get(item.id)).status == "answered"
