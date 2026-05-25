"""
Reminder worker service.

Sends due reminders to users with:
- Idempotency (no duplicate notifications)
- Safe concurrent execution (multiple worker instances)
- Recurring reminders support (daily/weekly/monthly)

Architecture:
1. Worker polls database every N seconds
2. Uses SELECT ... FOR UPDATE SKIP LOCKED to atomically claim reminders
3. Sends notification via Telegram Bot API
4. Marks reminder as notified (commits transaction)
5. For recurring reminders, creates next occurrence
"""

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut

from src.config import settings
from src.db.session import async_session_maker
from src.db.models import Reminder, ReminderStatus, RepeatRule
from src.repositories.reminder_repo import (
    ReminderRepository,
    calculate_next_occurrence,
)
from src.services.medication_service import MedicationService
from src.utils.labels import repeat_rule_label

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerCycleResult:
    """Summary of one worker polling cycle."""

    total: int = 0
    processed: int = 0
    failed: int = 0


class ReminderWorkerService:
    """
    Service for processing and sending reminders.
    
    Designed for horizontal scaling:
    - Multiple workers can run simultaneously
    - Each reminder is processed exactly once (idempotency)
    - Row-level locking prevents race conditions
    """

    def __init__(
        self,
        bot: Bot,
        batch_size: int = 100,
        poll_interval: int = 60,
        session_factory=async_session_maker,
        repository_factory=ReminderRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        medication_action_checker: Callable | None = None,
    ):
        """
        Initialize worker service.
        
        Args:
            bot: Telegram bot instance for sending messages
            batch_size: Max reminders to process per iteration
            poll_interval: Seconds between polling cycles
        """
        self.bot = bot
        self.batch_size = batch_size
        self.poll_interval = poll_interval
        self.session_factory = session_factory
        self.repository_factory = repository_factory
        self.clock = clock
        self.medication_action_checker = medication_action_checker
        self._running = False

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info(
            "Reminder worker started",
            extra={
                "batch_size": self.batch_size,
                "poll_interval": self.poll_interval,
            }
        )

        while self._running:
            try:
                await self.process_cycle()
            except asyncio.CancelledError:
                logger.info("Worker received cancel signal")
                break
            except Exception as e:
                logger.exception(f"Worker cycle failed: {e}")
                # Don't fail completely, wait and retry
                await asyncio.sleep(self.poll_interval)

        logger.info("Reminder worker stopped")

    def stop(self) -> None:
        """Signal worker to stop."""
        self._running = False

    async def process_cycle(self) -> WorkerCycleResult:
        """
        One iteration of the worker loop.
        
        1. Get current UTC time
        2. Fetch due reminders with row-level locking
        3. Process each reminder (send + mark + reschedule)
        4. Commit transaction (atomic)
        """
        now = self.clock()
        
        logger.debug(
            "Starting reminder processing cycle",
            extra={"now": now.isoformat()}
        )

        async with self.session_factory() as session:
            repo = self.repository_factory(session)
            
            # Atomically claim due reminders
            # Other workers will skip these locked rows
            due_reminders = await repo.get_due_reminders_locked(
                now=now,
                limit=self.batch_size,
            )

            if not due_reminders:
                logger.debug("No due reminders found")
                return WorkerCycleResult()

            logger.info(
                f"Processing {len(due_reminders)} due reminder(s)",
                extra={"count": len(due_reminders)}
            )

            processed = 0
            failed = 0

            for reminder in due_reminders:
                try:
                    await self._process_reminder(session, repo, reminder, now)
                    processed += 1
                except Exception as e:
                    logger.exception(
                        f"Failed to process reminder {reminder.id}: {e}"
                    )
                    failed += 1
                    # Continue with next reminder, don't abort entire batch

            logger.info(
                "Reminder processing cycle completed",
                extra={
                    "processed": processed,
                    "failed": failed,
                    "total": len(due_reminders),
                }
            )

            # Commit transaction (marks reminders as notified)
            await session.commit()

            return WorkerCycleResult(
                total=len(due_reminders),
                processed=processed,
                failed=failed,
            )

    async def _process_cycle(self) -> WorkerCycleResult:
        """Backward-compatible alias for one worker cycle."""
        return await self.process_cycle()

    async def _process_reminder(
        self,
        session,
        repo: ReminderRepository,
        reminder: Reminder,
        now: datetime,
    ) -> None:
        """
        Process a single reminder.
        
        Steps:
        1. Send notification to user via Telegram
        2. Mark reminder as notified (idempotency key)
        3. If recurring, create next occurrence
        
        Args:
            session: Database session
            repo: Reminder repository
            reminder: Reminder to process
            now: Current UTC time
        """
        logger.debug(
            f"Processing reminder {reminder.id}",
            extra={
                "reminder_id": reminder.id,
                "user_id": reminder.user_id,
                "remind_at": reminder.remind_at_utc.isoformat(),
            }
        )

        if await self._should_skip_medication_notification(session, reminder, now):
            logger.info(
                "Skipping medication reminder because current intake slot is already marked",
                extra={"reminder_id": reminder.id, "medication_id": reminder.medication_id},
            )
            await repo.mark_as_notified(reminder.id, now)
            if reminder.repeat_rule != RepeatRule.NONE:
                await self._handle_recurring(session, repo, reminder, now)
            return

        # Send notification. Retryable errors bubble up so the reminder stays due.
        delivery_status = await self._send_notification(reminder)

        if delivery_status == "permanent_failure":
            await repo.mark_status(reminder.id, ReminderStatus.MISSED)
            return

        # Mark as notified (this is the idempotency guarantee)
        await repo.mark_as_notified(reminder.id, now)

        # Handle recurring reminders
        if reminder.repeat_rule != RepeatRule.NONE:
            await self._handle_recurring(
                session, repo, reminder, now
            )

    async def _should_skip_medication_notification(
        self,
        session,
        reminder: Reminder,
        now: datetime,
    ) -> bool:
        """Avoid sending a daily medication reminder for an already marked slot."""
        medication_id = getattr(reminder, "medication_id", None)
        if not medication_id or reminder.repeat_rule != RepeatRule.DAILY:
            return False

        if self.medication_action_checker:
            return bool(await self.medication_action_checker(session, reminder, now))

        service = MedicationService(session)
        state = await service.get_intake_action_state(
            medication_id=medication_id,
            user_id=reminder.user_id,
            user_timezone=self._get_user_timezone(reminder),
            now_utc=now,
        )
        return state.reason in {"slot_already_marked", "already_marked_today"}

    async def _send_notification(self, reminder: Reminder) -> str:
        """
        Send reminder notification to user via Telegram.
        
        Args:
            reminder: Reminder with user relationship loaded
        """
        if not reminder.user or not reminder.user.telegram_id:
            logger.warning(
                f"Reminder {reminder.id} has no valid user",
                extra={"reminder_id": reminder.id}
            )
            return "permanent_failure"

        chat_id = reminder.user.telegram_id
        
        # Format message
        message = self._format_reminder_message(reminder)

        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                reply_markup=self._build_reminder_reply_markup(reminder),
            )
            logger.info(
                f"Sent reminder {reminder.id} to user {reminder.user_id}",
                extra={
                    "reminder_id": reminder.id,
                    "user_id": reminder.user_id,
                    "chat_id": chat_id,
                }
            )
            return "sent"
        except (Forbidden, BadRequest) as e:
            logger.error(
                f"Permanent Telegram failure for reminder {reminder.id} to user {reminder.user_id}: {e}"
            )
            return "permanent_failure"
        except (TimedOut, NetworkError, TelegramError) as e:
            logger.warning(
                f"Retryable Telegram failure for reminder {reminder.id} to user {reminder.user_id}: {e}"
            )
            raise

    def _format_reminder_message(self, reminder: Reminder) -> str:
        """
        Format reminder message for Telegram.
        
        Args:
            reminder: Reminder instance
            
        Returns:
            Formatted message string
        """
        user_timezone = self._get_user_timezone(reminder)
        remind_time = reminder.remind_at_utc.astimezone(
            ZoneInfo(user_timezone)
        ).strftime("%d.%m.%Y %H:%M")
        
        title = reminder.title or "⏰ Напоминание"
        text = reminder.text or ""

        message = f"<b>{html.escape(title)}</b>\n\n{html.escape(text)}"

        list_id = getattr(reminder, "list_id", None)
        todo_list = getattr(reminder, "todo_list", None)
        medication_id = getattr(reminder, "medication_id", None)
        medication = getattr(reminder, "medication", None)

        if list_id:
            if todo_list:
                message += f"\n\n📋 Список: {html.escape(todo_list.title)}"
            else:
                message += "\n\n📋 Связанный список был удален"

        if medication_id:
            if medication:
                importance = getattr(medication, "importance", "normal")
                importance_prefix = {
                    "supplement": "🌿",
                    "normal": "💊",
                    "important": "❗",
                    "critical": "🚨",
                }.get(importance, "💊")
                message += f"\n\n{importance_prefix} Лекарство: {html.escape(medication.name)}"
            else:
                message += "\n\n💊 Связанное лекарство было удалено"
        
        if reminder.repeat_rule != RepeatRule.NONE:
            repeat_emoji = {
                RepeatRule.DAILY: "📅",
                RepeatRule.WEEKLY: "📆",
                RepeatRule.MONTHLY: "🗓️",
            }
            emoji = repeat_emoji.get(reminder.repeat_rule, "🔁")
            message += f"\n\n{emoji} Повтор: {repeat_rule_label(reminder.repeat_rule)}"
        
        message += f"\n\n🕒 Время: {remind_time} ({user_timezone})"
        
        return message

    def _get_user_timezone(self, reminder: Reminder) -> str:
        """Return reminder user's timezone with project default fallback."""
        timezone_name = getattr(getattr(reminder, "user", None), "timezone", None)
        if not timezone_name:
            return settings.TIMEZONE_DEFAULT
        if timezone_name == "UTC" and settings.TIMEZONE_DEFAULT != "UTC":
            return settings.TIMEZONE_DEFAULT
        return timezone_name

    def _build_reminder_reply_markup(self, reminder: Reminder):
        """Build inline actions for reminder notifications."""
        medication_id = getattr(reminder, "medication_id", None)
        medication = getattr(reminder, "medication", None)
        list_id = getattr(reminder, "list_id", None)
        todo_list = getattr(reminder, "todo_list", None)

        if medication_id and medication:
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Принял",
                        callback_data=f"med_taken:{medication_id}",
                    ),
                    InlineKeyboardButton(
                        "↩️ Отложить 15 мин",
                        callback_data=f"med_snooze:{medication_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⏭ Пропустил",
                        callback_data=f"med_skip:{medication_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "💊 Открыть лекарство",
                        callback_data=f"med_view:{medication_id}",
                    ),
                ],
            ])

        if not list_id or not todo_list:
            return None

        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📋 Открыть список",
                    callback_data=f"list_view:{list_id}",
                ),
            ],
        ])

    async def _handle_recurring(
        self,
        session,
        repo: ReminderRepository,
        reminder: Reminder,
        now: datetime,
    ) -> None:
        """
        Create next occurrence for a recurring reminder.
        
        The current reminder is marked as notified (already done).
        A new reminder is created for the next occurrence.
        
        Args:
            session: Database session
            repo: Reminder repository
            reminder: Current reminder
            now: Current UTC time
        """
        try:
            next_time = calculate_next_occurrence(
                reminder.remind_at_utc,
                reminder.repeat_rule,
                self._get_user_timezone(reminder),
            )
            
            await repo.create_next_occurrence(reminder, next_time)
            
            logger.info(
                f"Created next occurrence for reminder {reminder.id}",
                extra={
                    "reminder_id": reminder.id,
                    "next_time": next_time.isoformat(),
                    "repeat_rule": reminder.repeat_rule.value,
                }
            )
        except Exception as e:
            logger.exception(
                f"Failed to create next occurrence for reminder {reminder.id}: {e}"
            )
            # Don't fail the entire operation, just log the error
            # The current reminder is still marked as notified


async def run_worker(
    bot_token: str,
    batch_size: int = 100,
    poll_interval: int = 60,
) -> None:
    """
    Run reminder worker as a standalone task.
    
    Args:
        bot_token: Telegram bot token
        batch_size: Max reminders per cycle
        poll_interval: Seconds between cycles
    """
    from telegram import Bot
    
    bot = Bot(token=bot_token)
    
    try:
        await bot.initialize()
        
        worker = ReminderWorkerService(
            bot=bot,
            batch_size=batch_size,
            poll_interval=poll_interval,
        )
        
        await worker.start()
    finally:
        await bot.shutdown()
