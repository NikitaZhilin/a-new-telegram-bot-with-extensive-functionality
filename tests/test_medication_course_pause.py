"""Break between medication courses (e.g. Хофитол once every 3-6 months)."""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from src.db.models import Reminder, ReminderNotificationStatus, ReminderStatus, RepeatRule, User
from src.services.medication_service import MedicationService

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def _setup(db_session, telegram_id=86001):
    user = User(telegram_id=telegram_id, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Хофитол")
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    await meds.replace_daily_reminders(
        medication.id,
        user.id,
        [datetime.combine(tomorrow, time(10, 0), tzinfo=MSK).astimezone(timezone.utc)],
    )
    return user, meds, medication


async def _active(db_session, user_id):
    return (await db_session.execute(
        select(Reminder).where(Reminder.user_id == user_id, Reminder.status == ReminderStatus.ACTIVE)
    )).scalars().all()


@pytest.mark.asyncio
async def test_pause_stops_reminders_and_plans_a_heads_up_a_week_before(db_session):
    user, meds, medication = await _setup(db_session)
    until = datetime.now(MSK).date() + timedelta(days=90)

    await meds.pause_course(medication.id, user.id, until, TZ)

    assert medication.paused_until == until
    assert medication.paused_schedule == ["10:00"]
    assert await meds._get_active_daily_reminders(medication.id, user.id) == []
    active = await _active(db_session, user.id)
    assert len(active) == 1  # only the heads-up
    notice = active[0]
    assert notice.medication_id is None and notice.repeat_rule == RepeatRule.NONE
    local = _utc(notice.remind_at_utc).astimezone(MSK)
    assert (local.date(), local.hour, local.minute) == (until - timedelta(days=7), 10, 0)
    assert "Хофитол" in notice.text and until.strftime("%d.%m.%Y") in notice.text

    state = await meds.get_intake_action_state(medication.id, user.id, TZ)
    assert not state.can_mark and state.reason == "paused"
    assert await meds.get_today_slots(medication.id, user.id, TZ) == []


@pytest.mark.asyncio
async def test_short_pause_has_no_heads_up_and_past_date_is_refused(db_session):
    user, meds, medication = await _setup(db_session, 86002)
    today = datetime.now(MSK).date()
    with pytest.raises(ValueError):
        await meds.pause_course(medication.id, user.id, today, TZ)
    await meds.pause_course(medication.id, user.id, today + timedelta(days=3), TZ)
    assert await _active(db_session, user.id) == []


@pytest.mark.asyncio
async def test_changing_pause_date_replaces_the_heads_up(db_session):
    user, meds, medication = await _setup(db_session, 86003)
    today = datetime.now(MSK).date()
    await meds.pause_course(medication.id, user.id, today + timedelta(days=60), TZ)
    first_notice = medication.pause_notice_reminder_id
    await meds.pause_course(medication.id, user.id, today + timedelta(days=120), TZ)

    assert medication.paused_schedule == ["10:00"]  # kept from before the first pause
    old = await db_session.get(Reminder, first_notice)
    assert old.status == ReminderStatus.CANCELED
    assert all(n.status != ReminderNotificationStatus.PENDING for n in old.notifications)
    active = await _active(db_session, user.id)
    assert [r.id for r in active] == [medication.pause_notice_reminder_id]


@pytest.mark.asyncio
async def test_schedule_cannot_be_recreated_during_a_break(db_session):
    user, meds, medication = await _setup(db_session, 86004)
    await meds.pause_course(medication.id, user.id, datetime.now(MSK).date() + timedelta(days=30), TZ)
    soon = datetime.now(timezone.utc) + timedelta(hours=2)
    assert await meds.create_reminder(medication.id, user.id, soon) is None
    assert await meds.replace_daily_reminders(medication.id, user.id, [soon]) == []


@pytest.mark.asyncio
async def test_resume_now_brings_back_the_same_time_and_drops_the_heads_up(db_session):
    user, meds, medication = await _setup(db_session, 86005)
    await meds.pause_course(medication.id, user.id, datetime.now(MSK).date() + timedelta(days=90), TZ)
    notice_id = medication.pause_notice_reminder_id

    await meds.resume_course(medication.id, user.id, TZ)

    assert medication.paused_until is None and medication.paused_schedule is None
    assert (await db_session.get(Reminder, notice_id)).status == ReminderStatus.CANCELED
    assert await meds._get_daily_schedule_times(medication.id, user.id, TZ) == [time(10, 0)]
    daily = await meds._get_active_daily_reminders(medication.id, user.id)
    assert len(daily) == 1 and _utc(daily[0].remind_at_utc) > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_course_resumes_by_itself_on_its_day(db_session):
    user, meds, medication = await _setup(db_session, 86006)
    today = datetime.now(MSK).date()
    until = today + timedelta(days=10)
    await meds.pause_course(medication.id, user.id, until, TZ)

    day_before = datetime.combine(until - timedelta(days=1), time(23, 0), tzinfo=MSK).astimezone(timezone.utc)
    assert await meds.resume_due_courses(day_before, TZ) == []

    morning = datetime.combine(until, time(0, 5), tzinfo=MSK).astimezone(timezone.utc)
    resumed = await meds.resume_due_courses(morning, TZ)

    assert [m.id for m, _ in resumed] == [medication.id]
    daily = await meds._get_active_daily_reminders(medication.id, user.id)
    first = _utc(daily[0].remind_at_utc).astimezone(MSK)
    assert (first.date(), first.hour) == (until, 10)  # today's 10:00 dose is not lost


@pytest.mark.asyncio
async def test_archiving_a_paused_medication_cancels_the_heads_up(db_session):
    user, meds, medication = await _setup(db_session, 86007)
    await meds.pause_course(medication.id, user.id, datetime.now(MSK).date() + timedelta(days=90), TZ)
    await meds.archive_medication(medication.id, user.id)
    assert await _active(db_session, user.id) == []


def test_pause_helpers_in_the_bot():
    from src.bot.handlers.medications import _add_months, _parse_pause_date

    assert _add_months(date(2026, 10, 31), 4) == date(2027, 2, 28)
    assert _add_months(date(2026, 10, 16), 3) == date(2027, 1, 16)
    today = date(2026, 10, 16)
    assert _parse_pause_date("15.01.2027", today) == date(2027, 1, 15)
    assert _parse_pause_date("15.01.27", today) == date(2027, 1, 15)
    assert _parse_pause_date("15.01", today) == date(2027, 1, 15)
    assert _parse_pause_date("20.10", today) == date(2026, 10, 20)
    assert _parse_pause_date("31.02.2027", today) is None
    assert _parse_pause_date("через месяц", today) is None


def test_card_buttons_switch_during_a_break():
    from src.bot.keyboards import get_medication_view_keyboard

    def callbacks(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    normal = callbacks(get_medication_view_keyboard(5))
    assert "med_pause:5" in normal and "med_resume:5" not in normal
    paused = callbacks(get_medication_view_keyboard(5, can_mark=False, paused=True))
    assert "med_resume:5" in paused and "med_pause:5" in paused
    assert not any(c.startswith(("med_taken", "med_skip", "med_snooze", "med_remind")) for c in paused)


def test_pause_buttons_are_registered():
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in ("med_pause:5", "med_pause_set:5:3", "med_pause_custom:5", "med_resume:5"):
        assert _is_registered(callback, patterns), callback


def test_paused_card_text():
    from src.bot.handlers.medications import _format_pause_state

    until = datetime.now(MSK).date() + timedelta(days=90)
    medication = SimpleNamespace(paused_until=until, paused_schedule=["10:00"])
    text = "\n".join(_format_pause_state(medication, TZ))
    assert "Перерыв между курсами до" in text and until.strftime("%d.%m.%Y") in text
    assert "Напомню за неделю" in text and "10:00" in text
