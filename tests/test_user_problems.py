"""Problems found in real usage (anonymous diagnostics, 14.10.2026)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from telegram.error import BadRequest

from src.bot.handlers.conversation_exit import stale_button_callback
from src.bot.handlers.free_text import TOKEN_LIKE, free_text_keyboard
from src.bot.keyboards import get_reminder_notify_offsets_keyboard
from src.db.models import Reminder, ReminderStatus, RepeatRule, User
from src.repositories.reminder_repo import ReminderRepository
from src.services.medication_service import MedicationService
from src.utils.date_parser import extract_reminder_datetime
from src.worker.reminder_worker import ReminderWorkerService, WorkerCycleResult
from tests.test_worker_cycle import FakeReminderRepository, FakeSession

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)


# --- Phrases with date/time (people abandoned the separate date/time steps) ---------------

def test_phrase_with_tomorrow_and_hour():
    kind, when, rest = extract_reminder_datetime("завтра в 10 позвонить маме", TZ)
    assert kind == "datetime"
    assert when.date() == datetime.now(MSK).date() + timedelta(days=1)
    assert (when.hour, when.minute) == (10, 0)
    assert rest == "позвонить маме"


@pytest.mark.parametrize(
    "phrase, hour, minute, rest",
    [
        ("тренировка в 7.30", 7, 30, "тренировка"),
        ("в 3 дня встреча", 15, 0, "встреча"),
        ("28 октября в 7 вечера театр", 19, 0, "театр"),
        ("в пн в 8:15 планёрка", 8, 15, "планёрка"),
        ("позвонить маме в 18:30", 18, 30, "позвонить маме"),
    ],
)
def test_phrases_with_time(phrase, hour, minute, rest):
    kind, when, text = extract_reminder_datetime(phrase, TZ)
    assert kind == "datetime"
    assert (when.hour, when.minute) == (hour, minute)
    assert text == rest
    assert when > datetime.now(MSK)


def test_numeric_date_with_time():
    kind, when, rest = extract_reminder_datetime("15.10 в 18 стоматолог", TZ)
    assert kind == "datetime" and (when.day, when.month, when.hour) == (15, 10, 18)
    assert rest == "стоматолог"


def test_relative_phrase():
    kind, when, rest = extract_reminder_datetime("через полчаса чай", TZ)
    assert kind == "datetime"
    assert timedelta(minutes=29) < when - datetime.now(MSK) < timedelta(minutes=31)
    assert rest == "чай"


def test_day_without_time_asks_for_time():
    kind, day, rest = extract_reminder_datetime("во вторник отчёт", TZ)
    assert kind == "date" and day.weekday() == 1 and rest == "отчёт"


@pytest.mark.parametrize("phrase", ["купить хлеб", "оплатить 10 счетов", "взять 5 кг картошки"])
def test_phrases_without_date_are_left_alone(phrase):
    assert extract_reminder_datetime(phrase, TZ) is None


# --- Saved-at-time-selection wizard ------------------------------------------------------------

def test_saved_reminder_card_has_done_and_delete_buttons():
    markup = get_reminder_notify_offsets_keyboard("none", saved=True)
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert callbacks[0] == "rem_finish"
    assert "rem_cancel_create" in callbacks


@pytest.mark.asyncio
async def test_stale_buttons_of_saved_reminder_say_it_is_saved():
    class Query:
        data = "rem_finish"
        answers = []

        async def answer(self, text=None, show_alert=False):
            self.answers.append(text)

        async def edit_message_reply_markup(self, reply_markup=None):
            pass

    query = Query()
    await stale_button_callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))
    assert "уже сохранено" in query.answers[0]


def test_free_text_offers_reminder_and_note():
    callbacks = [b.callback_data for row in free_text_keyboard().inline_keyboard for b in row]
    assert callbacks == ["free_reminder", "free_note", "home"]
    assert TOKEN_LIKE.match("x" * 40)
    assert not TOKEN_LIKE.match("купить молоко")


def test_free_text_buttons_are_registered():
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in ("free_reminder", "free_note", "rem_finish"):
        assert _is_registered(callback, patterns), callback


# --- Delivery failures --------------------------------------------------------------------------

class FlakyFormatBot:
    """Rejects the HTML message once, accepts the plain-text retry."""

    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.calls.append((text, parse_mode))
        if parse_mode == "HTML":
            raise BadRequest("Can't parse entities: unsupported start tag")


def _reminder(rule=RepeatRule.NONE):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    return now, SimpleNamespace(
        id=60, user_id=7, title="Тест", text="Проверка <важно>", remind_at_utc=now,
        repeat_rule=rule, list_id=None, medication_id=None, medication=None, todo_list=None,
        user=SimpleNamespace(telegram_id=1, timezone=TZ),
    )


@pytest.mark.asyncio
async def test_formatting_error_is_retried_as_plain_text():
    now, reminder = _reminder()
    session = FakeSession()
    repo = FakeReminderRepository(session, [reminder])
    bot = FlakyFormatBot()
    worker = ReminderWorkerService(bot=bot, session_factory=lambda: session,
                                   repository_factory=lambda s: repo, clock=lambda: now)

    result = await worker.process_cycle()

    assert result == WorkerCycleResult(total=1, processed=1, failed=0)
    assert repo.sent_notifications
    assert bot.calls[-1][1] is None and "<b>" not in bot.calls[-1][0]


@pytest.mark.asyncio
async def test_revive_series_stopped_by_failed_delivery(db_session):
    """Found on the server: a medication schedule died after one failed delivery."""
    user = User(telegram_id=84001, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Магний")
    archived = await meds.create_medication(user_id=user.id, name="Старое")
    await meds.archive_medication(archived.id, user.id)
    old = datetime(2026, 9, 3, 5, 0, tzinfo=timezone.utc)
    for med_id in (medication.id, archived.id):
        db_session.add(Reminder(
            user_id=user.id, text="Принять лекарство", remind_at_utc=old, repeat_rule=RepeatRule.DAILY,
            status=ReminderStatus.MISSED, medication_id=med_id, source_module="medication",
        ))
    db_session.add(Reminder(
        user_id=user.id, text="Закончено пользователем", remind_at_utc=old, repeat_rule=RepeatRule.DAILY,
        status=ReminderStatus.DONE, source_module="general",
    ))
    await db_session.flush()
    now = datetime.now(timezone.utc)

    revived = await ReminderRepository(db_session).revive_dead_series(now, TZ)

    assert revived == 1
    active = await meds._get_active_daily_reminders(medication.id, user.id)
    assert len(active) == 1
    next_at = active[0].remind_at_utc.replace(tzinfo=timezone.utc) if active[0].remind_at_utc.tzinfo is None else active[0].remind_at_utc
    assert next_at > now
    assert next_at.astimezone(MSK).hour == 8  # same local time as before (05:00 UTC = 08:00 MSK)
    assert await meds._get_active_daily_reminders(archived.id, user.id) == []

    assert await ReminderRepository(db_session).revive_dead_series(now, TZ) == 0
