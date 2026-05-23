"""
Reminders handlers.

Creation with date/time selection (presets + inline calendar + custom time).
View, edit, toggle status, repeat settings.
"""

import logging
import re
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.keyboards import (
    get_reminders_list_keyboard,
    get_reminder_view_keyboard,
    get_reminder_date_keyboard,
    get_reminder_time_keyboard,
    get_reminder_confirm_keyboard,
    get_reminder_repeat_keyboard,
    get_back_home_inline_keyboard,
    get_cancel_keyboard,
    get_cancel_inline_keyboard,
)
from src.bot.states import ReminderStates
from src.config import settings
from src.db.session import async_session_maker
from src.services.list_service import ListService
from src.services.reminder_service import ReminderService
from src.repositories.user_repo import UserRepository
from src.db.models import RepeatRule
from src.utils.date_parser import parse_datetime

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 20


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID, creating the user for direct deep-link flows."""
    user_repo = UserRepository(session)
    telegram_user = update.effective_user
    user = await user_repo.get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )
    await session.commit()
    return user.id


async def _get_user_timezone(update: Update, session) -> str:
    """Return user's timezone or the configured default."""
    user_repo = UserRepository(session)
    telegram_user = update.effective_user
    user = await user_repo.get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )
    if not user or not user.timezone:
        await session.commit()
        return settings.TIMEZONE_DEFAULT
    if user.timezone == "UTC" and settings.TIMEZONE_DEFAULT != "UTC":
        user.timezone = settings.TIMEZONE_DEFAULT
        await session.commit()
        return settings.TIMEZONE_DEFAULT
    await session.commit()
    return user.timezone


