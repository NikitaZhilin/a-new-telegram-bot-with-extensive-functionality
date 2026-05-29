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
    get_reminder_edit_keyboard,
    get_reminder_edit_repeat_keyboard,
    get_driver_reminder_repeat_keyboard,
    get_back_home_inline_keyboard,
    get_cancel_keyboard,
    get_cancel_inline_keyboard,
)
from src.bot.states import ReminderStates
from src.config import settings
from src.db.session import async_session_maker
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.note_service import NoteService
from src.services.reminder_service import ReminderService
from src.repositories.user_repo import UserRepository
from src.db.models import RepeatRule
from src.utils.date_parser import parse_datetime
from src.utils.labels import reminder_status_label, repeat_rule_label

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 20


def _clear_linked_reminder_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove domain links from reminder creation context."""
    for key in (
        "linked_list_id",
        "linked_list_title",
        "linked_note_id",
        "linked_note_title",
        "reminder_source_module",
        "driver_reminder_template",
    ):
        context.user_data.pop(key, None)


async def _delete_user_message(update: Update) -> None:
    """Best-effort cleanup for text inputs in reminder edit flows."""
    if not update.message:
        return
    try:
        await update.message.delete()
    except Exception:
        logger.debug("Could not delete reminder user input", exc_info=True)


def _remember_reminder_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> None:
    """Remember a reminder message that can be edited after text input."""
    context.user_data["reminder_wizard_chat_id"] = chat_id
    context.user_data["reminder_wizard_message_id"] = message_id


async def _show_reminder_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit the current reminder message when possible, otherwise send a new one."""
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=reply_markup)
        _remember_reminder_message(context, query.message.chat_id, query.message.message_id)
        return

    chat_id = context.user_data.get("reminder_wizard_chat_id")
    message_id = context.user_data.get("reminder_wizard_message_id")
    if chat_id and message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return
        except Exception:
            logger.debug("Could not edit reminder message", exc_info=True)

    if update.effective_chat:
        message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
        )
        _remember_reminder_message(context, message.chat_id, message.message_id)


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


def _build_driver_reminder_template_text(template_key: str, reminder_text: str) -> str:
    """Build a ready-made driver reminder setup screen."""
    lines = [
        "⏰ Авто-напоминание готово",
        "",
        f"📝 {reminder_text}",
    ]
    if template_key == "tire_pressure":
        lines.extend([
            "",
            "Ориентиры по давлению:",
            "• легковые авто обычно: 2.2-2.4 бар",
            "• при полной загрузке часто добавляют около 0.2 бар",
            "• точные значения смотрите на табличке в проеме двери, лючке бака или в инструкции к авто",
        ])
    lines.extend(["", "Выберите периодичность:"])
    return "\n".join(lines)


def _driver_reminder_journal_title(template_key: str) -> str:
    """Return journal title for driver reminder templates."""
    return {
        "oil": "Напоминание о замене масла настроено",
        "fluids": "Напоминание о проверке жидкостей настроено",
        "wash": "Напоминание о мойке настроено",
        "tire_pressure": "Напоминание о давлении шин настроено",
        "service": "Напоминание о ТО настроено",
    }.get(template_key, "Авто-напоминание настроено")


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


