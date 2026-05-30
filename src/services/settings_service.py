"""
Settings service for user preferences.
"""

import logging
from typing import Optional

import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import distinct, func, select

from src.db.models import User
from src.repositories.user_repo import UserRepository
from src.services.activity_service import ActivityService
from src.services.driver_service import DriverService

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for user settings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return await self.repo.get(user_id)

    async def set_timezone(self, user_id: int, timezone_str: str) -> Optional[User]:
        """
        Set user's timezone.
        
        Args:
            user_id: User ID
            timezone_str: Timezone string (e.g., 'Europe/Moscow')
            
        Returns:
            Updated User or None
            
        Raises:
            ValueError: If timezone is invalid
        """
        # Validate timezone
        try:
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f"Invalid timezone: {timezone_str}")
        
        user = await self.repo.get(user_id)
        if not user:
            return None
        
        user.timezone = timezone_str
        await self.db.flush()
        await self.db.refresh(user)
        
        logger.info(f"Set timezone {timezone_str} for user {user_id}")
        return user

    async def get_stats(self, user_id: int) -> dict:
        """
        Get user statistics.

        Returns dict with counts of visible user domains.
        """
        from sqlalchemy import func
        from src.db.models import (
            ChecklistRun,
            DriverDocument,
            DriverExpense,
            DriverFuelEntry,
            DriverJournalEntry,
            DriverVehicle,
            ListMember,
            Medication,
            Note,
            Reminder,
            ReminderNotification,
            ReminderNotificationStatus,
            ReminderStatus,
            TodoList,
        )

        async def count(query) -> int:
            result = await self.db.execute(query)
            return result.scalar() or 0

        owned_lists = await count(
            select(func.count(TodoList.id)).where(
                TodoList.user_id == user_id,
                TodoList.source_module == "general",
            )
        )
        shared_lists = await count(
            select(func.count(ListMember.id))
            .join(TodoList, TodoList.id == ListMember.list_id)
            .where(
                ListMember.user_id == user_id,
                TodoList.source_module == "general",
            )
        )
        notes_active = await count(
            select(func.count(Note.id)).where(
                Note.user_id == user_id,
                Note.is_archived.is_not(True),
            )
        )
        notes_archived = await count(
            select(func.count(Note.id)).where(
                Note.user_id == user_id,
                Note.is_archived.is_(True),
            )
        )

        reminders_active = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.ACTIVE,
                Reminder.source_module == "general",
            )
        )
        reminders_done = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.DONE,
                Reminder.source_module == "general",
            )
        )
        reminders_canceled = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.CANCELED,
                Reminder.source_module == "general",
            )
        )
        reminders_missed = await count(
            select(func.count(Reminder.id)).where(
                Reminder.user_id == user_id,
                Reminder.status == ReminderStatus.MISSED,
                Reminder.source_module == "general",
            )
        )
        reminder_notifications_pending = await count(
            select(func.count(ReminderNotification.id))
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .where(
                Reminder.user_id == user_id,
                Reminder.source_module == "general",
                ReminderNotification.status == ReminderNotificationStatus.PENDING,
            )
        )
        reminder_notifications_failed = await count(
            select(func.count(ReminderNotification.id))
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .where(
                Reminder.user_id == user_id,
                Reminder.source_module == "general",
                ReminderNotification.status == ReminderNotificationStatus.FAILED,
            )
        )

        medications_active = await count(
            select(func.count(Medication.id)).where(
                Medication.user_id == user_id,
                Medication.is_active.is_(True),
            )
        )
        medications_archived = await count(
            select(func.count(Medication.id)).where(
                Medication.user_id == user_id,
                Medication.is_active.is_(False),
            )
        )
        checklist_active = await count(
            select(func.count(ChecklistRun.id)).where(
                ChecklistRun.user_id == user_id,
                ChecklistRun.status == "active",
            )
        )
        checklist_completed = await count(
            select(func.count(ChecklistRun.id)).where(
                ChecklistRun.user_id == user_id,
                ChecklistRun.status == "completed",
            )
        )
        checklist_canceled = await count(
            select(func.count(ChecklistRun.id)).where(
                ChecklistRun.user_id == user_id,
                ChecklistRun.status == "canceled",
            )
        )
        driver_overview = await DriverService(self.db).get_user_overview(user_id)
        
        return {
            "lists": {
                "owned": owned_lists,
                "shared": shared_lists,
            },
            "notes": {
                "active": notes_active,
                "archived": notes_archived,
            },
            "reminders": {
                "active": reminders_active,
                "done": reminders_done,
                "canceled": reminders_canceled,
                "missed": reminders_missed,
                "pending_notifications": reminder_notifications_pending,
                "failed_notifications": reminder_notifications_failed,
            },
            "medications": {
                "active": medications_active,
                "archived": medications_archived,
            },
            "checklists": {
                "active": checklist_active,
                "completed": checklist_completed,
                "canceled": checklist_canceled,
            },
            "driver": driver_overview,
        }

    async def get_admin_activity_stats(self, current_user_id: int) -> dict:
        """Return aggregate activity for admins without exposing private content."""
        from src.db.models import (
            ChecklistRun,
            DriverDocument,
            DriverExpense,
            DriverFuelEntry,
            DriverJournalEntry,
            DriverVehicle,
            ListMember,
            Medication,
            Note,
            Reminder,
            ReminderNotification,
            ReminderNotificationStatus,
            TodoList,
        )

        async def count(query) -> int:
            result = await self.db.execute(query)
            return result.scalar() or 0

        other_user_filter = User.id != current_user_id

        total_users = await count(select(func.count(User.id)))
        other_users = await count(select(func.count(User.id)).where(other_user_filter))

        general_lists_total = await count(
            select(func.count(TodoList.id)).where(TodoList.source_module == "general")
        )
        general_lists_users = await count(
            select(func.count(distinct(TodoList.user_id))).where(
                TodoList.source_module == "general",
                TodoList.user_id != current_user_id,
            )
        )

        shared_members_total = await count(select(func.count(ListMember.id)))
        shared_members_users = await count(
            select(func.count(distinct(ListMember.user_id))).where(
                ListMember.user_id != current_user_id,
            )
        )
        notes_total = await count(select(func.count(Note.id)).where(Note.is_archived.is_not(True)))
        notes_users = await count(
            select(func.count(distinct(Note.user_id))).where(
                Note.user_id != current_user_id,
                Note.is_archived.is_not(True),
            )
        )

        reminders_total = await count(
            select(func.count(Reminder.id)).where(Reminder.source_module == "general")
        )
        reminders_users = await count(
            select(func.count(distinct(Reminder.user_id))).where(
                Reminder.source_module == "general",
                Reminder.user_id != current_user_id,
            )
        )
        reminder_notifications_pending = await count(
            select(func.count(ReminderNotification.id))
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .where(
                Reminder.source_module == "general",
                ReminderNotification.status == ReminderNotificationStatus.PENDING,
            )
        )
        reminder_notifications_failed = await count(
            select(func.count(ReminderNotification.id))
            .join(Reminder, Reminder.id == ReminderNotification.reminder_id)
            .where(
                Reminder.source_module == "general",
                ReminderNotification.status == ReminderNotificationStatus.FAILED,
            )
        )
        checklist_runs_total = await count(select(func.count(ChecklistRun.id)))
        checklist_runs_users = await count(
            select(func.count(distinct(ChecklistRun.user_id))).where(
                ChecklistRun.user_id != current_user_id,
            )
        )

        medications_total = await count(select(func.count(Medication.id)))
        medications_users = await count(
            select(func.count(distinct(Medication.user_id))).where(Medication.user_id != current_user_id)
        )

        driver_vehicles_total = await count(select(func.count(DriverVehicle.id)))
        driver_vehicles_users = await count(
            select(func.count(distinct(DriverVehicle.user_id))).where(DriverVehicle.user_id != current_user_id)
        )

        driver_fuel_total = await count(select(func.count(DriverFuelEntry.id)))
        driver_fuel_users = await count(
            select(func.count(distinct(DriverFuelEntry.user_id))).where(DriverFuelEntry.user_id != current_user_id)
        )
        driver_expenses_total = await count(select(func.count(DriverExpense.id)))
        driver_expenses_users = await count(
            select(func.count(distinct(DriverExpense.user_id))).where(DriverExpense.user_id != current_user_id)
        )
        driver_documents_total = await count(select(func.count(DriverDocument.id)))
        driver_documents_users = await count(
            select(func.count(distinct(DriverDocument.user_id))).where(DriverDocument.user_id != current_user_id)
        )
        driver_journal_total = await count(
            select(func.count(DriverJournalEntry.id)).where(DriverJournalEntry.status != "canceled")
        )
        driver_journal_users = await count(
            select(func.count(distinct(DriverJournalEntry.user_id))).where(
                DriverJournalEntry.user_id != current_user_id,
                DriverJournalEntry.status != "canceled",
            )
        )
        activity_service = ActivityService(self.db)
        activity = await activity_service.get_admin_event_summary(current_user_id)
        funnels = await activity_service.get_funnel_summary()

        return {
            "users": {
                "total": total_users,
                "other": other_users,
            },
            "lists": {
                "records": general_lists_total,
                "other_users": general_lists_users,
            },
            "shared_lists": {
                "records": shared_members_total,
                "other_users": shared_members_users,
            },
            "notes": {
                "records": notes_total,
                "other_users": notes_users,
            },
            "reminders": {
                "records": reminders_total,
                "other_users": reminders_users,
                "pending_notifications": reminder_notifications_pending,
                "failed_notifications": reminder_notifications_failed,
            },
            "checklists": {
                "records": checklist_runs_total,
                "other_users": checklist_runs_users,
            },
            "medications": {
                "records": medications_total,
                "other_users": medications_users,
            },
            "driver": {
                "vehicles": driver_vehicles_total,
                "vehicle_users": driver_vehicles_users,
                "fuel_entries": driver_fuel_total,
                "fuel_users": driver_fuel_users,
                "expenses": driver_expenses_total,
                "expense_users": driver_expenses_users,
                "documents": driver_documents_total,
                "document_users": driver_documents_users,
                "journal_entries": driver_journal_total,
                "journal_users": driver_journal_users,
            },
            "activity": activity,
            "funnels": funnels,
        }
