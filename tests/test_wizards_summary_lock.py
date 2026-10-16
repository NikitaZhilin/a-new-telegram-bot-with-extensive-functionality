"""Early-saving wizards, weekly medication summary, single bot instance, web pause."""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models import Medication, MedicationIntakeStatus, Note, User
from src.services.medication_service import MedicationService

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)


@pytest.fixture
async def shared_db(monkeypatch):
    """One in-memory DB used both by the test and by handlers' async_session_maker."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    from src.bot.handlers import medications as med_handlers
    from src.bot.handlers import notes as note_handlers

    monkeypatch.setattr(note_handlers, "async_session_maker", maker)
    monkeypatch.setattr(med_handlers, "async_session_maker", maker)
    yield maker
    await engine.dispose()


class _Message:
    def __init__(self, text):
        self.text = text
        self.chat_id = 1
        self.message_id = 10
        self.replies = []

    async def delete(self):
        pass

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.replies.append((text, reply_markup))
        return SimpleNamespace(chat_id=1, message_id=11)


class _Bot:
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, chat_id=None, message_id=None, text=None, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup))

    async def send_message(self, chat_id=None, text=None, reply_markup=None, **kwargs):
        self.edits.append((text, reply_markup))
        return SimpleNamespace(chat_id=chat_id, message_id=12)


def _update(text):
    return SimpleNamespace(
        message=_Message(text),
        callback_query=None,
        effective_user=SimpleNamespace(id=55501, username="u", first_name="U", last_name=None),
        effective_chat=SimpleNamespace(id=1),
    )


def _context():
    return SimpleNamespace(user_data={}, bot=_Bot())


@pytest.mark.asyncio
async def test_note_is_saved_right_after_the_title(shared_db):
    from src.bot.handlers.notes import note_save_text, note_save_title
    from src.bot.states import NoteStates

    context = _context()
    state = await note_save_title(_update("Рецепт борща"), context)
    assert state == NoteStates.WAIT_TEXT
    async with shared_db() as session:
        notes = (await session.execute(select(Note))).scalars().all()
    assert [n.title for n in notes] == ["Рецепт борща"]  # saved even if the user leaves now

    await note_save_text(_update("Свекла, капуста"), context)
    async with shared_db() as session:
        note = (await session.execute(select(Note))).scalar_one()
    assert note.text == "Свекла, капуста"


@pytest.mark.asyncio
async def test_medication_is_saved_right_after_the_name(shared_db):
    from src.bot.handlers.medications import medication_save_dosage, medication_save_name
    from src.bot.states import MedicationStates

    context = _context()
    state = await medication_save_name(_update("Магний"), context)
    assert state == MedicationStates.WAIT_DOSAGE
    async with shared_db() as session:
        meds = (await session.execute(select(Medication))).scalars().all()
    assert [(m.name, m.importance, m.is_active) for m in meds] == [("Магний", "normal", True)]

    await medication_save_dosage(_update("2 таблетки"), context)
    async with shared_db() as session:
        med = (await session.execute(select(Medication))).scalar_one()
    assert med.dosage == "2 таблетки"
    assert context.user_data["med_saved_id"] == med.id


@pytest.mark.asyncio
async def test_cancel_drops_a_half_made_medication(shared_db):
    from src.bot.handlers.medications import cancel_handler, medication_save_name

    context = _context()
    update = _update("Ненужное")
    await medication_save_name(update, context)
    await cancel_handler(update, context)
    async with shared_db() as session:
        med = (await session.execute(select(Medication))).scalar_one()
    assert med.is_active is False


# --- Weekly summary -------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_summary_counts_taken_skipped_and_unmarked(db_session):
    user = User(telegram_id=55601, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    now = datetime.combine(date(2026, 10, 18), time(19, 0), tzinfo=MSK).astimezone(timezone.utc)  # Sunday
    medication = await meds.create_medication(user_id=user.id, name="Магний")
    medication.created_at = now - timedelta(days=30)
    await meds.replace_daily_reminders(
        medication.id, user.id, [datetime.combine(date(2026, 10, 19), time(9, 0), tzinfo=MSK).astimezone(timezone.utc)]
    )
    for days_ago, status in ((1, "taken"), (2, "taken"), (3, "skipped")):
        at = datetime.combine(date(2026, 10, 18) - timedelta(days=days_ago), time(9, 5), tzinfo=MSK).astimezone(timezone.utc)
        if status == "taken":
            await meds.mark_taken(medication.id, user.id, taken_at_utc=at)
        else:
            await meds.mark_skipped(medication.id, user.id, skipped_at_utc=at)

    summary = await meds.weekly_summary(user.id, TZ, now)
    row = summary["rows"][0]
    assert (row["taken"], row["skipped"], row["expected"], row["unmarked"]) == (2, 1, 7, 4)
    text = MedicationService.format_weekly_summary(summary)
    assert "12.10–18.10" in text and "Магний: принято 2 из 7, пропущено 1, без отметки 4" in text
    assert "Итого принято 29%" in text


@pytest.mark.asyncio
async def test_weekly_summary_shows_a_break(db_session):
    user = User(telegram_id=55602, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Хофитол")
    await meds.pause_course(medication.id, user.id, datetime.now(MSK).date() + timedelta(days=60), TZ)
    text = MedicationService.format_weekly_summary(await meds.weekly_summary(user.id, TZ))
    assert "⏸ Хофитол: перерыв до" in text


def test_summary_buttons_are_registered():
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in ("med_summary", "med_summary_on", "med_summary_off", "note_new_done:5", "note_new_discard:5"):
        assert _is_registered(callback, patterns), callback


# --- Single instance -------------------------------------------------------------

@pytest.mark.asyncio
async def test_instance_lock_is_a_no_op_without_postgres():
    from src.services.instance_lock import acquire_instance_lock

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    lock = await acquire_instance_lock(engine, "bot")
    assert lock is not None and lock.connection is None
    await lock.release()
    await engine.dispose()


# --- Web: pause / resume -----------------------------------------------------------

@pytest.mark.asyncio
async def test_web_pause_and_resume(db_session):
    from src.api.app import create_application
    from src.api.user_auth import get_current_web_user
    from src.db.session import get_db

    user = User(telegram_id=55701, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Хофитол")
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    await meds.replace_daily_reminders(
        medication.id, user.id, [datetime.combine(tomorrow, time(10, 0), tzinfo=MSK).astimezone(timezone.utc)]
    )

    app = create_application()

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_web_user] = override_user
    until = (datetime.now(MSK).date() + timedelta(days=90)).isoformat()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        bad = await client.post(f"/me/medications/{medication.id}/pause", json={"until": "2020-01-01"})
        paused = await client.post(f"/me/medications/{medication.id}/pause", json={"until": until, "notice_days": 14})
        resumed = await client.post(f"/me/medications/{medication.id}/resume")

    assert bad.status_code == 400
    body = paused.json()
    assert body["paused_until"] == until and body["pause_notice_days"] == 14 and body["daily_times_local"] == ["10:00"]
    assert resumed.json()["paused_until"] is None and resumed.json()["daily_times_local"] == ["10:00"]


def test_backup_script_sends_to_telegram_once_a_day():
    from pathlib import Path

    script = Path("scripts/backup-vps.sh").read_text(encoding="utf-8")
    assert "send-backup-telegram.py" in script and "TELEGRAM_BACKUP_HOUR_UTC" in script
    sender = Path("scripts/send-backup-telegram.py").read_text(encoding="utf-8")
    assert "MAX_RECIPIENTS = 3" in sender and "ADMIN_TELEGRAM_IDS" in sender
