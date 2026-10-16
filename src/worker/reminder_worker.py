"""
Reminder worker service.

Sends due reminders to users with:
- Idempotency (no duplicate notifications)
- Safe concurrent execution (multiple worker instances)
- Recurring reminders support (daily/weekly/monthly)

Architecture:
1. Worker polls database every N seconds
2. Uses SELECT ... FOR UPDATE SKIP LOCKED to atomically claim reminders
3. Sends notification delivery via Telegram Bot API
4. Marks the delivery as sent (commits transaction)
5. On the final delivery, closes the reminder event and creates next occurrence
"""

import asyncio
import html
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut

from src.config import settings
from src.db.session import async_session_maker
from src.db.models import (
    Reminder,
    ReminderNotification,
    ReminderNotificationStatus,
    ReminderStatus,
    RepeatRule,
)
from src.repositories.reminder_repo import (
    ReminderRepository,
    calculate_next_occurrence,
    monthly_anchor_day,
    next_future_occurrence,
)
from src.services.medication_service import MedicationService
from src.utils.labels import repeat_rule_label
from src.utils.timezones import safe_timezone_name

logger = logging.getLogger(__name__)


# A delivery that keeps failing with temporary errors is given up after this
# long instead of being retried every minute forever.
RETRY_GIVE_UP_AFTER = timedelta(hours=24)


@asynccontextmanager
async def _savepoint(session):
    """Run a block in a SAVEPOINT when the session supports it.

    One failing notification then rolls back only its own changes instead of
    leaving the whole batch transaction broken (which un-marked every message
    already sent in this cycle, so they were sent again a minute later).
    """
    begin_nested = getattr(session, "begin_nested", None)
    if begin_nested is None:
        yield
        return
    async with begin_nested():
        yield


def _retry_after_seconds(error: RetryAfter) -> float:
    value = getattr(error, "retry_after", 0) or 0
    if isinstance(value, timedelta):
        return value.total_seconds()
    return float(value)