def _context_timezone(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Get timezone remembered for the current reminder flow."""
    return context.user_data.get("user_timezone", settings.TIMEZONE_DEFAULT)


def _selected_date(context: ContextTypes.DEFAULT_TYPE, tz_name: str) -> date:
    """Get selected local date for time-only input."""
    selected = context.user_data.get("selected_date")
    if selected:
        return datetime.fromisoformat(selected).date()
    return datetime.now(ZoneInfo(tz_name)).date()


def _parse_time_on_date(value: str, selected_date: date, tz_name: str) -> datetime:
    """Parse a compact time input and return UTC datetime."""
    raw = value.strip().lower().replace(".", ":").replace(",", ":")
    raw = re.sub(r"\s+", " ", raw)

    match = re.fullmatch(r"(\d{1,2})(?::(\d{1,2}))?", raw)
    spaced_match = re.fullmatch(r"(\d{1,2})\s+(\d{1,2})", raw)
    if not match and re.fullmatch(r"\d{3,4}", raw):
        hour = int(raw[:-2])
        minute = int(raw[-2:])
    elif spaced_match:
        hour = int(spaced_match.group(1))
        minute = int(spaced_match.group(2))
    elif match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
    else:
        raise ValueError(f"Invalid time: {value}")

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid time: {value}")

    local_dt = datetime(
        selected_date.year,
        selected_date.month,
        selected_date.day,
        hour,
        minute,
        tzinfo=ZoneInfo(tz_name),
    )
    return local_dt.astimezone(timezone.utc)


def _parse_flexible_datetime(value: str, context: ContextTypes.DEFAULT_TYPE) -> datetime:
    """Parse reminder time from natural text or compact time input."""
    tz_name = _context_timezone(context)
    selected_date = _selected_date(context, tz_name)

    try:
        return _parse_time_on_date(value, selected_date, tz_name)
    except ValueError:
        parsed = parse_datetime(value, tz_name)
        return parsed.astimezone(timezone.utc)


def _parse_date_only(value: str, context: ContextTypes.DEFAULT_TYPE) -> date:
    """Parse a date without requiring a year."""
    tz_name = _context_timezone(context)
    raw = value.strip()
    today = datetime.now(ZoneInfo(tz_name)).date()

    match = re.fullmatch(r"(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{2,4}))?", raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        parsed_date = date(year, month, day)
        if parsed_date < today and not match.group(3):
            parsed_date = date(year + 1, month, day)
        return parsed_date

    return parse_datetime(raw, tz_name).date()


def _looks_like_full_datetime(value: str) -> bool:
    """Detect inputs that include both date intent and time intent."""
    raw = value.strip().lower()
    if "через" in raw:
        return True
    if any(word in raw for word in ("сегодня", "завтра", "послезавтра")) and re.search(r"\d", raw):
        return True
    if re.search(r"\d{1,2}[.\-/]\d{1,2}(?:[.\-/]\d{2,4})?\s+\d{1,2}", raw):
        return True
    if re.search(r"\d{1,2}:\d{1,2}", raw):
        return True
    return False


def _format_remind_at(context: ContextTypes.DEFAULT_TYPE, remind_at_utc: datetime) -> str:
    """Format reminder time in the user's timezone."""
    tz_name = _context_timezone(context)
    local_dt = remind_at_utc.astimezone(ZoneInfo(tz_name))
    return f"{local_dt.strftime('%d.%m.%Y %H:%M')} ({tz_name})"


async def reminders_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show reminders list."""
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    context.user_data.setdefault("reminders_filter_active", True)
    show_active = context.user_data["reminders_filter_active"]
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        reminders, total = await reminder_service.get_reminders_list(
            user_id=user.id if user else user_id,
            active=show_active,
            page=0,
            page_size=ITEMS_PER_PAGE,
        )
    
    if not reminders:
        filter_text = "активных" if show_active else "завершенных"
        text = f"⏰ Напоминания\n\nНет {filter_text} напоминаний."
    else:
        filter_text = "активных" if show_active else "завершенных"
        text = f"⏰ Напоминания ({total} {filter_text})\n\n"
    
    keyboard = get_reminders_list_keyboard(
        reminders,
        page=0,
        has_next=total > ITEMS_PER_PAGE,
        show_active=show_active,
    )
    
    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    
    return ConversationHandler.END


async def reminders_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show selected reminders page."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.split(":", 1)[1])
    page = max(page, 0)
    show_active = context.user_data.get("reminders_filter_active", True)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        reminders, total = await reminder_service.get_reminders_list(
            user_id=user_id,
            active=show_active,
            page=page,
            page_size=ITEMS_PER_PAGE,
        )

    if not reminders and page > 0:
        page -= 1
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            reminder_service = ReminderService(session)
            reminders, total = await reminder_service.get_reminders_list(
                user_id=user_id,
                active=show_active,
                page=page,
                page_size=ITEMS_PER_PAGE,
            )

    filter_text = "активные" if show_active else "завершенные"
    if not reminders:
        text = f"⏰ Напоминания\n\nНет напоминаний: {filter_text}."
    else:
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        text = f"⏰ Напоминания ({total}, {filter_text})\nСтраница {page + 1}/{total_pages}"

    keyboard = get_reminders_list_keyboard(
        reminders,
        page=page,
        has_next=(page + 1) * ITEMS_PER_PAGE < total,
        show_active=show_active,
    )
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def reminder_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start reminder creation."""
    query = update.callback_query

    if query and query.data.startswith("list_remind:"):
        await query.answer()
        list_id = int(query.data.split(":", 1)[1])

        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            context.user_data["user_timezone"] = await _get_user_timezone(update, session)
            list_service = ListService(session)
            list_obj = await list_service.get_list(list_id, user_id)

        if not list_obj:
            await query.edit_message_text(
                "❌ Список не найден",
                reply_markup=get_back_home_inline_keyboard(),
            )
            return ConversationHandler.END

        context.user_data["linked_list_id"] = list_id
        context.user_data["linked_list_title"] = list_obj.title
        context.user_data["reminder_text"] = f"Напомнить про список: {list_obj.title}"

        await query.edit_message_text(
            f"⏰ Напоминание о списке\n\n📋 {list_obj.title}\n\nКогда напомнить?",
            reply_markup=get_reminder_date_keyboard(),
        )
        return ReminderStates.WAIT_DATE

    context.user_data.pop("linked_list_id", None)
    context.user_data.pop("linked_list_title", None)

    async with async_session_maker() as session:
        context.user_data["user_timezone"] = await _get_user_timezone(update, session)

    if query:
        await query.answer()
        await query.edit_message_text(
            "⏰ Создание напоминания\n\nВведите текст напоминания:",
            reply_markup=get_cancel_inline_keyboard(),
        )
    else:
        await update.message.reply_text(
            "⏰ Создание напоминания\n\nВведите текст напоминания:",
            reply_markup=get_cancel_keyboard(),
        )
    
    return ReminderStates.WAIT_TEXT


async def reminder_save_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save reminder text and show date selection."""
    text = update.message.text.strip()
    context.user_data["reminder_text"] = text
    
    await update.message.reply_text(
        f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        f"Когда напомнить?",
        reply_markup=get_reminder_date_keyboard(),
    )
    
    return ReminderStates.WAIT_DATE


async def reminder_date_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select today's date."""
    query = update.callback_query
    await query.answer()
    
    now = datetime.now(ZoneInfo(_context_timezone(context)))
    context.user_data["selected_date"] = now.date().isoformat()
    
    await query.edit_message_text(
        "📅 Сегодня\n\nВыберите время:",
        reply_markup=get_reminder_time_keyboard(),
    )
    
    return ReminderStates.WAIT_TIME


async def reminder_date_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select tomorrow's date."""
    query = update.callback_query
    await query.answer()
    
    tomorrow = datetime.now(ZoneInfo(_context_timezone(context))).date() + timedelta(days=1)
    context.user_data["selected_date"] = tomorrow.isoformat()
    
    await query.edit_message_text(
        "📅 Завтра\n\nВыберите время:",
        reply_markup=get_reminder_time_keyboard(),
    )
    
    return ReminderStates.WAIT_TIME


async def reminder_date_after_tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select the day after tomorrow."""
    query = update.callback_query
    await query.answer()

    selected_date = datetime.now(ZoneInfo(_context_timezone(context))).date() + timedelta(days=2)
    context.user_data["selected_date"] = selected_date.isoformat()

    await query.edit_message_text(
        "📅 Послезавтра\n\nВыберите время:",
        reply_markup=get_reminder_time_keyboard(),
    )

    return ReminderStates.WAIT_TIME


async def reminder_date_next_week(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Select the same weekday next week."""
    query = update.callback_query
    await query.answer()

    selected_date = datetime.now(ZoneInfo(_context_timezone(context))).date() + timedelta(days=7)
    context.user_data["selected_date"] = selected_date.isoformat()

    await query.edit_message_text(
        "📆 Через неделю\n\nВыберите время:",
        reply_markup=get_reminder_time_keyboard(),
    )

    return ReminderStates.WAIT_TIME


async def reminder_date_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Custom date selection."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📆 Введите дату или фразу\n\n"
        "Примеры:\n"
        "25.12.2026\n"
        "25.12\n"
        "завтра 10\n"
        "через 2 часа",
        reply_markup=get_cancel_inline_keyboard(),
    )
    
    return ReminderStates.WAIT_DATE


