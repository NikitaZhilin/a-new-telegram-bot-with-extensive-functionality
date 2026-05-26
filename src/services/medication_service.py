"""Medication service."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select

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
            reminder.status = ReminderStatus.CANCELED

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
        marked_at = await self._get_intake_in_window(
            medication_id=medication_id,
            user_id=user_id,
            start_utc=current_open,
            end_utc=next_open,
        )
        if marked_at:
            return MedicationIntakeActionState(
                can_mark=False,
                reason="slot_already_marked",
                current_slot_at_utc=current_slot,
                current_window_start_utc=current_open,
                next_available_at_utc=next_open,
                marked_at_utc=marked_at,
                has_schedule=True,
            )

        return MedicationIntakeActionState(
            can_mark=True,
            reason="slot_available",
            current_slot_at_utc=current_slot,
            current_window_start_utc=current_open,
            next_available_at_utc=next_open,
            has_schedule=True,
        )

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
        if not medication or not medication.is_active:
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

        result: list[MedicationDailySlot] = []
        for index, (scheduled_time, slot_utc, open_utc) in enumerate(occurrences):
            next_open_utc = (
                occurrences[index + 1][2]
                if index + 1 < len(occurrences)
                else (datetime.combine(local_today + timedelta(days=1), schedule[0], tzinfo=tz) - self.SLOT_OPEN_BEFORE).astimezone(timezone.utc)
            )
            intake = await self._get_intake_record_in_window(medication_id, user_id, open_utc, next_open_utc)
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
        """Create a reminder linked to a medication."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
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
                    duplicate.remind_at_utc = remind_at_utc
                    duplicate.notified_at = None
                else:
                    duplicate.status = ReminderStatus.CANCELED

            if duplicate:
                await self.db.flush()
                await self.db.refresh(duplicate)
                return duplicate

        text = f"Принять лекарство: {medication.name}"
        if medication.importance in {"important", "critical"}:
            text = f"Важное напоминание. {text}"
        if medication.dosage:
            text += f"\nДозировка: {medication.dosage}"
        if medication.instructions:
            text += f"\nКомментарий: {medication.instructions}"

        reminder_service = ReminderService(self.db)
        return await reminder_service.create_reminder(
            user_id=user_id,
            text=text,
            title="💊 Приём лекарства",
            remind_at_utc=remind_at_utc,
            repeat_rule=repeat_rule,
            medication_id=medication_id,
        )

    async def replace_daily_reminders(
        self,
        medication_id: int,
        user_id: int,
        remind_at_utcs: list[datetime],
    ) -> list[Reminder]:
        """Replace a medication's active daily schedule with the provided times."""
        medication = await self.get_medication(medication_id, user_id)
        if not medication or not medication.is_active:
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
                reminder.status = ReminderStatus.CANCELED
                continue
            existing_by_key[key] = reminder

        created_or_updated: list[Reminder] = []
        for key, reminder in existing_by_key.items():
            if key not in normalized:
                reminder.status = ReminderStatus.CANCELED
                continue
            reminder.remind_at_utc = normalized[key]
            reminder.notified_at = None
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