def _roll_forward_if_needed(remind_at_utc: datetime, context: ContextTypes.DEFAULT_TYPE) -> datetime:
    """Move time-only driver reminders to the next future occurrence."""
    if not context.user_data.get("reminder_time_rollover_if_past"):
        return remind_at_utc

    now = datetime.now(timezone.utc)
    while remind_at_utc <= now:
        remind_at_utc += timedelta(days=1)
    return remind_at_utc


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

    if query and query.data.startswith("driver_reminder_template:"):
        await query.answer()
        from src.bot.handlers.driver import DRIVER_REMINDER_TEMPLATES

        template_key = query.data.split(":", 1)[1]
        _clear_linked_reminder_context(context)
        context.user_data["reminder_source_module"] = "driver"
        context.user_data["driver_reminder_template"] = template_key
        context.user_data["reminder_time_rollover_if_past"] = True
        context.user_data["reminder_text"] = DRIVER_REMINDER_TEMPLATES.get(
            template_key,
            "Автомобильное напоминание",
        )

        async with async_session_maker() as session:
            context.user_data["user_timezone"] = await _get_user_timezone(update, session)

        await query.edit_message_text(
            _build_driver_reminder_template_text(template_key, context.user_data["reminder_text"]),
            reply_markup=get_driver_reminder_repeat_keyboard(),
        )
        return ReminderStates.WAIT_REPEAT

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

        _clear_linked_reminder_context(context)
        context.user_data["linked_list_id"] = list_id
        context.user_data["linked_list_title"] = list_obj.title
        context.user_data["reminder_source_module"] = "list"
        context.user_data["reminder_text"] = f"Напомнить про список: {list_obj.title}"

        await query.edit_message_text(
            f"⏰ Напоминание о списке\n\n📋 {list_obj.title}\n\nКогда напомнить?",
            reply_markup=get_reminder_date_keyboard(),
        )
        return ReminderStates.WAIT_DATE

    if query and query.data.startswith("note_remind:"):
        await query.answer()
        note_id = int(query.data.split(":", 1)[1])

        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            context.user_data["user_timezone"] = await _get_user_timezone(update, session)
            note = await NoteService(session).get_note(note_id, user_id)

        if not note:
            await query.edit_message_text(
                "❌ Заметка не найдена",
                reply_markup=get_back_home_inline_keyboard(),
            )
            return ConversationHandler.END

        _clear_linked_reminder_context(context)
        context.user_data["linked_note_id"] = note_id
        context.user_data["linked_note_title"] = note.title
        context.user_data["reminder_source_module"] = "note"
        context.user_data["reminder_text"] = f"Напомнить про заметку: {note.title}"

        await query.edit_message_text(
            f"⏰ Напоминание о заметке\n\n📝 {note.title}\n\nКогда напомнить?",
            reply_markup=get_reminder_date_keyboard(),
        )
        return ReminderStates.WAIT_DATE

    _clear_linked_reminder_context(context)

    async with async_session_maker() as session:
        context.user_data["user_timezone"] = await _get_user_timezone(update, session)

    if query:
        await query.answer()
        await query.edit_message_text(
            "⏰ Создание напоминания\n\nВведите текст напоминания:",
            reply_markup=get_cancel_inline_keyboard(),
        )
        _remember_reminder_message(context, query.message.chat_id, query.message.message_id)
    else:
        message = await update.message.reply_text(
            "⏰ Создание напоминания\n\nВведите текст напоминания:",
            reply_markup=get_cancel_keyboard(),
        )
        _remember_reminder_message(context, message.chat_id, message.message_id)
    
    return ReminderStates.WAIT_TEXT


