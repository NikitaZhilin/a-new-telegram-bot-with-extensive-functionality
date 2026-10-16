"""A dose marked «Пропустил» by mistake can be corrected to «Принял» (and back).

Found on 16.10.2026: «Пропустил» was pressed on the magnesium card, and the
«Принял» pressed 5 seconds later was refused as «already marked».
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from src.db.models import MedicationIntakeStatus, User
from src.services.medication_service import MedicationService

TZ = "Europe/Moscow"
MSK = ZoneInfo(TZ)


async def _medication_with_slot(db_session, telegram_id):
    user = User(telegram_id=telegram_id, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    meds = MedicationService(db_session)
    medication = await meds.create_medication(user_id=user.id, name="Магний")
    today = datetime.now(MSK).date()
    slot = datetime.combine(today, time(15, 0), tzinfo=MSK)
    await meds.replace_daily_reminders(medication.id, user.id, [slot.astimezone(timezone.utc) + timedelta(days=1)])
    return user, meds, medication, slot.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_skip_then_taken_on_the_same_slot_becomes_taken(db_session):
    user, meds, medication, slot = await _medication_with_slot(db_session, 87001)
    now = slot + timedelta(hours=2, minutes=28)

    skipped, _ = await meds.mark_skipped_for_current_slot(medication.id, user.id, TZ, skipped_at_utc=now)
    assert skipped.status == MedicationIntakeStatus.SKIPPED
    state = await meds.get_intake_action_state(medication.id, user.id, TZ, now_utc=now + timedelta(seconds=5))
    assert state.reason == "slot_already_marked" and state.marked_status == "skipped"

    fixed, _ = await meds.mark_taken_for_slot(
        medication.id, user.id, TZ, slot, taken_at_utc=now + timedelta(seconds=5)
    )
    assert fixed is not None and fixed.id == skipped.id
    assert fixed.status == MedicationIntakeStatus.TAKEN
    recent = await meds.get_recent_intakes(medication.id, user.id, limit=5)
    assert [i.status for i in recent] == [MedicationIntakeStatus.TAKEN]  # corrected, not duplicated


@pytest.mark.asyncio
async def test_same_button_twice_does_not_change_anything(db_session):
    user, meds, medication, slot = await _medication_with_slot(db_session, 87002)
    now = slot + timedelta(minutes=10)
    await meds.mark_taken_for_current_slot(medication.id, user.id, TZ, taken_at_utc=now)
    again, state = await meds.mark_taken_for_current_slot(medication.id, user.id, TZ, taken_at_utc=now + timedelta(minutes=1))
    assert again is None and state.reason == "slot_already_marked"


@pytest.mark.asyncio
async def test_taken_can_be_corrected_to_skipped_from_the_card(db_session):
    user, meds, medication, slot = await _medication_with_slot(db_session, 87003)
    now = slot + timedelta(minutes=10)
    taken, _ = await meds.mark_taken_for_current_slot(medication.id, user.id, TZ, taken_at_utc=now)
    fixed, _ = await meds.mark_skipped_for_current_slot(medication.id, user.id, TZ, skipped_at_utc=now + timedelta(minutes=1))
    assert fixed.id == taken.id and fixed.status == MedicationIntakeStatus.SKIPPED


def test_card_offers_the_correction_button():
    from src.bot.keyboards import get_medication_view_keyboard

    markup = get_medication_view_keyboard(5, can_mark=False, fix_action=("taken", 1760616000))
    first = markup.inline_keyboard[0][0]
    assert first.callback_data == "med_taken:5:1760616000"
    assert "принял" in first.text