async def reminder_save_custom_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save custom date."""
    date_str = update.message.text.strip()
    
    try:
        if _looks_like_full_datetime(date_str):
            remind_at = _parse_flexible_datetime(date_str, context)
            context.user_data["remind_at_utc"] = remind_at.isoformat()
            await update.message.reply_text(
                _build_confirmation_text(context, remind_at),
                reply_markup=get_reminder_confirm_keyboard(remind_at),
            )
            return ReminderStates.WAIT_CONFIRM

        selected_date = _parse_date_only(date_str, context)
        context.user_data["selected_date"] = selected_date.isoformat()
        
        await update.message.reply_text(
            f"📅 Выбрано: {selected_date.strftime('%d.%m.%Y')}\n\nТеперь выберите время:",
            reply_markup=get_reminder_time_keyboard(),
        )
        
        return ReminderStates.WAIT_TIME
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Не понял дату. Попробуйте так: 25.12, завтра 10, через 2 часа",
            reply_markup=get_cancel_keyboard(),
        )
        return ReminderStates.WAIT_DATE


async def reminder_time_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle time preset selection."""
    query = update.callback_query
    await query.answer()
    
    preset = query.data.removeprefix("rem_time_")
    now = datetime.now(timezone.utc)

    if preset.startswith("clock_"):
        hhmm = preset.removeprefix("clock_")
        selected_date = _selected_date(context, _context_timezone(context))
        remind_at = _parse_time_on_date(
            f"{hhmm[:2]}:{hhmm[2:]}",
            selected_date,
            _context_timezone(context),
        )
    elif preset == "10min":
        remind_at = now + timedelta(minutes=10)
    elif preset == "30min":
        remind_at = now + timedelta(minutes=30)
    elif preset == "1hour":
        remind_at = now + timedelta(hours=1)
    elif preset == "2hour":
        remind_at = now + timedelta(hours=2)
    else:
        remind_at = now + timedelta(hours=1)
    
    context.user_data["remind_at_utc"] = remind_at.isoformat()
    
    await show_confirmation(query, context, remind_at)
    
    return ReminderStates.WAIT_CONFIRM