async def reminder_save_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save reminder text and show date selection."""
    text = update.message.text.strip()
    context.user_data["reminder_text"] = text
    await _delete_user_message(update)

    await _show_reminder_message(
        update,
        context,
        f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        "Когда напомнить?",
        get_reminder_date_keyboard(),
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
            await _delete_user_message(update)
            return await _create_reminder_from_context(update, context)

        selected_date = _parse_date_only(date_str, context)
        context.user_data["selected_date"] = selected_date.isoformat()
        await _delete_user_message(update)

        await _show_reminder_message(
            update,
            context,
            f"📅 Выбрано: {selected_date.strftime('%d.%m.%Y')}\n\n"
            "Теперь выберите время:",
            get_reminder_time_keyboard(),
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
    
    remind_at = _roll_forward_if_needed(remind_at, context)
    context.user_data["remind_at_utc"] = remind_at.isoformat()

    return await _create_reminder_from_context(update, context)


async def reminder_time_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return from time selection to date selection."""
    query = update.callback_query
    await query.answer()

    if context.user_data.get("driver_reminder_template"):
        await query.edit_message_text(
            _build_driver_reminder_template_text(
                context.user_data["driver_reminder_template"],
                context.user_data.get("reminder_text", "Автомобильное напоминание"),
            ),
            reply_markup=get_driver_reminder_repeat_keyboard(),
        )
        return ReminderStates.WAIT_REPEAT

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
        remind_at = _roll_forward_if_needed(remind_at, context)
        context.user_data["remind_at_utc"] = remind_at.isoformat()
        await _delete_user_message(update)
        return await _create_reminder_from_context(update, context)
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
    linked_note_title = context.user_data.get("linked_note_title")
    list_line = f"📋 Список: {linked_list_title}\n" if linked_list_title else ""
    note_line = f"📝 Заметка: {linked_note_title}\n" if linked_note_title else ""
    return (
        f"{prefix}"
        f"⏰ Подтверждение\n\n"
        f"{list_line}"
        f"{note_line}"
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


async def _create_reminder_from_context(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Create reminder from the current creation context and render its card."""
    user_id = update.effective_user.id
    text = context.user_data.get("reminder_text", "")
    remind_at_str = context.user_data.get("remind_at_utc")
    repeat_rule = context.user_data.get("repeat_rule", RepeatRule.NONE)
    linked_list_id = context.user_data.get("linked_list_id")
    linked_note_id = context.user_data.get("linked_note_id")
    source_module = context.user_data.get("reminder_source_module")

    if not remind_at_str:
        await _show_reminder_message(
            update,
            context,
            "❌ Не указано время напоминания.",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
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
            note_id=linked_note_id,
            source_module=source_module,
        )
        if reminder is None:
            await session.rollback()
            await _show_reminder_message(
                update,
                context,
                "❌ Не удалось создать напоминание: связанный объект не найден.",
                get_back_home_inline_keyboard(),
            )
            context.user_data.clear()
            return ConversationHandler.END
        driver_template = context.user_data.get("driver_reminder_template")
        if source_module == "driver" and driver_template:
            await DriverService(session).create_journal_entry(
                user_id=user.id if user else user_id,
                event_type=f"{driver_template}_reminder",
                title=_driver_reminder_journal_title(driver_template),
                description=f"Напоминание: {text}",
                happened_at_utc=datetime.now(timezone.utc),
                metadata={
                    "reminder_id": reminder.id,
                    "template": driver_template,
                    "remind_at_utc": reminder.remind_at_utc.isoformat(),
                    "repeat_rule": reminder.repeat_rule.value if hasattr(reminder.repeat_rule, "value") else str(reminder.repeat_rule),
                },
            )
        await session.commit()

    await _show_reminder_message(
        update,
        context,
        f"✅ Напоминание создано!\n\n"
        f"📝 {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        f"⏰ {_format_remind_at(context, remind_at_utc)}",
        get_reminder_view_keyboard(
            reminder.id,
            list_id=linked_list_id,
            note_id=linked_note_id,
            source_module=source_module,
        ),
    )

    context.user_data.clear()
    return ConversationHandler.END


async def reminder_confirm_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm and create reminder."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    text = context.user_data.get("reminder_text", "")
    remind_at_str = context.user_data.get("remind_at_utc")
    repeat_rule = context.user_data.get("repeat_rule", RepeatRule.NONE)
    linked_list_id = context.user_data.get("linked_list_id")
    linked_note_id = context.user_data.get("linked_note_id")
    source_module = context.user_data.get("reminder_source_module")
    
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
            note_id=linked_note_id,
            source_module=source_module,
        )
        if reminder is None:
            await session.rollback()
            await query.edit_message_text(
                "❌ Не удалось создать напоминание: связанный объект не найден",
                reply_markup=get_back_home_inline_keyboard(),
            )
            context.user_data.clear()
            return ConversationHandler.END
        await session.commit()
    
    await query.edit_message_text(
        f"✅ Напоминание создано!\n\n"
        f"📝 {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        f"⏰ {_format_remind_at(context, remind_at_utc)}",
        reply_markup=get_reminder_view_keyboard(
            reminder.id,
            list_id=linked_list_id,
            note_id=linked_note_id,
            source_module=source_module,
        ),
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


async def driver_reminder_repeat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save repeat rule for a ready-made driver reminder and ask only for time."""
    query = update.callback_query
    await query.answer()

    repeat_value = query.data.split(":", 1)[1]
    try:
        repeat_rule = RepeatRule(repeat_value)
    except ValueError:
        repeat_rule = RepeatRule.NONE

    context.user_data["repeat_rule"] = repeat_rule
    context.user_data["selected_date"] = datetime.now(ZoneInfo(_context_timezone(context))).date().isoformat()
    context.user_data["reminder_time_rollover_if_past"] = True

    await query.edit_message_text(
        f"🔁 Периодичность: {repeat_rule_label(repeat_rule)}\n\n"
        "Теперь выберите время напоминания:",
        reply_markup=get_reminder_time_keyboard(),
    )
    return ReminderStates.WAIT_TIME


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
        _build_confirmation_text(context, remind_at, prefix=f"🔁 Повтор: {repeat_rule_label(repeat_rule)}\n\n"),
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

    return await _refresh_reminder_screen(update, context, reminder_id, clear_context=False)


async def _render_reminder_screen(
    reminder_id: int,
    user_id: int,
    user_timezone: str,
) -> tuple[str | None, object | None]:
    """Build reminder details screen."""
    async with async_session_maker() as session:
        reminder_service = ReminderService(session)
        reminder = await reminder_service.get_reminder(reminder_id, user_id)

    if not reminder:
        return None, None

    remind_at = reminder.remind_at_utc
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)
    time_str = remind_at.astimezone(ZoneInfo(user_timezone)).strftime("%d.%m.%Y %H:%M")
    status_value = reminder.status.value if hasattr(reminder.status, "value") else reminder.status
    linked_lines = []
    if reminder.list_id:
        linked_title = reminder.todo_list.title if getattr(reminder, "todo_list", None) else "список удален"
        linked_lines.append(f"📋 Список: {linked_title}")
    if reminder.note_id:
        linked_title = reminder.note.title if getattr(reminder, "note", None) else "заметка удалена"
        linked_lines.append(f"📝 Заметка: {linked_title}")
    linked_block = ("\n".join(linked_lines) + "\n") if linked_lines else ""

    text = (
        f"⏰ Напоминание #{reminder.id}\n\n"
        f"{reminder.text}\n\n"
        f"{linked_block}"
        f"📅 Запланировано: {time_str} ({user_timezone})\n"
        f"🔁 Повтор: {repeat_rule_label(reminder.repeat_rule)}\n"
        f"⏰ Статус: {reminder_status_label(status_value)}"
    )

    return text, get_reminder_view_keyboard(
        reminder.id,
        status_value,
        reminder.list_id,
        reminder.source_module,
        note_id=reminder.note_id,
    )


async def _refresh_reminder_screen(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    reminder_id: int,
    clear_context: bool = True,
) -> int:
    """Render reminder details after edit actions."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)

    text, keyboard = await _render_reminder_screen(reminder_id, user_id, user_timezone)
    if not text:
        text = "❌ Напоминание не найдено"
        keyboard = get_back_home_inline_keyboard()

    await _show_reminder_message(update, context, text, keyboard)
    if clear_context:
        context.user_data.clear()
    return ConversationHandler.END


async def reminder_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show reminder edit choices from a compact edit button."""
    query = update.callback_query
    await query.answer()

    reminder_id = int(query.data.split(":")[1])
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        reminder = await reminder_service.get_reminder(reminder_id, user_id)

    if not reminder:
        await query.edit_message_text(
            "❌ Напоминание не найдено",
            reply_markup=get_back_home_inline_keyboard(),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "✏️ Что изменить в напоминании?",
        reply_markup=get_reminder_edit_keyboard(reminder_id),
    )
    return ConversationHandler.END


async def reminder_edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for new reminder text."""
    query = update.callback_query
    await query.answer()

    reminder_id = int(query.data.split(":")[1])
    context.user_data["reminder_edit_id"] = reminder_id

    await query.edit_message_text(
        "✏️ Введите новый текст напоминания:",
        reply_markup=get_cancel_inline_keyboard(),
    )
    _remember_reminder_message(context, query.message.chat_id, query.message.message_id)
    return ReminderStates.WAIT_EDIT_TEXT


async def reminder_edit_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save new reminder text."""
    reminder_id = context.user_data.get("reminder_edit_id")
    value = update.message.text.strip() if update.message else ""
    await _delete_user_message(update)

    if not reminder_id:
        await _show_reminder_message(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    if not value:
        await _show_reminder_message(
            update,
            context,
            "Текст не должен быть пустым. Введите новый текст напоминания:",
            get_cancel_inline_keyboard(),
        )
        return ReminderStates.WAIT_EDIT_TEXT

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        await reminder_service.update_reminder_text(reminder_id, user_id, value)
        await session.commit()

    return await _refresh_reminder_screen(update, context, reminder_id)


async def reminder_edit_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new reminder time."""
    query = update.callback_query
    await query.answer()

    reminder_id = int(query.data.split(":")[1])
    context.user_data["reminder_edit_id"] = reminder_id

    async with async_session_maker() as session:
        context.user_data["user_timezone"] = await _get_user_timezone(update, session)

    await query.edit_message_text(
        "🕒 Введите новое время или фразу:\n\n10\n10:30\nзавтра 10\nчерез 2 часа",
        reply_markup=get_cancel_inline_keyboard(),
    )
    _remember_reminder_message(context, query.message.chat_id, query.message.message_id)
    return ReminderStates.WAIT_EDIT_TIME


async def reminder_edit_time_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save new reminder time."""
    reminder_id = context.user_data.get("reminder_edit_id")
    if not reminder_id:
        await _delete_user_message(update)
        await _show_reminder_message(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    try:
        remind_at_utc = _parse_flexible_datetime(update.message.text.strip(), context)
    except ValueError:
        await _delete_user_message(update)
        await _show_reminder_message(
            update,
            context,
            "❌ Не понял время. Попробуйте так: 10, 10:30, завтра 10, через 2 часа",
            get_cancel_inline_keyboard(),
        )
        return ReminderStates.WAIT_EDIT_TIME

    await _delete_user_message(update)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        await reminder_service.update_reminder_time(reminder_id, user_id, remind_at_utc)
        await session.commit()

    return await _refresh_reminder_screen(update, context, reminder_id)


async def reminder_edit_repeat_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show repeat choices for an existing reminder."""
    query = update.callback_query
    await query.answer()

    reminder_id = int(query.data.split(":")[1])
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        reminder = await reminder_service.get_reminder(reminder_id, user_id)

    if not reminder:
        await query.edit_message_text("❌ Напоминание не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    repeat_value = reminder.repeat_rule.value if hasattr(reminder.repeat_rule, "value") else reminder.repeat_rule
    await query.edit_message_text(
        "🔁 Выберите повтор напоминания:",
        reply_markup=get_reminder_edit_repeat_keyboard(reminder_id, repeat_value),
    )
    return ConversationHandler.END


async def reminder_edit_repeat_value_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save repeat rule for an existing reminder."""
    query = update.callback_query
    await query.answer("Сохранено")

    _, reminder_id_str, repeat_value = query.data.split(":", 2)
    reminder_id = int(reminder_id_str)
    try:
        repeat_rule = RepeatRule(repeat_value)
    except ValueError:
        repeat_rule = RepeatRule.NONE

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        reminder_service = ReminderService(session)
        await reminder_service.update_reminder_repeat(reminder_id, user_id, repeat_rule)
        await session.commit()

    return await _refresh_reminder_screen(update, context, reminder_id)


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


reminder_edit_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(reminder_edit_text_start, pattern="^reminder_edit_text:"),
        CallbackQueryHandler(reminder_edit_time_start, pattern="^reminder_edit_time:"),
    ],
    states={
        ReminderStates.WAIT_EDIT_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_edit_text_save),
        ],
        ReminderStates.WAIT_EDIT_TIME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_edit_time_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)


# Conversation handler for reminder creation
reminder_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(reminder_create_start, pattern="^reminder_create$"),
        CallbackQueryHandler(reminder_create_start, pattern="^list_remind:"),
        CallbackQueryHandler(reminder_create_start, pattern="^note_remind:"),
        CallbackQueryHandler(reminder_create_start, pattern="^driver_reminder_template:"),
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
            CallbackQueryHandler(driver_reminder_repeat_callback, pattern="^driver_rem_repeat:"),
            CallbackQueryHandler(reminder_back_to_confirm, pattern="^rem_confirm_back$"),
            CallbackQueryHandler(reminder_save_repeat, pattern="^rem_repeat_"),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)
