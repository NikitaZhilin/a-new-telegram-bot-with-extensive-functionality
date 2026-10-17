"""Morning «plan for today»: today's reminders and medication times in one message."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Medication, Reminder, ReminderStatus, User
from src.services.medication_service import MedicationService

DIGEST_HOUR = 8  # local time
MAX_LINES = 25


async def build_daily_plan(
    session: AsyncSession, user: User, user_timezone: str, now_utc: Optional[datetime] = None
) -> Optional[str]:
    """Text of the plan for the user's local today, or None when there is nothing planned."""
    now_utc = now_utc or datetime.now(timezone.utc)
    tz = ZoneInfo(user_timezone)
    today = now_utc.astimezone(tz).date()
    start = datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = start + timedelta(days=1)

    reminders = (
        await session.execute(
            select(Reminder)
            .where(
                and_(
                    Reminder.user_id == user.id,
                    Reminder.status == ReminderStatus.ACTIVE,
                    Reminder.medication_id.is_(None),
                    Reminder.remind_at_utc >= start,
                    Reminder.remind_at_utc < end,
                )
            )
            .order_by(Reminder.remind_at_utc)
        )
    ).scalars().all()

    medications = (
        await session.execute(
            select(Medication)
            .where(and_(Medication.user_id == user.id, Medication.is_active.is_(True)))
            .order_by(Medication.name)
        )
    ).scalars().all()
    service = MedicationService(session)
    med_lines = []
    for medication in medications:
        if service.is_paused(medication):
            continue
        times = await service._get_daily_schedule_times(medication.id, user.id, user_timezone)
        if times:
            med_lines.append(f"💊 {medication.name} — " + ", ".join(t.strftime("%H:%M") for t in times))

    if not reminders and not med_lines:
        return None

    lines = [f"🌅 План на сегодня, {today.strftime('%d.%m')}", ""]
    if reminders:
        lines.append("⏰ Напоминания:")
        for reminder in reminders[:MAX_LINES]:
            at = reminder.remind_at_utc
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            label = (reminder.text or reminder.title or "Напоминание").split("\n", 1)[0][:80]
            lines.append(f"• {at.astimezone(tz).strftime('%H:%M')} {label}")
        if len(reminders) > MAX_LINES:
            lines.append(f"• …и ещё {len(reminders) - MAX_LINES}")
    if med_lines:
        if reminders:
            lines.append("")
        lines.append("Лекарства:")
        lines.extend(med_lines[:MAX_LINES])
    return "\n".join(lines)