async def reminder_time_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return from time selection to date selection."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Когда напомнить?",
        reply_markup=get_reminder_date_keyboard(),
    )

    return ReminderStates.WAIT_DATE


async def reminder_time_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Custom time selection."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🕒 Введите время или фразу\n\n"
        "Примеры:\n"
        "10\n"
        "10:30\n"
        "завтра 10\n"
        "через 2 часа",
        reply_markup=get_cancel_inline_keyboard(),
    )
    
    return ReminderStates.WAIT_TIME_CUSTOM


async def reminder_save_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save custom time."""
    time_str = update.message.text.strip()
    
    try:
        remind_at = _parse_flexible_datetime(time_str, context)
        context.user_data["remind_at_utc"] = remind_at.isoformat()
        
        await update.message.reply_text(
            _build_confirmation_text(context, remind_at, prefix=f"🕒 Выбрано: {time_str}\n\n"),
            reply_markup=get_reminder_confirm_keyboard(remind_at),
        )
        
        return ReminderStates.WAIT_CONFIRM
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Не понял время. Попробуйте так: 10, 10:30, завтра 10, через 2 часа",
            reply_markup=get_cancel_keyboard(),
        )
        return ReminderStates.WAIT_TIME_CUSTOM


def _build_confirmation_text(
    context: ContextTypes.DEFAULT_TYPE,
    remind_at: datetime,
    prefix: str = "",
) -> str:
    """Build confirmation text, including linked list context when present."""
    linked_list_title = context.user_data.get("linked_list_title")
    list_line = f"📋 Список: {linked_list_title}\n" if linked_list_title else ""
    return (
        f"{prefix}"
        f"⏰ Подтверждение\n\n"
        f"{list_line}"
        f"Когда: {_format_remind_at(context, remind_at)}\n\n"
        f"Подтвердить создание?"
    )


async def show_confirmation(query, context: ContextTypes.DEFAULT_TYPE, remind_at: datetime) -> None:
    """Show confirmation screen."""
    text = _build_confirmation_text(context, remind_at)
    
    await query.edit_message_text(
        text,
        reply_markup=get_reminder_confirm_keyboard(remind_at),
    )


async def reminder_confirm_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm and create reminder."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    text = context.user_data.get("reminder_text", "")
    remind_at_str = context.user_data.get("remind_at_utc")
    repeat_rule = context.user_data.get("repeat_rule", RepeatRule.NONE)
    linked_list_id = context.user_data.get("linked_list_id")
    
    if not remind_at_str:
        await query.edit_message_text("❌ Ошибка: не указано время")
        return ConversationHandler.END
    
    remind_at_utc = datetime.fromisoformat(remind_at_str)
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        reminder = await reminder_service.create_reminder(
            user_id=user.id if user else user_id,
            text=text,
            remind_at_utc=remind_at_utc,
            repeat_rule=repeat_rule,
            list_id=linked_list_id,
        )
        if reminder is None:
            await session.rollback()
            await query.edit_message_text(
                "❌ Не удалось создать напоминание: список не найден",
                reply_markup=get_back_home_inline_keyboard(),
            )
            context.user_data.clear()
            return ConversationHandler.END
        await session.commit()
    
    await query.edit_message_text(
        f"✅ Напоминание создано!\n\n"
        f"📝 {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        f"⏰ {_format_remind_at(context, remind_at_utc)}",
        reply_markup=get_reminder_view_keyboard(reminder.id),
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def reminder_cancel_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel reminder creation."""
    query = update.callback_query
    await query.answer("Отменено")
    
    await query.edit_message_text(
        "❌ Создание отменено",
        reply_markup=get_back_home_inline_keyboard(),
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def reminder_repeat_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set repeat rule."""
    query = update.callback_query
    await query.answer()
    
    current = context.user_data.get("repeat_rule", RepeatRule.NONE)
    
    await query.edit_message_text(
        "🔁 Повтор напоминания\n\nВыберите правило:",
        reply_markup=get_reminder_repeat_keyboard(current.value if hasattr(current, 'value') else current),
    )
    
    return ReminderStates.WAIT_REPEAT


async def reminder_back_to_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return from repeat settings to confirmation."""
    query = update.callback_query
    await query.answer()

    remind_at_str = context.user_data.get("remind_at_utc")
    remind_at = datetime.fromisoformat(remind_at_str) if remind_at_str else datetime.now(timezone.utc)

    await query.edit_message_text(
        _build_confirmation_text(context, remind_at),
        reply_markup=get_reminder_confirm_keyboard(remind_at),
    )

    return ReminderStates.WAIT_CONFIRM


async def reminder_save_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save repeat rule."""
    query = update.callback_query
    await query.answer()
    
    rule_map = {
        "rem_repeat_none": RepeatRule.NONE,
        "rem_repeat_daily": RepeatRule.DAILY,
        "rem_repeat_weekly": RepeatRule.WEEKLY,
        "rem_repeat_monthly": RepeatRule.MONTHLY,
    }
    
    selected = query.data
    repeat_rule = rule_map.get(selected, RepeatRule.NONE)
    context.user_data["repeat_rule"] = repeat_rule
    
    remind_at_str = context.user_data.get("remind_at_utc")
    remind_at = datetime.fromisoformat(remind_at_str) if remind_at_str else datetime.now(timezone.utc)
    
    await query.edit_message_text(
        _build_confirmation_text(context, remind_at, prefix=f"🔁 Повтор: {repeat_rule.value}\n\n"),
        reply_markup=get_reminder_confirm_keyboard(remind_at, repeat_rule.value),
    )
    
    return ReminderStates.WAIT_CONFIRM


async def reminder_change_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return from confirmation to time selection."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Выберите новое время:",
        reply_markup=get_reminder_time_keyboard(),
    )

    return ReminderStates.WAIT_TIME


async def reminder_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View reminder details."""
    query = update.callback_query
    await query.answer()
    
    reminder_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        reminder = await reminder_service.get_reminder(reminder_id, user.id if user else user_id)
    
    if not reminder:
        await query.edit_message_text("❌ Напоминание не найдено")
        return ConversationHandler.END
    
    time_str = reminder.remind_at_utc.strftime("%d.%m.%Y %H:%M")
    
    text = (
        f"⏰ Напоминание #{reminder.id}\n\n"
        f"{reminder.text}\n\n"
        f"📅 Запланировано: {time_str} UTC\n"
        f"🔁 Повтор: {reminder.repeat_rule.value}\n"
        f"⏰ Статус: {reminder.status.value}"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=get_reminder_view_keyboard(reminder.id, reminder.status.value),
    )
    
    return ConversationHandler.END


async def reminder_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mark reminder as done."""
    query = update.callback_query
    await query.answer()
    
    reminder_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        await reminder_service.mark_reminder_done(reminder_id, user.id if user else user_id)
        await session.commit()
    
    await query.edit_message_text("✅ Напоминание выполнено!")
    return ConversationHandler.END


async def reminder_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel reminder."""
    query = update.callback_query
    await query.answer()
    
    reminder_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        await reminder_service.mark_reminder_canceled(reminder_id, user.id if user else user_id)
        await session.commit()
    
    await query.edit_message_text("🚫 Напоминание отменено!")
    return ConversationHandler.END


async def reminder_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete reminder."""
    query = update.callback_query
    await query.answer()
    
    reminder_id = int(query.data.split(":")[1])
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        reminder_service = ReminderService(session)
        await reminder_service.delete_reminder(reminder_id, user.id if user else user_id)
        await session.commit()
    
    await query.edit_message_text("🗑 Напоминание удалено!")
    context.user_data.clear()
    return ConversationHandler.END


async def reminders_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle reminders filter."""
    query = update.callback_query
    await query.answer()
    
    if "active" in query.data:
        context.user_data["reminders_filter_active"] = True
    else:
        context.user_data["reminders_filter_active"] = False
    
    # Refresh list
    return await reminders_list_callback(update, context)


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current operation."""
    if update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.edit_message_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard(),
        )
    else:
        await update.message.reply_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard(),
        )
    context.user_data.clear()
    return ConversationHandler.END


# Conversation handler for reminder creation
reminder_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(reminder_create_start, pattern="^reminder_create$"),
        CallbackQueryHandler(reminder_create_start, pattern="^list_remind:"),
    ],
    states={
        ReminderStates.WAIT_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_save_text),
        ],
        ReminderStates.WAIT_DATE: [
            CallbackQueryHandler(reminder_date_today, pattern="^rem_date_today$"),
            CallbackQueryHandler(reminder_date_tomorrow, pattern="^rem_date_tomorrow$"),
            CallbackQueryHandler(reminder_date_after_tomorrow, pattern="^rem_date_after_tomorrow$"),
            CallbackQueryHandler(reminder_date_next_week, pattern="^rem_date_next_week$"),
            CallbackQueryHandler(reminder_date_custom, pattern="^rem_date_custom$"),
            CallbackQueryHandler(reminder_cancel_create, pattern="^rem_cancel_create$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_save_custom_date),
        ],
        ReminderStates.WAIT_TIME: [
            CallbackQueryHandler(reminder_time_back, pattern="^rem_time_back$"),
            CallbackQueryHandler(reminder_time_custom, pattern="^rem_time_custom$"),
            CallbackQueryHandler(reminder_time_preset, pattern="^rem_time_"),
        ],
        ReminderStates.WAIT_TIME_CUSTOM: [
            CallbackQueryHandler(reminder_time_back, pattern="^rem_time_back$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_save_custom_time),
        ],
        ReminderStates.WAIT_CONFIRM: [
            CallbackQueryHandler(reminder_confirm_create, pattern="^rem_confirm_create$"),
            CallbackQueryHandler(reminder_cancel_create, pattern="^rem_cancel_create$"),
            CallbackQueryHandler(reminder_repeat_set, pattern="^rem_repeat_set$"),
            CallbackQueryHandler(reminder_change_time, pattern="^rem_time_change$"),
        ],
        ReminderStates.WAIT_REPEAT: [
            CallbackQueryHandler(reminder_back_to_confirm, pattern="^rem_confirm_back$"),
            CallbackQueryHandler(reminder_save_repeat, pattern="^rem_repeat_"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)
