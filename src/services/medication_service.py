"""Medication service."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select

from src.db.models import Medication, MedicationIntake, MedicationIntakeStatus, Reminder, ReminderStatus, RepeatRule
from src.repositories.medication_repo import MedicationRepository
from src.services.reminder_service import ReminderService


@dataclass(frozen=True)
class MedicationIntakeActionState:
    """Whether a medication can be marked for the current scheduled slot."""

    can_mark: bool
    reason: str
    current_slot_at_utc: Optional[datetime] = None
    current_window_start_utc: Optional[datetime] = None
    next_available_at_utc: Optional[datetime] = None
    marked_at_utc: Optional[datetime] = None
    has_schedule: bool = False
    # For an already marked slot: how it was marked, so a wrong press can be fixed.
    marked_status: Optional[str] = None
    marked_intake_id: Optional[int] = None


@dataclass(frozen=True)
class MedicationDailySlot:
    """One visible intake slot for the current local day."""

    label: str
    status: str
    scheduled_time_local: Optional[str] = None
    slot_at_utc: Optional[datetime] = None
    window_start_utc: Optional[datetime] = None
    next_window_start_utc: Optional[datetime] = None
    marked_at_utc: Optional[datetime] = None
    intake_id: Optional[int] = None


class MedicationService:
    """Business logic for medication schedules and intake marks."""

    SLOT_OPEN_BEFORE = timedelta(hours=2)
    # A "Taken"/"Skipped" button on a reminder message stays bound to its own
    # slot for this long; older presses fall back to the current slot.
    SLOT_LATE_MARK_LIMIT = timedelta(hours=24)
    SLOT_MATCH_TOLERANCE = timedelta(seconds=59)

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MedicationRepository(db)

    async def create_medication(
        self,
        user_id: int,
        name: str,
        dosage: Optional[str] = None,
        instructions: Optional[str] = None,
        importance: str = "normal",
    ) -> Medication:
        """Create a medication schedule."""
        medication = Medication(
            user_id=user_id,
            name=name.strip(),
            dosage=dosage.strip() if dosage else None,
            instructions=instructions.strip() if instructions else None,
            importance=importance if importance in {"supplement", "normal", "important", "critical"} else "normal",
            is_active=True,
        )
        self.db.add(medication)
        await self.db.flush()
        await self.db.refresh(medication)
        return medication

    async def get_medication(self, medication_id: int, user_id: int) -> Optional[Medication]:
        """Get medication with ownership check."""
        return await self.repo.get_for_user(medication_id, user_id)

    async def get_medications_list(
        self,
        user_id: int,
        page: int = 0,
        page_size: int = 10,
        active: bool = True,
    ) -> tuple[list[Medication], int]:
        """Get paginated medications."""
        offset = page * page_size
        items = await self.repo.get_by_user(
            user_id=user_id,
            active=active,
            limit=page_size,
            offset=offset,
        )
        total = await self.repo.count_by_user(user_id, active=active)
        return list(items), total

    async def update_medication(
        self,
        medication_id: int,
        user_id: int,
        name: Optional[str] = None,
        dosage: Optional[str] = None,
        instructions: Optional[str] = None,
        importance: Optional[str] = None,
    ) -> Optional[Medication]:
        """Update user-owned medication."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication:
            return None

        if name is not None:
            medication.name = name.strip()
        if dosage is not None:
            medication.dosage = dosage.strip() or None
        if instructions is not None:
            medication.instructions = instructions.strip() or None
        if importance is not None:
            medication.importance = importance if importance in {"supplement", "normal", "important", "critical"} else "normal"

        medication.updated_at = datetime.now(timezone.utc)

        # Active reminders carry a copy of name/dosage in their text. Without
        # this they kept showing the old dosage after it was changed.
        reminders_result = await self.db.execute(
            select(Reminder).where(
                and_(
                    Reminder.medication_id == medication_id,
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
        )
        new_text = self._reminder_text(medication)
        for reminder in reminders_result.scalars().all():
            if (reminder.text or "").startswith(("Принять лекарство", "Важное напоминание")):
                reminder.text = new_text

        await self.db.flush()
        await self.db.refresh(medication)
        return medication

    async def archive_medication(self, medication_id: int, user_id: int) -> bool:
        """Archive medication instead of hard-deleting intake history."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication:
            return False

        medication.is_active = False
        medication.updated_at = datetime.now(timezone.utc)
        await self._cancel_pause_notice(medication)
        medication.paused_until = None
        medication.paused_schedule = None
        medication.pause_notice_days = None

        reminders_result = await self.db.execute(
            select(Reminder).where(
                and_(
                    Reminder.medication_id == medication_id,
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
        )
        for reminder in reminders_result.scalars().all():
            self._cancel_reminder(reminder)

        await self.db.flush()
        return True

    async def mark_taken(
        self,
        medication_id: int,
        user_id: int,
        taken_at_utc: Optional[datetime] = None,
        note: Optional[str] = None,
        scheduled_slot_at_utc: Optional[datetime] = None,
    ) -> Optional[MedicationIntake]:
        """Mark medication as taken, with ownership check."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return None

        taken_at_utc = taken_at_utc or datetime.now(timezone.utc)
        if taken_at_utc.tzinfo is None:
            taken_at_utc = taken_at_utc.replace(tzinfo=timezone.utc)

        intake = await self.repo.add_intake(
            medication_id=medication_id,
            user_id=user_id,
            taken_at_utc=taken_at_utc,
            note=note,
            scheduled_slot_at_utc=scheduled_slot_at_utc,
            medication_name_snapshot=medication.name,
            dosage_snapshot=medication.dosage,
            instructions_snapshot=medication.instructions,
            importance_snapshot=medication.importance,
        )
        medication.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return intake

    async def mark_skipped(
        self,
        medication_id: int,
        user_id: int,
        skipped_at_utc: Optional[datetime] = None,
        note: Optional[str] = None,
        scheduled_slot_at_utc: Optional[datetime] = None,
    ) -> Optional[MedicationIntake]:
        """Mark medication intake as skipped."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return None

        skipped_at_utc = skipped_at_utc or datetime.now(timezone.utc)
        if skipped_at_utc.tzinfo is None:
            skipped_at_utc = skipped_at_utc.replace(tzinfo=timezone.utc)

        intake = await self.repo.add_intake(
            medication_id=medication_id,
            user_id=user_id,
            taken_at_utc=skipped_at_utc,
            status=MedicationIntakeStatus.SKIPPED,
            note=note,
            scheduled_slot_at_utc=scheduled_slot_at_utc,
            medication_name_snapshot=medication.name,
            dosage_snapshot=medication.dosage,
            instructions_snapshot=medication.instructions,
            importance_snapshot=medication.importance,
        )
        medication.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return intake

    async def get_intake_action_state(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        now_utc: Optional[datetime] = None,
    ) -> MedicationIntakeActionState:
        """Return whether the user can mark the current scheduled intake slot."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return MedicationIntakeActionState(can_mark=False, reason="not_found")
        if self.is_paused(medication):
            return MedicationIntakeActionState(can_mark=False, reason="paused")

        now_utc = now_utc or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        schedule = await self._get_daily_schedule_times(medication_id, user_id, user_timezone)
        if not schedule:
            start = self._local_day_start_utc(now_utc, user_timezone)
            marked_at = await self._get_intake_in_window(
                medication_id=medication_id,
                user_id=user_id,
                start_utc=start,
                end_utc=start + timedelta(days=1),
            )
            if marked_at:
                return MedicationIntakeActionState(
                    can_mark=False,
                    reason="already_marked_today",
                    current_window_start_utc=start,
                    next_available_at_utc=start + timedelta(days=1),
                    marked_at_utc=marked_at,
                    has_schedule=False,
                )
            return MedicationIntakeActionState(can_mark=True, reason="manual_daily", has_schedule=False)

        current_slot, current_open, next_open = self._resolve_current_slot_window(
            schedule=schedule,
            user_timezone=user_timezone,
            now_utc=now_utc,
        )
        intake = await self._get_intake_record_for_slot(
            medication_id=medication_id,
            user_id=user_id,
            slot_utc=current_slot,
            open_utc=current_open,
            next_open_utc=next_open,
            known_slots=self._slot_occurrences(schedule, user_timezone, now_utc),
        )
        marked_at = self._ensure_utc(intake.taken_at_utc) if intake else None
        if marked_at:
            return MedicationIntakeActionState(
                can_mark=False,
                reason="slot_already_marked",
                current_slot_at_utc=current_slot,
                current_window_start_utc=current_open,
                next_available_at_utc=next_open,
                marked_at_utc=marked_at,
                has_schedule=True,
                marked_status=self._slot_status_from_intake(intake),
                marked_intake_id=intake.id,
            )

        return MedicationIntakeActionState(
            can_mark=True,
            reason="slot_available",
            current_slot_at_utc=current_slot,
            current_window_start_utc=current_open,
            next_available_at_utc=next_open,
            has_schedule=True,
        )

    async def _correct_mark(
        self,
        state: MedicationIntakeActionState,
        kind: str,
        medication_id: int,
        user_id: int,
        now_utc: datetime,
    ) -> Optional[MedicationIntake]:
        """A slot marked «skipped» by mistake can be re-marked «taken» (and back)."""
        if state.reason != "slot_already_marked" or not state.marked_intake_id or state.marked_status == kind:
            return None
        intake = await self.db.get(MedicationIntake, state.marked_intake_id)
        if intake is None or intake.medication_id != medication_id or intake.user_id != user_id:
            return None
        intake.status = MedicationIntakeStatus.TAKEN if kind == "taken" else MedicationIntakeStatus.SKIPPED
        intake.taken_at_utc = now_utc
        await self.db.flush()
        return intake

    async def mark_taken_for_current_slot(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        taken_at_utc: Optional[datetime] = None,
    ) -> tuple[Optional[MedicationIntake], MedicationIntakeActionState]:
        """Mark the current scheduled slot as taken if it is not already closed."""
        now_utc = taken_at_utc or datetime.now(timezone.utc)
        state = await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
        if not state.can_mark:
            corrected = await self._correct_mark(state, "taken", medication_id, user_id, self._ensure_utc(now_utc))
            if corrected:
                return corrected, await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
            return None, state
        intake = await self.mark_taken(
            medication_id,
            user_id,
            taken_at_utc=now_utc,
            scheduled_slot_at_utc=state.current_slot_at_utc,
        )
        updated_state = await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
        return intake, updated_state

    async def mark_skipped_for_current_slot(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        skipped_at_utc: Optional[datetime] = None,
    ) -> tuple[Optional[MedicationIntake], MedicationIntakeActionState]:
        """Mark the current scheduled slot as skipped if it is not already closed."""
        now_utc = skipped_at_utc or datetime.now(timezone.utc)
        state = await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
        if not state.can_mark:
            corrected = await self._correct_mark(state, "skipped", medication_id, user_id, self._ensure_utc(now_utc))
            if corrected:
                return corrected, await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
            return None, state
        intake = await self.mark_skipped(
            medication_id,
            user_id,
            skipped_at_utc=now_utc,
            scheduled_slot_at_utc=state.current_slot_at_utc,
        )
        updated_state = await self.get_intake_action_state(medication_id, user_id, user_timezone, now_utc=now_utc)
        return intake, updated_state

    async def snooze_reminder(
        self,
        medication_id: int,
        user_id: int,
        minutes: int = 15,
    ) -> Optional[Reminder]:
        """Create a one-time reminder for a medication after a delay."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return None

        reminder_service = ReminderService(self.db)
        return await reminder_service.create_reminder(
            user_id=user_id,
            text=f"Повторное напоминание: принять лекарство {medication.name}",
            title="💊 Приём лекарства",
            remind_at_utc=datetime.now(timezone.utc) + timedelta(minutes=minutes),
            repeat_rule=RepeatRule.NONE,
            medication_id=medication_id,
        )

    async def get_recent_intakes(
        self,
        medication_id: int,
        user_id: int,
        limit: int = 5,
    ) -> list[MedicationIntake]:
        """Get recent intake marks."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication:
            return []
        return list(await self.repo.get_intakes_for_user(medication_id, user_id, limit=limit))

    async def get_today_slots(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        now_utc: Optional[datetime] = None,
    ) -> list[MedicationDailySlot]:
        """Return today's visible intake slots with taken/skipped/pending state."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active or self.is_paused(medication):
            return []

        now_utc = now_utc or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)

        tz = ZoneInfo(user_timezone)
        local_today = now_utc.astimezone(tz).date()
        schedule = await self._get_daily_schedule_times(medication_id, user_id, user_timezone)

        if not schedule:
            start_utc = self._local_day_start_utc(now_utc, user_timezone)
            end_utc = start_utc + timedelta(days=1)
            intake = await self._get_intake_record_in_window(medication_id, user_id, start_utc, end_utc)
            return [
                MedicationDailySlot(
                    label="Сегодня",
                    status=self._slot_status_from_intake(intake) if intake else "available",
                    window_start_utc=start_utc,
                    next_window_start_utc=end_utc,
                    marked_at_utc=self._ensure_utc(intake.taken_at_utc) if intake else None,
                    intake_id=intake.id if intake else None,
                )
            ]

        occurrences: list[tuple[time, datetime, datetime]] = []
        for scheduled_time in schedule:
            slot_local = datetime.combine(local_today, scheduled_time, tzinfo=tz)
            open_utc = (slot_local - self.SLOT_OPEN_BEFORE).astimezone(timezone.utc)
            occurrences.append((scheduled_time, slot_local.astimezone(timezone.utc), open_utc))

        known_slots = self._slot_occurrences(schedule, user_timezone, now_utc)
        result: list[MedicationDailySlot] = []
        for index, (scheduled_time, slot_utc, open_utc) in enumerate(occurrences):
            next_open_utc = (
                occurrences[index + 1][2]
                if index + 1 < len(occurrences)
                else (datetime.combine(local_today + timedelta(days=1), schedule[0], tzinfo=tz) - self.SLOT_OPEN_BEFORE).astimezone(timezone.utc)
            )
            intake = await self._get_intake_record_for_slot(
                medication_id=medication_id,
                user_id=user_id,
                slot_utc=slot_utc,
                open_utc=open_utc,
                next_open_utc=next_open_utc,
                known_slots=known_slots,
            )
            if intake:
                status = self._slot_status_from_intake(intake)
            elif now_utc < open_utc:
                status = "pending"
            elif now_utc < next_open_utc:
                status = "available"
            else:
                status = "missed"

            result.append(
                MedicationDailySlot(
                    label=scheduled_time.strftime("%H:%M"),
                    scheduled_time_local=scheduled_time.strftime("%H:%M"),
                    status=status,
                    slot_at_utc=slot_utc,
                    window_start_utc=open_utc,
                    next_window_start_utc=next_open_utc,
                    marked_at_utc=self._ensure_utc(intake.taken_at_utc) if intake else None,
                    intake_id=intake.id if intake else None,
                )
            )
        return result

    async def _get_daily_schedule_times(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
    ) -> list[time]:
        """Return distinct local daily reminder times for a medication."""
        query = (
            select(Reminder.remind_at_utc)
            .where(
                and_(
                    Reminder.medication_id == medication_id,
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                    Reminder.repeat_rule == RepeatRule.DAILY,
                )
            )
        )
        result = await self.db.execute(query)
        tz = ZoneInfo(user_timezone)
        values = set()
        for remind_at in result.scalars().all():
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)
            values.add(remind_at.astimezone(tz).time().replace(second=0, microsecond=0))
        return sorted(values)

    async def _get_intake_in_window(
        self,
        medication_id: int,
        user_id: int,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Optional[datetime]:
        """Return latest intake mark inside a window."""
        intake = await self._get_intake_record_in_window(medication_id, user_id, start_utc, end_utc)
        return self._ensure_utc(intake.taken_at_utc) if intake else None

    async def _get_intake_record_in_window(
        self,
        medication_id: int,
        user_id: int,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Optional[MedicationIntake]:
        """Return latest intake record inside a window."""
        query = (
            select(MedicationIntake)
            .where(
                and_(
                    MedicationIntake.medication_id == medication_id,
                    MedicationIntake.user_id == user_id,
                    MedicationIntake.taken_at_utc >= start_utc,
                    MedicationIntake.taken_at_utc < end_utc,
                )
            )
            .order_by(MedicationIntake.taken_at_utc.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _slot_occurrences(
        self,
        schedule: list[time],
        user_timezone: str,
        around_utc: datetime,
        day_offsets: tuple[int, ...] = (-1, 0, 1, 2),
    ) -> list[datetime]:
        """Return scheduled slot moments (UTC) for days around a moment."""
        tz = ZoneInfo(user_timezone)
        local_date = self._ensure_utc(around_utc).astimezone(tz).date()
        slots = [
            datetime.combine(local_date + timedelta(days=offset), scheduled_time, tzinfo=tz).astimezone(timezone.utc)
            for offset in day_offsets
            for scheduled_time in schedule
        ]
        return sorted(slots)

    def _same_slot(self, left: datetime, right: datetime) -> bool:
        return abs(self._ensure_utc(left) - self._ensure_utc(right)) <= self.SLOT_MATCH_TOLERANCE

    def _intake_belongs_to_window(
        self,
        intake: MedicationIntake,
        slot_utc: datetime,
        open_utc: datetime,
        next_open_utc: datetime,
        known_slots: list[datetime],
    ) -> bool:
        """Decide which slot an intake mark counts for.

        A mark made for a specific slot (from a reminder button or for the
        current slot) counts for that slot, even when it was pressed hours
        later. Marks without a slot, or whose slot is no longer in the
        schedule, count for the window in which they fall.
        """
        scheduled = intake.scheduled_slot_at_utc
        if scheduled is not None:
            scheduled = self._ensure_utc(scheduled)
            if self._same_slot(scheduled, slot_utc):
                return True
            if any(self._same_slot(scheduled, other) for other in known_slots):
                return False
            return open_utc <= scheduled < next_open_utc
        taken = self._ensure_utc(intake.taken_at_utc)
        return open_utc <= taken < next_open_utc

    async def _get_intake_record_for_slot(
        self,
        medication_id: int,
        user_id: int,
        slot_utc: datetime,
        open_utc: datetime,
        next_open_utc: datetime,
        known_slots: list[datetime],
    ) -> Optional[MedicationIntake]:
        """Return the latest intake that counts for a scheduled slot."""
        margin = self.SLOT_LATE_MARK_LIMIT + timedelta(days=1)
        range_start = open_utc - margin
        range_end = next_open_utc + margin
        query = (
            select(MedicationIntake)
            .where(
                and_(
                    MedicationIntake.medication_id == medication_id,
                    MedicationIntake.user_id == user_id,
                    or_(
                        and_(
                            MedicationIntake.taken_at_utc >= range_start,
                            MedicationIntake.taken_at_utc < range_end,
                        ),
                        and_(
                            MedicationIntake.scheduled_slot_at_utc >= range_start,
                            MedicationIntake.scheduled_slot_at_utc < range_end,
                        ),
                    ),
                )
            )
            .order_by(MedicationIntake.taken_at_utc.desc(), MedicationIntake.id.desc())
        )
        result = await self.db.execute(query)
        for intake in result.scalars().all():
            if self._intake_belongs_to_window(intake, slot_utc, open_utc, next_open_utc, known_slots):
                return intake
        return None

    async def get_slot_action_state(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        slot_utc: datetime,
        now_utc: Optional[datetime] = None,
    ) -> Optional[MedicationIntakeActionState]:
        """State of one specific scheduled slot, e.g. the one a reminder was for.

        Returns None when the slot is not (or no longer) part of the schedule,
        or is too old; callers then fall back to the current slot.
        """
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return MedicationIntakeActionState(can_mark=False, reason="not_found")
        if self.is_paused(medication):
            return MedicationIntakeActionState(can_mark=False, reason="paused")

        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        slot_utc = self._ensure_utc(slot_utc)
        if now_utc - slot_utc > self.SLOT_LATE_MARK_LIMIT:
            return None

        schedule = await self._get_daily_schedule_times(medication_id, user_id, user_timezone)
        if not schedule:
            return None
        occurrences = self._slot_occurrences(schedule, user_timezone, slot_utc)
        index = next((i for i, item in enumerate(occurrences) if self._same_slot(item, slot_utc)), None)
        if index is None or index + 1 >= len(occurrences):
            return None

        slot_utc = occurrences[index]
        open_utc = slot_utc - self.SLOT_OPEN_BEFORE
        next_open_utc = occurrences[index + 1] - self.SLOT_OPEN_BEFORE
        if now_utc < open_utc:
            return MedicationIntakeActionState(
                can_mark=False,
                reason="slot_not_open",
                current_slot_at_utc=slot_utc,
                current_window_start_utc=open_utc,
                next_available_at_utc=open_utc,
                has_schedule=True,
            )

        intake = await self._get_intake_record_for_slot(
            medication_id=medication_id,
            user_id=user_id,
            slot_utc=slot_utc,
            open_utc=open_utc,
            next_open_utc=next_open_utc,
            known_slots=occurrences,
        )
        if intake:
            return MedicationIntakeActionState(
                can_mark=False,
                reason="slot_already_marked",
                current_slot_at_utc=slot_utc,
                current_window_start_utc=open_utc,
                next_available_at_utc=max(next_open_utc, now_utc),
                marked_at_utc=self._ensure_utc(intake.taken_at_utc),
                has_schedule=True,
                marked_status=self._slot_status_from_intake(intake),
                marked_intake_id=intake.id,
            )
        return MedicationIntakeActionState(
            can_mark=True,
            reason="slot_available",
            current_slot_at_utc=slot_utc,
            current_window_start_utc=open_utc,
            next_available_at_utc=next_open_utc,
            has_schedule=True,
        )

    async def _mark_for_slot(
        self,
        kind: str,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        slot_utc: datetime,
        now_utc: Optional[datetime] = None,
    ) -> tuple[Optional[MedicationIntake], MedicationIntakeActionState]:
        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        state = await self.get_slot_action_state(medication_id, user_id, user_timezone, slot_utc, now_utc=now_utc)
        if state is None:
            if kind == "taken":
                return await self.mark_taken_for_current_slot(medication_id, user_id, user_timezone, taken_at_utc=now_utc)
            return await self.mark_skipped_for_current_slot(medication_id, user_id, user_timezone, skipped_at_utc=now_utc)
        if not state.can_mark:
            corrected = await self._correct_mark(state, kind, medication_id, user_id, now_utc)
            if corrected:
                updated = await self.get_slot_action_state(
                    medication_id, user_id, user_timezone, state.current_slot_at_utc, now_utc=now_utc
                )
                return corrected, updated or state
            return None, state
        if kind == "taken":
            intake = await self.mark_taken(
                medication_id, user_id, taken_at_utc=now_utc, scheduled_slot_at_utc=state.current_slot_at_utc
            )
        else:
            intake = await self.mark_skipped(
                medication_id, user_id, skipped_at_utc=now_utc, scheduled_slot_at_utc=state.current_slot_at_utc
            )
        updated = await self.get_slot_action_state(
            medication_id, user_id, user_timezone, state.current_slot_at_utc, now_utc=now_utc
        )
        return intake, updated or state

    async def mark_taken_for_slot(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        slot_utc: datetime,
        taken_at_utc: Optional[datetime] = None,
    ) -> tuple[Optional[MedicationIntake], MedicationIntakeActionState]:
        """Mark the slot a reminder was sent for (not whatever slot is current now)."""
        return await self._mark_for_slot("taken", medication_id, user_id, user_timezone, slot_utc, taken_at_utc)

    async def mark_skipped_for_slot(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        slot_utc: datetime,
        skipped_at_utc: Optional[datetime] = None,
    ) -> tuple[Optional[MedicationIntake], MedicationIntakeActionState]:
        """Mark the reminder's own slot as skipped."""
        return await self._mark_for_slot("skipped", medication_id, user_id, user_timezone, slot_utc, skipped_at_utc)

    @staticmethod
    def _slot_status_from_intake(intake: MedicationIntake) -> str:
        """Return public slot status from an intake record."""
        status = intake.status.value if hasattr(intake.status, "value") else intake.status
        status = str(status).lower()
        return "skipped" if status in {"skipped", "skip"} else "taken"

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        """Normalize a datetime to UTC."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _local_day_start_utc(self, now_utc: datetime, user_timezone: str) -> datetime:
        """Return user's local midnight for now as UTC."""
        tz = ZoneInfo(user_timezone)
        local_now = now_utc.astimezone(tz)
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=tz)
        return local_start.astimezone(timezone.utc)

    def _resolve_current_slot_window(
        self,
        schedule: list[time],
        user_timezone: str,
        now_utc: datetime,
    ) -> tuple[datetime, datetime, datetime]:
        """Resolve current scheduled slot window and the next window opening."""
        tz = ZoneInfo(user_timezone)
        local_now = now_utc.astimezone(tz)
        occurrences = []
        for day_offset in (-1, 0, 1, 2):
            local_date = local_now.date() + timedelta(days=day_offset)
            for scheduled_time in schedule:
                slot_local = datetime.combine(local_date, scheduled_time, tzinfo=tz)
                open_local = slot_local - self.SLOT_OPEN_BEFORE
                occurrences.append(
                    (
                        slot_local.astimezone(timezone.utc),
                        open_local.astimezone(timezone.utc),
                    )
                )

        occurrences.sort(key=lambda item: item[1])
        current_index = 0
        for index, (_, open_utc) in enumerate(occurrences):
            if open_utc <= now_utc:
                current_index = index
            else:
                break

        current_slot, current_open = occurrences[current_index]
        next_index = min(current_index + 1, len(occurrences) - 1)
        next_open = occurrences[next_index][1]
        return current_slot, current_open, next_open

    async def create_reminder(
        self,
        medication_id: int,
        user_id: int,
        remind_at_utc: datetime,
        repeat_rule: RepeatRule = RepeatRule.DAILY,
    ) -> Optional[Reminder]:
        """Create a reminder linked to a medication (not during a break between courses)."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active or self.is_paused(medication):
            return None

        if remind_at_utc.tzinfo is None:
            remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)

        if repeat_rule == RepeatRule.DAILY:
            existing = await self._get_active_daily_reminders(medication_id, user_id)
            duplicate = None
            duplicate_key = self._reminder_time_key(remind_at_utc)
            for reminder in existing:
                if self._reminder_time_key(reminder.remind_at_utc) != duplicate_key:
                    continue
                if duplicate is None:
                    duplicate = reminder
                    self._retime_reminder(duplicate, remind_at_utc)
                else:
                    self._cancel_reminder(reminder)

            if duplicate:
                await self.db.flush()
                await self.db.refresh(duplicate)
                return duplicate

        text = self._reminder_text(medication)

        reminder_service = ReminderService(self.db)
        return await reminder_service.create_reminder(
            user_id=user_id,
            text=text,
            title="💊 Приём лекарства",
            remind_at_utc=remind_at_utc,
            repeat_rule=repeat_rule,
            medication_id=medication_id,
        )

    @staticmethod
    def _cancel_reminder(reminder: Reminder) -> None:
        """Cancel a reminder together with its pending deliveries.

        Setting only the status left PENDING delivery rows behind forever.
        """
        reminder.status = ReminderStatus.CANCELED
        ReminderService._cancel_pending_notifications(reminder)

    def _retime_reminder(self, reminder: Reminder, remind_at_utc: datetime) -> None:
        """Move a reminder and rebuild its deliveries for the new time."""
        offsets = ReminderService._active_notification_offsets(reminder)
        reminder.remind_at_utc = remind_at_utc
        reminder.notified_at = None
        ReminderService._cancel_pending_notifications(reminder)
        ReminderService(self.db)._add_notification_plan(reminder, offsets)

    @staticmethod
    def _reminder_text(medication: Medication) -> str:
        """Reminder text built from the medication's current details."""
        text = f"Принять лекарство: {medication.name}"
        if medication.importance in {"important", "critical"}:
            text = f"Важное напоминание. {text}"
        if medication.dosage:
            text += f"\nДозировка: {medication.dosage}"
        if medication.instructions:
            text += f"\nКомментарий: {medication.instructions}"
        return text

    async def replace_daily_reminders(
        self,
        medication_id: int,
        user_id: int,
        remind_at_utcs: list[datetime],
    ) -> list[Reminder]:
        """Replace a medication's active daily schedule with the provided times."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active or self.is_paused(medication):
            return []

        normalized: dict[tuple[int, int], datetime] = {}
        for remind_at_utc in remind_at_utcs:
            if remind_at_utc.tzinfo is None:
                remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)
            normalized[self._reminder_time_key(remind_at_utc)] = remind_at_utc

        existing = await self._get_active_daily_reminders(medication_id, user_id)
        existing_by_key: dict[tuple[int, int], Reminder] = {}
        for reminder in existing:
            key = self._reminder_time_key(reminder.remind_at_utc)
            if key in existing_by_key:
                self._cancel_reminder(reminder)
                continue
            existing_by_key[key] = reminder

        created_or_updated: list[Reminder] = []
        for key, reminder in existing_by_key.items():
            if key not in normalized:
                self._cancel_reminder(reminder)
                continue
            self._retime_reminder(reminder, normalized[key])
            created_or_updated.append(reminder)

        for key, remind_at_utc in normalized.items():
            if key in existing_by_key:
                continue
            reminder = await self.create_reminder(
                medication_id=medication_id,
                user_id=user_id,
                remind_at_utc=remind_at_utc,
                repeat_rule=RepeatRule.DAILY,
            )
            if reminder:
                created_or_updated.append(reminder)

        await self.db.flush()
        return sorted(created_or_updated, key=lambda item: item.remind_at_utc)

    async def _get_active_daily_reminders(
        self,
        medication_id: int,
        user_id: int,
    ) -> list[Reminder]:
        """Return active daily reminders for one medication."""
        result = await self.db.execute(
            select(Reminder).where(
                and_(
                    Reminder.medication_id == medication_id,
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                    Reminder.repeat_rule == RepeatRule.DAILY,
                )
            )
        )
        return list(result.scalars().all())

    def _reminder_time_key(self, remind_at_utc: datetime) -> tuple[int, int]:
        """Deduplicate daily medication reminders by UTC clock time."""
        if remind_at_utc.tzinfo is None:
            remind_at_utc = remind_at_utc.replace(tzinfo=timezone.utc)
        utc = remind_at_utc.astimezone(timezone.utc)
        return utc.hour, utc.minute

    # --- Break between courses ------------------------------------------------

    PAUSE_NOTICE_DAYS = 7
    PAUSE_DEFAULT_TIME = time(10, 0)

    @staticmethod
    def is_paused(medication: Optional[Medication]) -> bool:
        return bool(medication is not None and getattr(medication, "paused_until", None))

    @staticmethod
    def _parse_hhmm(value: str) -> Optional[time]:
        try:
            hours, minutes = str(value).split(":", 1)
            return time(int(hours), int(minutes))
        except (TypeError, ValueError):
            return None

    @classmethod
    def paused_times(cls, medication: Medication) -> list[time]:
        times = [cls._parse_hhmm(item) for item in (medication.paused_schedule or [])]
        return sorted(item for item in times if item is not None)

    @classmethod
    def notice_days(cls, medication: Medication) -> int:
        value = getattr(medication, "pause_notice_days", None)
        return cls.PAUSE_NOTICE_DAYS if value is None else int(value)

    @staticmethod
    def days_phrase(days: int) -> str:
        """3 → «3 дня», 7 → «неделю», 14 → «2 недели»."""
        if days == 7:
            return "неделю"
        if days == 14:
            return "2 недели"
        if days % 10 == 1 and days % 100 != 11:
            return f"{days} день"
        if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
            return f"{days} дня"
        return f"{days} дней"

    @classmethod
    def pause_notice_at(cls, medication: Medication, user_timezone: str) -> Optional[datetime]:
        """When the «course starts soon» heads-up fires (UTC), or None when it is off."""
        if not medication.paused_until or cls.notice_days(medication) <= 0:
            return None
        notice_day = medication.paused_until - timedelta(days=cls.notice_days(medication))
        times = cls.paused_times(medication)
        local = datetime.combine(notice_day, times[0] if times else cls.PAUSE_DEFAULT_TIME, tzinfo=ZoneInfo(user_timezone))
        return local.astimezone(timezone.utc)

    async def _cancel_pause_notice(self, medication: Medication) -> None:
        if not medication.pause_notice_reminder_id:
            return
        reminder = await self.db.get(Reminder, medication.pause_notice_reminder_id)
        if reminder is not None and reminder.user_id == medication.user_id and reminder.status == ReminderStatus.ACTIVE:
            self._cancel_reminder(reminder)
        medication.pause_notice_reminder_id = None

    async def pause_course(
        self,
        medication_id: int,
        user_id: int,
        until: date,
        user_timezone: str,
        now_utc: Optional[datetime] = None,
        notice_days: Optional[int] = None,
    ) -> Optional[Medication]:
        """Stop reminders until ``until`` (local date); keep the daily times to bring them back.

        ``notice_days``: heads-up that many days before the course (0 = none, None = 7).
        """
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return None
        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        today = now_utc.astimezone(ZoneInfo(user_timezone)).date()
        if until <= today:
            raise ValueError("pause must end in the future")

        if not self.is_paused(medication):
            times = await self._get_daily_schedule_times(medication_id, user_id, user_timezone)
            medication.paused_schedule = [item.strftime("%H:%M") for item in times]
        await self._cancel_pause_notice(medication)

        active = await self.db.execute(
            select(Reminder).where(
                and_(
                    Reminder.medication_id == medication_id,
                    Reminder.user_id == user_id,
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
        )
        for reminder in active.scalars().all():
            self._cancel_reminder(reminder)

        medication.paused_until = until
        medication.pause_notice_days = self.PAUSE_NOTICE_DAYS if notice_days is None else max(0, int(notice_days))
        medication.updated_at = now_utc

        notice_at = self.pause_notice_at(medication, user_timezone)
        if notice_at is not None and notice_at > now_utc:
            times_text = ", ".join(item.strftime("%H:%M") for item in self.paused_times(medication))
            text = (
                f"Через {self.days_phrase(self.notice_days(medication))}, {until.strftime('%d.%m.%Y')}, "
                f"снова начинается курс: {medication.name}.\n"
                + (f"Напоминания о приёме вернутся сами ({times_text})." if times_text else
                   "Не забудьте настроить время приёма в карточке лекарства.")
                + "\nЕсли нужно — купите лекарство заранее."
            )
            notice = await ReminderService(self.db).create_reminder(
                user_id=user_id,
                text=text,
                title="💊 Скоро курс",
                remind_at_utc=notice_at,
            )
            if notice is not None:
                medication.pause_notice_reminder_id = notice.id

        await self.db.flush()
        return medication

    async def resume_course(
        self,
        medication_id: int,
        user_id: int,
        user_timezone: str,
        now_utc: Optional[datetime] = None,
    ) -> Optional[Medication]:
        """End the break now: daily reminders come back at the saved times."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
            return None
        if not self.is_paused(medication):
            return medication
        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        times = self.paused_times(medication)
        await self._cancel_pause_notice(medication)
        medication.paused_until = None
        medication.paused_schedule = None
        medication.pause_notice_days = None
        medication.updated_at = now_utc
        await self.db.flush()

        tz = ZoneInfo(user_timezone)
        local_now = now_utc.astimezone(tz)
        next_times = []
        for item in times:
            local = datetime.combine(local_now.date(), item, tzinfo=tz)
            if local <= local_now:
                local += timedelta(days=1)
            next_times.append(local.astimezone(timezone.utc))
        if next_times:
            await self.replace_daily_reminders(medication_id, user_id, next_times)
        await self.db.flush()
        return medication

    async def resume_due_courses(self, now_utc: datetime, default_timezone: str) -> list[tuple[Medication, "User"]]:
        """Bring back every course whose break ends today (user's local date) or earlier."""
        from src.db.models import User
        from src.utils.timezones import safe_timezone_name

        now_utc = self._ensure_utc(now_utc)
        rows = await self.db.execute(
            select(Medication, User)
            .join(User, User.id == Medication.user_id)
            .where(and_(Medication.is_active.is_(True), Medication.paused_until.is_not(None)))
        )
        resumed = []
        for medication, user in rows.all():
            tz_name = safe_timezone_name(user.timezone, default_timezone)
            if medication.paused_until > now_utc.astimezone(ZoneInfo(tz_name)).date():
                continue
            await self.resume_course(medication.id, user.id, tz_name, now_utc=now_utc)
            resumed.append((medication, user))
        return resumed

    # --- Weekly summary ---------------------------------------------------------

    async def weekly_summary(self, user_id: int, user_timezone: str, now_utc: Optional[datetime] = None) -> dict:
        """Taken / skipped / unmarked doses per medication for the last 7 local days (today included)."""
        now_utc = self._ensure_utc(now_utc or datetime.now(timezone.utc))
        tz = ZoneInfo(user_timezone)
        today = now_utc.astimezone(tz).date()
        first_day = today - timedelta(days=6)
        start_utc = datetime.combine(first_day, time.min, tzinfo=tz).astimezone(timezone.utc)

        medications = (
            await self.db.execute(
                select(Medication)
                .where(and_(Medication.user_id == user_id, Medication.is_active.is_(True)))
                .order_by(Medication.name)
            )
        ).scalars().all()
        rows = []
        for medication in medications:
            intakes = (
                await self.db.execute(
                    select(MedicationIntake).where(
                        and_(
                            MedicationIntake.medication_id == medication.id,
                            MedicationIntake.user_id == user_id,
                            MedicationIntake.taken_at_utc >= start_utc,
                            MedicationIntake.taken_at_utc <= now_utc,
                        )
                    )
                )
            ).scalars().all()
            taken = sum(1 for item in intakes if self._slot_status_from_intake(item) == "taken")
            skipped = len(intakes) - taken
            paused = self.is_paused(medication)
            times = (
                self.paused_times(medication)
                if paused
                else await self._get_daily_schedule_times(medication.id, user_id, user_timezone)
            )
            expected = 0
            if times and not paused:
                created = self._ensure_utc(medication.created_at).astimezone(tz).date() if medication.created_at else first_day
                for offset in range(7):
                    day = first_day + timedelta(days=offset)
                    if day < created:
                        continue
                    for slot_time in times:
                        slot_utc = datetime.combine(day, slot_time, tzinfo=tz).astimezone(timezone.utc)
                        if slot_utc <= now_utc:
                            expected += 1
            if not intakes and not expected and not paused:
                continue
            rows.append(
                {
                    "name": medication.name,
                    "taken": taken,
                    "skipped": skipped,
                    "expected": max(expected, taken + skipped),
                    "unmarked": max(expected - taken - skipped, 0),
                    "paused_until": medication.paused_until if paused else None,
                }
            )
        return {"first_day": first_day, "last_day": today, "rows": rows}

    @staticmethod
    def format_weekly_summary(summary: dict) -> Optional[str]:
        rows = summary["rows"]
        if not rows:
            return None
        lines = [
            f"📊 Лекарства за неделю ({summary['first_day'].strftime('%d.%m')}–{summary['last_day'].strftime('%d.%m')})",
            "",
        ]
        total_expected = total_taken = 0
        for row in rows:
            if row["paused_until"] and not row["expected"]:
                lines.append(f"⏸ {row['name']}: перерыв до {row['paused_until'].strftime('%d.%m.%Y')}")
                continue
            parts = [f"принято {row['taken']} из {row['expected']}"]
            if row["skipped"]:
                parts.append(f"пропущено {row['skipped']}")
            if row["unmarked"]:
                parts.append(f"без отметки {row['unmarked']}")
            icon = "✅" if row["expected"] and row["taken"] == row["expected"] else "💊"
            lines.append(f"{icon} {row['name']}: " + ", ".join(parts))
            total_expected += row["expected"]
            total_taken += row["taken"]
        if total_expected:
            lines += ["", f"Итого принято {round(100 * total_taken / total_expected)}% приёмов."]
        return "\n".join(lines)