def _html_to_plain(message: str) -> str:
    """Plain-text version of a reminder message built for parse_mode=HTML."""
    return html.unescape(re.sub(r"</?[a-zA-Z][^>]*>", "", message))


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
        heartbeat=None,
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
        self.heartbeat = heartbeat
        self._running = False
        self._retry_after_seconds = 0.0
        self._last_failure_reason = None
        self._last_summary_check = None

    async def revive_dead_series(self) -> int:
        """One-time repair on start: restart series ended by a failed delivery."""
        try:
            async with self.session_factory() as session:
                repo = self.repository_factory(session)
                revive = getattr(repo, "revive_dead_series", None)
                if revive is None:
                    return 0
                count = await revive(self.clock(), settings.TIMEZONE_DEFAULT)
                await session.commit()
                if count:
                    logger.info(f"Revived {count} repeating reminder series")
                return count
        except Exception:
            logger.exception("Could not revive repeating reminder series")
            return 0

    async def resume_paused_courses(self) -> int:
        """Bring back medication courses whose break ends today and tell the user."""
        try:
            async with self.session_factory() as session:
                service = MedicationService(session)
                resumed = await service.resume_due_courses(self.clock(), settings.TIMEZONE_DEFAULT)
                if not resumed:
                    return 0
                messages = []
                for medication, user in resumed:
                    times = await service._get_daily_schedule_times(
                        medication.id, user.id, safe_timezone_name(user.timezone, settings.TIMEZONE_DEFAULT)
                    )
                    times_text = ", ".join(item.strftime("%H:%M") for item in times)
                    text = (
                        f"▶️ Сегодня снова начинается курс: {medication.name}.\n"
                        + (f"Напоминания о приёме вернулись: {times_text}." if times_text else
                           "Задайте время приёма в карточке лекарства кнопкой «Напомнить».")
                    )
                    messages.append((user.telegram_id, medication.id, text))
                await session.commit()
            for telegram_id, medication_id, text in messages:
                try:
                    await self.bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("💊 Открыть лекарство", callback_data=f"med_view:{medication_id}")]]
                        ),
                    )
                except Exception:
                    logger.warning("Could not tell the user that a course resumed", exc_info=True)
            logger.info(f"Resumed {len(messages)} medication course(s) after a break")
            return len(messages)
        except Exception:
            logger.exception("Could not resume paused medication courses")
            return 0

    WEEKLY_SUMMARY_WEEKDAY = 6  # Sunday
    WEEKLY_SUMMARY_HOUR = 19  # local time

    async def send_weekly_summaries(self) -> int:
        """Sunday 19:00 local: «medications this week» to users who take something."""
        from sqlalchemy import exists, select as sa_select

        from src.db.models import BotActivityEvent, Medication, User
        from src.services.activity_service import ActivityService

        now = self.clock()
        if self._last_summary_check and now - self._last_summary_check < timedelta(minutes=10):
            return 0
        self._last_summary_check = now
        sent = 0
        try:
            async with self.session_factory() as session:
                users = (
                    await session.execute(
                        sa_select(User).where(
                            User.weekly_med_summary.is_(True),
                            exists().where(Medication.user_id == User.id, Medication.is_active.is_(True)),
                        )
                    )
                ).scalars().all()
                for user in users:
                    tz_name = safe_timezone_name(user.timezone, settings.TIMEZONE_DEFAULT)
                    local = now.astimezone(ZoneInfo(tz_name))
                    if local.weekday() != self.WEEKLY_SUMMARY_WEEKDAY or local.hour != self.WEEKLY_SUMMARY_HOUR:
                        continue
                    year, week, _ = local.isocalendar()
                    event_name = f"weekly_med_summary:{year}-W{week:02d}"
                    already = await session.scalar(
                        sa_select(BotActivityEvent.id).where(
                            BotActivityEvent.telegram_id == user.telegram_id,
                            BotActivityEvent.event_name == event_name,
                        ).limit(1)
                    )
                    if already:
                        continue
                    service = MedicationService(session)
                    text = service.format_weekly_summary(await service.weekly_summary(user.id, tz_name, now))
                    if text:
                        try:
                            await self.bot.send_message(
                                chat_id=user.telegram_id,
                                text=text,
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("💊 Лекарства", callback_data="medications_list")],
                                    [InlineKeyboardButton("🔕 Не присылать сводку", callback_data="med_summary_off")],
                                ]),
                            )
                            sent += 1
                        except Forbidden:
                            pass
                        except Exception:
                            logger.warning("Could not send weekly medication summary", exc_info=True)
                            continue
                    await ActivityService(session).record_event(
                        event_type="system",
                        event_name=event_name,
                        domain="system",
                        user_id=user.id,
                        telegram_id=user.telegram_id,
                        source="system",
                    )
                    await session.commit()
        except Exception:
            logger.exception("Weekly medication summaries failed")
        if sent:
            logger.info(f"Sent {sent} weekly medication summaries")
        return sent

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
                await self.resume_paused_courses()
                await self.send_weekly_summaries()
                result = await self.process_cycle()
                if self.heartbeat:
                    if result.failed:
                        self.heartbeat.mark_degraded(
                            f"{result.failed} reminder(s) failed in the last worker cycle"
                        )
                    else:
                        self.heartbeat.mark_ok()
                if self._running:
                    pause = max(self.poll_interval, self._retry_after_seconds)
                    self._retry_after_seconds = 0.0
                    await asyncio.sleep(pause)
            except asyncio.CancelledError:
                logger.info("Worker received cancel signal")
                self._running = False
                break
            except Exception as e:
                logger.exception(f"Worker cycle failed: {e}")
                if self.heartbeat:
                    self.heartbeat.mark_degraded(str(e))
                # Don't fail completely, wait and retry
                if self._running:
                    await asyncio.sleep(self.poll_interval)

        logger.info("Reminder worker stopped")

    def stop(self) -> None:
        """Signal worker to stop."""
        self._running = False

    async def process_cycle(self) -> WorkerCycleResult:
        """
        One iteration of the worker loop.
        
        1. Get current UTC time
        2. Fetch due notification deliveries with row-level locking
        3. Process each delivery (send + mark + reschedule on final delivery)
        4. Commit transaction (atomic)
        """
        now = self.clock()
        
        logger.debug(
            "Starting reminder processing cycle",
            extra={"now": now.isoformat()}
        )

        async with self.session_factory() as session:
            repo = self.repository_factory(session)
            
            # Atomically claim due notification deliveries
            # Other workers will skip these locked rows
            due_notifications = await repo.get_due_notifications_locked(
                now=now,
                limit=self.batch_size,
            )

            if not due_notifications:
                logger.debug("No due reminder notifications found")
                return WorkerCycleResult()

            logger.info(
                f"Processing {len(due_notifications)} due reminder notification(s)",
                extra={"count": len(due_notifications)}
            )

            processed = 0
            failed = 0

            for notification in due_notifications:
                try:
                    async with _savepoint(session):
                        await self._process_notification(session, repo, notification, now)
                    processed += 1
                except RetryAfter as e:
                    # Telegram asked us to slow down: stop this batch and wait.
                    self._retry_after_seconds = _retry_after_seconds(e)
                    await self._record_failure(session, repo, notification, now, str(e))
                    logger.warning(
                        f"Telegram flood control, pausing {self._retry_after_seconds:.0f}s"
                    )
                    failed += 1
                    break
                except Exception as e:
                    await self._record_failure(session, repo, notification, now, str(e))
                    logger.exception(
                        f"Failed to process reminder notification {notification.id}: {e}"
                    )
                    failed += 1
                    # Continue with next reminder, don't abort entire batch

            logger.info(
                "Reminder processing cycle completed",
                extra={
                    "processed": processed,
                    "failed": failed,
                    "total": len(due_notifications),
                }
            )

            # Commit transaction (marks reminders as notified)
            await session.commit()

            return WorkerCycleResult(
                total=len(due_notifications),
                processed=processed,
                failed=failed,
            )

    async def _record_failure(self, session, repo, notification, now: datetime, error: str) -> None:
        """Keep a retryable delivery pending, or give up after RETRY_GIVE_UP_AFTER."""
        notify_at = notification.notify_at_utc
        if notify_at.tzinfo is None:
            notify_at = notify_at.replace(tzinfo=timezone.utc)
        try:
            async with _savepoint(session):
                if now - notify_at > RETRY_GIVE_UP_AFTER:
                    await repo.mark_notification_failed(
                        notification.id,
                        f"Gave up after {RETRY_GIVE_UP_AFTER}: {error}",
                    )
                else:
                    await repo.remember_notification_error(notification.id, error)
        except Exception:
            logger.exception(f"Could not record failure for notification {notification.id}")

    async def _process_cycle(self) -> WorkerCycleResult:
        """Backward-compatible alias for one worker cycle."""
        return await self.process_cycle()

    async def _process_notification(
        self,
        session,
        repo: ReminderRepository,
        notification: ReminderNotification,
        now: datetime,
    ) -> None:
        """
        Process a single reminder notification delivery.
        
        Steps:
        1. Send notification to user via Telegram
        2. Mark notification as sent (idempotency key)
        3. If this is the final delivery, close/reschedule the reminder
        
        Args:
            session: Database session
            repo: Reminder repository
            notification: ReminderNotification to process
            now: Current UTC time
        """
        reminder = notification.reminder
        if reminder is None:
            await repo.mark_notification_failed(notification.id, "Reminder was not loaded")
            return

        logger.debug(
            f"Processing reminder notification {notification.id}",
            extra={
                "notification_id": notification.id,
                "reminder_id": reminder.id,
                "user_id": reminder.user_id,
                "remind_at": reminder.remind_at_utc.isoformat(),
                "notify_at": notification.notify_at_utc.isoformat(),
                "offset_minutes": notification.offset_minutes,
            }
        )

        if await self._should_skip_medication_notification(session, reminder, now):
            logger.info(
                "Skipping medication reminder because current intake slot is already marked",
                extra={"reminder_id": reminder.id, "medication_id": reminder.medication_id},
            )
            await repo.mark_notification_canceled(
                notification.id,
                now,
                "Medication intake slot is already marked",
            )
            await repo.cancel_pending_notifications(
                reminder.id,
                "Medication intake slot is already marked",
            )
            await repo.mark_as_notified(reminder.id, now)
            if reminder.repeat_rule != RepeatRule.NONE:
                await self._handle_recurring(session, repo, reminder, now)
            return

        # Send notification. Retryable errors bubble up so the notification stays due.
        delivery_status = await self._send_notification(reminder)

        if delivery_status == "permanent_failure":
            reason = getattr(self, "_last_failure_reason", None) or "Permanent Telegram delivery failure"
            await repo.mark_notification_failed(notification.id, reason)
            await repo.cancel_pending_notifications(reminder.id, reason)
            await repo.mark_status(reminder.id, ReminderStatus.MISSED)
            if reminder.repeat_rule != RepeatRule.NONE:
                # One failed delivery used to end a daily/weekly series for good
                # (a medication schedule silently stopped). Keep the schedule.
                await self._handle_recurring(session, repo, reminder, now)
            return

        # Mark delivery as sent (this is the idempotency guarantee).
        await repo.mark_notification_sent(notification.id, now)

        if self._is_final_notification(notification, reminder):
            await repo.mark_as_notified(reminder.id, now)
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
        if not medication_id:
            return False

        if self.medication_action_checker:
            return bool(await self.medication_action_checker(session, reminder, now))

        service = MedicationService(session)
        user_timezone = self._get_user_timezone(reminder)
        if reminder.repeat_rule == RepeatRule.DAILY:
            # Check the slot this reminder is for, not whatever slot is current:
            # an early notice or a late "Taken" must not cancel the wrong dose.
            slot_state = await service.get_slot_action_state(
                medication_id=medication_id,
                user_id=reminder.user_id,
                user_timezone=user_timezone,
                slot_utc=reminder.remind_at_utc,
                now_utc=max(now, reminder.remind_at_utc),
            )
            if slot_state is not None:
                return slot_state.reason == "slot_already_marked"
        elif reminder.repeat_rule != RepeatRule.NONE:
            return False

        # One-time medication reminders ("snooze 15 min") and fallbacks: skip
        # when the current intake slot has already been marked.
        state = await service.get_intake_action_state(
            medication_id=medication_id,
            user_id=reminder.user_id,
            user_timezone=user_timezone,
            now_utc=now,
        )
        return state.reason in {"slot_already_marked", "already_marked_today"}

    @staticmethod
    def _is_final_notification(
        notification: ReminderNotification,
        reminder: Reminder,
    ) -> bool:
        """Return whether this delivery is the last active delivery for the event."""
        notify_at = notification.notify_at_utc
        if notify_at.tzinfo is None:
            notify_at = notify_at.replace(tzinfo=timezone.utc)

        for item in getattr(reminder, "notifications", []) or []:
            if item.id == notification.id:
                continue
            status = item.status.value if hasattr(item.status, "value") else item.status
            if status != ReminderNotificationStatus.PENDING.value:
                continue

            item_notify_at = item.notify_at_utc
            if item_notify_at.tzinfo is None:
                item_notify_at = item_notify_at.replace(tzinfo=timezone.utc)
            if item_notify_at > notify_at:
                return False

        return True

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
        self._last_failure_reason = None

        # Format message
        message = self._format_reminder_message(reminder)

        try:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=self._build_reminder_reply_markup(reminder),
                )
            except BadRequest as first_error:
                if "chat not found" in str(first_error).lower():
                    raise
                # Formatting or button problems must not cost the user the
                # reminder: retry once as plain text without buttons.
                logger.warning(f"Retrying reminder {reminder.id} as plain text after: {first_error}")
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=_html_to_plain(message),
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
            # A user who blocked the bot is not a bug: warning, not the error journal.
            log = logger.warning if isinstance(e, Forbidden) else logger.error
            log(
                f"Permanent Telegram failure for reminder {reminder.id} to user {reminder.user_id}: {e}"
            )
            # Keep the real reason (blocked by user, chat not found, …): the
            # generic text made failures impossible to diagnose.
            self._last_failure_reason = f"{type(e).__name__}: {e}"[:500]
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
        note_id = getattr(reminder, "note_id", None)
        note = getattr(reminder, "note", None)
        medication_id = getattr(reminder, "medication_id", None)
        medication = getattr(reminder, "medication", None)
        driver_document_id = getattr(reminder, "driver_document_id", None)
        driver_document = getattr(reminder, "driver_document", None)

        if list_id:
            if todo_list:
                message += f"\n\n📋 Список: {html.escape(todo_list.title)}"
            else:
                message += "\n\n📋 Связанный список был удален"

        if note_id:
            if note:
                message += f"\n\n📝 Заметка: {html.escape(note.title)}"
            else:
                message += "\n\n📝 Связанная заметка была удалена"

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

        if driver_document_id:
            if driver_document:
                message += f"\n\n📄 Документ: {html.escape(driver_document.title)}"
            else:
                message += "\n\n📄 Связанный документ был удален"
        
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

    @staticmethod
    def _monthly_anchor_day(reminder: Reminder, user_timezone: str) -> int | None:
        """Day of month a monthly reminder belongs to; remembered on the reminder."""
        return monthly_anchor_day(reminder, user_timezone)

    def _get_user_timezone(self, reminder: Reminder) -> str:
        """Return reminder user's timezone with project default fallback."""
        timezone_name = getattr(getattr(reminder, "user", None), "timezone", None)
        if not timezone_name:
            return safe_timezone_name(settings.TIMEZONE_DEFAULT, "UTC")
        if timezone_name == "UTC" and settings.TIMEZONE_DEFAULT != "UTC":
            return safe_timezone_name(settings.TIMEZONE_DEFAULT, "UTC")
        # A hand-typed name like "europe/moscow" used to raise here on every
        # cycle, so the reminder stayed pending forever and never arrived.
        return safe_timezone_name(timezone_name, settings.TIMEZONE_DEFAULT)

    def _build_reminder_reply_markup(self, reminder: Reminder):
        """Build inline actions for reminder notifications."""
        medication_id = getattr(reminder, "medication_id", None)
        medication = getattr(reminder, "medication", None)
        list_id = getattr(reminder, "list_id", None)
        todo_list = getattr(reminder, "todo_list", None)
        note_id = getattr(reminder, "note_id", None)
        note = getattr(reminder, "note", None)
        driver_document_id = getattr(reminder, "driver_document_id", None)
        driver_document = getattr(reminder, "driver_document", None)

        if medication_id and medication:
            # Daily reminders carry their slot so a late press marks this dose,
            # not the next one.
            slot_suffix = ""
            if reminder.repeat_rule == RepeatRule.DAILY and reminder.remind_at_utc is not None:
                remind_at = reminder.remind_at_utc
                if remind_at.tzinfo is None:
                    remind_at = remind_at.replace(tzinfo=timezone.utc)
                slot_suffix = f":{int(remind_at.timestamp())}"
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Принял",
                        callback_data=f"med_taken:{medication_id}{slot_suffix}",
                    ),
                    InlineKeyboardButton(
                        "↩️ Отложить 15 мин",
                        callback_data=f"med_snooze:{medication_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⏭ Пропустил",
                        callback_data=f"med_skip:{medication_id}{slot_suffix}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "💊 Открыть лекарство",
                        callback_data=f"med_view:{medication_id}",
                    ),
                ],
            ])

        if driver_document_id and driver_document:
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📄 Открыть документ",
                        callback_data=f"driver_document_view:{driver_document_id}",
                    ),
                ],
            ])

        if note_id and note:
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📝 Открыть заметку",
                        callback_data=f"note_view:{note_id}",
                    ),
                ],
                *self._reminder_action_rows(reminder),
            ])

        actions = self._reminder_action_rows(reminder)
        if not list_id or not todo_list:
            return InlineKeyboardMarkup(actions)

        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📋 Открыть список",
                    callback_data=f"list_view:{list_id}",
                ),
                InlineKeyboardButton(
                    "▶️ Чек-лист",
                    callback_data=f"checklist_start:{list_id}",
                ),
            ],
            *actions,
        ])

    @staticmethod
    def _reminder_action_rows(reminder: Reminder) -> list:
        """«Сделано» and «Отложить» for ordinary reminders (before: no buttons at all)."""
        reminder_id = reminder.id
        return [
            [InlineKeyboardButton("✅ Сделано", callback_data=f"rem_ack:{reminder_id}")],
            [
                InlineKeyboardButton("⏰ 15 мин", callback_data=f"rem_snooze:{reminder_id}:15"),
                InlineKeyboardButton("⏰ 1 час", callback_data=f"rem_snooze:{reminder_id}:60"),
                InlineKeyboardButton("📅 Завтра", callback_data=f"rem_snooze:{reminder_id}:1440"),
            ],
        ]

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
            async with _savepoint(session):
                user_timezone = self._get_user_timezone(reminder)
                day_of_month = self._monthly_anchor_day(reminder, user_timezone)
                # After downtime, jump straight to the first future occurrence
                # instead of sending every missed repeat one per minute.
                next_time = next_future_occurrence(
                    reminder.remind_at_utc,
                    reminder.repeat_rule,
                    user_timezone,
                    now,
                    day_of_month=day_of_month,
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
    from src.services.service_heartbeat import ServiceHeartbeatWriter
    
    bot = Bot(token=bot_token)
    
    heartbeat_task = None
    try:
        await bot.initialize()
        heartbeat = ServiceHeartbeatWriter(
            "worker",
            metadata_factory=lambda: {
                "batch_size": batch_size,
                "poll_interval": poll_interval,
                "telegram_bot_initialized": True,
            },
        )
        heartbeat_task = asyncio.create_task(heartbeat.run(), name="heartbeat-worker")
        
        worker = ReminderWorkerService(
            bot=bot,
            batch_size=batch_size,
            poll_interval=poll_interval,
            heartbeat=heartbeat,
        )
        
        await worker.revive_dead_series()
        await worker.start()
    finally:
        if heartbeat_task:
            heartbeat.stop()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        await bot.shutdown()
