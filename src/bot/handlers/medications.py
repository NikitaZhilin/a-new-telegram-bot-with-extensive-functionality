"""Medication handlers."""

import logging
import re
from datetime import datetime, time, timezone, timedelta
from typing import Optional
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
from sqlalchemy import func, select

from src.bot.handlers.reminders import (
    _get_user_timezone,
    _parse_flexible_datetime,
)
from src.bot.keyboards import (
    get_back_home_inline_keyboard,
    get_cancel_inline_keyboard,
    get_medication_dosage_keyboard,
    get_medication_edit_dosage_keyboard,
    get_medication_edit_importance_keyboard,
    get_medication_edit_instructions_keyboard,
    get_medication_edit_keyboard,
    get_medication_edit_text_keyboard,
    get_medication_delete_confirm_keyboard,
    get_medication_importance_keyboard,
    get_medication_instructions_keyboard,
    get_medication_reminder_keyboard,
    get_medication_view_keyboard,
    get_medications_list_keyboard,
)
from src.bot.states import MedicationStates
from src.db.models import Medication, Reminder, ReminderStatus
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.medication_service import MedicationService
from src.utils.text import truncate
from src.bot.handlers.conversation_exit import (
    TEXT_INPUT,
    WIZARD_TIMEOUT_SECONDS,
    exit_fallbacks,
    leave_wizard_fallbacks,
)

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 10

DOSAGE_PRESETS = {
    "tablet1": "1 таблетка",
    "tablet_half": "1/2 таблетки",
    "drop1": "1 капля",
    "ml5": "5 мл",
}

INSTRUCTION_PRESETS = {
    "after_food": "после еды",
    "during_food": "во время еды",
    "before_food": "до еды",
    "with_water": "запить водой",
    "separate": "принимать отдельно от других препаратов",
}

IMPORTANCE_LABELS = {
    "supplement": "🌿 БАД / добавка",
    "normal": "💊 Обычное лекарство",
    "important": "❗ Важное лекарство",
    "critical": "🚨 Критичное лекарство",
}

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


def _parse_id(data: str) -> int:
    """Parse first numeric ID from callback data."""
    return int(data.split(":", 1)[1].split(":", 1)[0])


def _parse_slot(data: str) -> Optional[datetime]:
    """Parse the optional reminder slot (unix seconds) from med_taken/med_skip data."""
    parts = data.split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return None
    return datetime.fromtimestamp(int(parts[2]), tz=timezone.utc)


async def _delete_user_message(update: Update) -> None:
    """Best-effort cleanup for medication text inputs."""
    if not update.message:
        return
    try:
        await update.message.delete()
    except Exception:
        logger.debug("Could not delete medication user input", exc_info=True)


async def _send_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup) -> None:
    """Send a message without replying to a user input that may be deleted."""
    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
    )
    _remember_wizard_message(context, message.chat_id, message.message_id)


def _remember_wizard_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
) -> None:
    """Remember the current medication wizard message for later edits."""
    context.user_data["med_wizard_chat_id"] = chat_id
    context.user_data["med_wizard_message_id"] = message_id


async def _show_wizard_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit the current wizard message when possible, otherwise send a new one."""
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=reply_markup)
        _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
        return

    chat_id = context.user_data.get("med_wizard_chat_id")
    message_id = context.user_data.get("med_wizard_message_id")
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
            logger.debug("Could not edit medication wizard message", exc_info=True)

    await _send_chat_message(update, context, text, reply_markup)


def _wizard_summary(next_step: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Build a compact medication creation progress message."""
    lines = ["💊 Новое лекарство"]
    if context.user_data.get("med_saved_id"):
        lines.append("✅ Уже сохранено — следующие шаги можно пропустить.")

    name = context.user_data.get("med_name")
    dosage = context.user_data.get("med_dosage")
    instructions = context.user_data.get("med_instructions")
    importance = context.user_data.get("med_importance")

    if name:
        lines.append(f"Название: {name}")
    if "med_dosage" in context.user_data:
        lines.append(f"Дозировка: {dosage or 'пропущена'}")
    if "med_instructions" in context.user_data:
        lines.append(f"Инструкция: {instructions or 'пропущена'}")
    if importance:
        lines.append(f"Важность: {IMPORTANCE_LABELS.get(importance, IMPORTANCE_LABELS['normal'])}")

    lines.append("")
    lines.append(next_step)
    return "\n".join(lines)


async def _render_medications_page(user_id: int, page: int = 0) -> tuple[str, object]:
    """Build medication list screen."""
    page = max(page, 0)

    async with async_session_maker() as session:
        service = MedicationService(session)
        medications, total = await service.get_medications_list(
            user_id=user_id,
            page=page,
            page_size=ITEMS_PER_PAGE,
        )
        active_reminders = (
            await session.execute(
                select(func.count(Reminder.id)).where(
                    Reminder.user_id == user_id,
                    Reminder.source_module == "medication",
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
        ).scalar() or 0
        critical_count = (
            await session.execute(
                select(func.count(Medication.id)).where(
                    Medication.user_id == user_id,
                    Medication.is_active.is_(True),
                    Medication.importance == "critical",
                )
            )
        ).scalar() or 0

    if not medications and page > 0:
        return await _render_medications_page(user_id, page - 1)

    if medications:
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        text = (
            f"💊 Приём лекарств ({total} всего)\n"
            f"Страница {page + 1}/{total_pages}\n\n"
            f"Кратко: активных напоминаний {active_reminders}, "
            f"критичных препаратов {critical_count}.\n\n"
            "Важно: бот только напоминает и фиксирует ваши отметки. "
            "Дозировки и режим приема задавайте по назначению врача."
        )
    else:
        text = (
            "💊 Приём лекарств\n\n"
            "Пока нет препаратов. Добавьте лекарство, дозировку/комментарий и время напоминания."
        )

    keyboard = get_medications_list_keyboard(
        medications,
        page=page,
        has_next=(page + 1) * ITEMS_PER_PAGE < total,
    )
    return text, keyboard


async def _render_medication_view(
    medication_id: int,
    user_id: int,
    user_timezone: str,
) -> tuple[str | None, object | None]:
    """Build one medication screen."""
    async with async_session_maker() as session:
        service = MedicationService(session)
        medication = await service.get_medication(medication_id, user_id)
        intakes = await service.get_recent_intakes(medication_id, user_id, limit=5)
        action_state = await service.get_intake_action_state(medication_id, user_id, user_timezone)
        today_slots = await service.get_today_slots(medication_id, user_id, user_timezone)

    if not medication:
        return None, None

    importance = getattr(medication, "importance", "normal")
    importance_label = IMPORTANCE_LABELS.get(importance, IMPORTANCE_LABELS["normal"])

    lines = [f"💊 {medication.name}", f"Важность: {importance_label}"]
    if medication.dosage:
        lines.append(f"Дозировка: {medication.dosage}")
    if medication.instructions:
        lines.append(f"Комментарий: {medication.instructions}")

    paused = MedicationService.is_paused(medication)
    lines.append("")
    if paused:
        lines.extend(_format_pause_state(medication, user_timezone))
    else:
        lines.extend(_format_medication_action_state(action_state, user_timezone))

    if today_slots:
        lines.append("")
        lines.append("Сегодня:")
        for slot in today_slots:
            lines.append(_format_medication_today_slot(slot, user_timezone))

    lines.append("")
    if intakes:
        lines.append("Последние отметки:")
        tz = ZoneInfo(user_timezone)
        for intake in intakes:
            local_dt = intake.taken_at_utc.astimezone(tz)
            status_value = intake.status.value if hasattr(intake.status, "value") else intake.status
            icon = "⏭" if status_value == "skipped" else "✅"
            label = "пропущено" if status_value == "skipped" else "принято"
            lines.append(f"{icon} {local_dt.strftime('%d.%m.%Y %H:%M')} — {label}")
    else:
        lines.append("Отметок приема пока нет.")

    fix_action = None
    if (
        not paused
        and action_state.reason == "slot_already_marked"
        and action_state.marked_status
        and action_state.current_slot_at_utc
    ):
        slot_ts = int(action_state.current_slot_at_utc.timestamp())
        fix_action = "taken" if action_state.marked_status == "skipped" else "skipped"
        fix_action = (fix_action, slot_ts)
    return "\n".join(lines), get_medication_view_keyboard(
        medication_id, can_mark=action_state.can_mark, paused=paused, fix_action=fix_action
    )


def _format_pause_state(medication, user_timezone: str) -> list[str]:
    """Card lines for a medication on a break between courses."""
    from datetime import date as date_cls

    service = MedicationService
    until = medication.paused_until
    today = datetime.now(ZoneInfo(user_timezone)).date()
    days_left = (until - today).days if isinstance(until, date_cls) else 0
    lines = [f"⏸ Перерыв между курсами до {until.strftime('%d.%m.%Y')} (осталось {days_left} дн.)"]
    notice_at = service.pause_notice_at(medication, user_timezone)
    if notice_at and notice_at > datetime.now(timezone.utc):
        notice_local = notice_at.astimezone(ZoneInfo(user_timezone))
        lines.append(
            f"🔔 Напомню за {service.days_phrase(service.notice_days(medication))}: "
            f"{notice_local.strftime('%d.%m.%Y в %H:%M')}"
        )
    elif service.notice_days(medication) <= 0:
        lines.append("🔕 Напоминание перед курсом выключено")
    times = service.paused_times(medication)
    if times:
        lines.append(
            f"▶️ {until.strftime('%d.%m')} приёмы вернутся сами: "
            + ", ".join(item.strftime("%H:%M") for item in times)
        )
    else:
        lines.append(f"▶️ {until.strftime('%d.%m')} курс возобновится — время приёма можно будет задать кнопкой «Напомнить».")
    return lines


def _format_medication_today_slot(slot, user_timezone: str) -> str:
    """Human-readable daily slot line for a medication card."""
    icon = {
        "taken": "✅",
        "skipped": "⏭",
        "available": "🟢",
        "pending": "⏳",
        "missed": "⚪",
    }.get(slot.status, "•")
    label = {
        "taken": "принято",
        "skipped": "пропущено",
        "available": "можно отметить",
        "pending": "ожидает",
        "missed": "без отметки",
    }.get(slot.status, slot.status)
    line = f"{icon} {slot.label}: {label}"
    if slot.marked_at_utc:
        local_dt = slot.marked_at_utc.astimezone(ZoneInfo(user_timezone))
        line += f" в {local_dt.strftime('%H:%M')}"
    return line


def _format_medication_action_state(action_state, user_timezone: str) -> list[str]:
    """Human-readable explanation of the current intake action state."""
    tz = ZoneInfo(user_timezone)
    if action_state.can_mark:
        if action_state.has_schedule and action_state.current_slot_at_utc:
            slot_local = action_state.current_slot_at_utc.astimezone(tz)
            return [f"Текущий прием: {slot_local.strftime('%H:%M')}. Можно отметить сейчас."]
        return ["Можно отметить прием сегодня."]

    if action_state.next_available_at_utc:
        next_local = action_state.next_available_at_utc.astimezone(tz)
        if action_state.reason in {"slot_already_marked", "already_marked_today"}:
            if action_state.marked_status and action_state.current_slot_at_utc:
                slot_local = action_state.current_slot_at_utc.astimezone(tz)
                label = "пропущено" if action_state.marked_status == "skipped" else "принято"
                first = f"Приём {slot_local.strftime('%H:%M')} отмечен: {label}. Ошиблись — исправьте кнопкой ниже."
            else:
                first = "Прием уже отмечен."
            return [
                first,
                f"Кнопки приема появятся снова: {next_local.strftime('%d.%m %H:%M')}.",
            ]

    return ["Сейчас прием недоступен."]


def _format_medication_action_alert(action_state, user_timezone: str) -> str:
    """Short alert for stale or unavailable medication action buttons."""
    if action_state.reason == "not_found":
        return "Лекарство не найдено"
    if action_state.reason == "paused":
        return "Сейчас перерыв между курсами — отмечать приём не нужно"
    if action_state.reason == "slot_not_open" and action_state.next_available_at_utc:
        open_local = action_state.next_available_at_utc.astimezone(ZoneInfo(user_timezone))
        return f"Окно этого приема откроется {open_local.strftime('%d.%m %H:%M')}"
    if action_state.next_available_at_utc:
        next_local = action_state.next_available_at_utc.astimezone(ZoneInfo(user_timezone))
        return f"Этот прием уже закрыт. Следующее окно: {next_local.strftime('%d.%m %H:%M')}"
    return "Сейчас прием недоступен"


async def medications_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show medication list."""
    query = update.callback_query
    if query:
        await query.answer()

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_medications_page(user_id, page=0)
    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return ConversationHandler.END


async def medications_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show paginated medication page."""
    query = update.callback_query
    await query.answer()

    page = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_medications_page(user_id, page=page)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def medication_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one medication."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)

    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    if not text:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def _refresh_medication_screen(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    medication_id: int,
) -> int:
    """Render medication screen after edit actions."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)

    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    if not text:
        text = "❌ Лекарство не найдено"
        keyboard = get_back_home_inline_keyboard("medications_list")

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await _show_wizard_step(update, context, text, reply_markup=keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def medication_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show medication edit field selector."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        medication = await service.get_medication(medication_id, user_id)

    if not medication:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    lines = [
        "✏️ Изменение лекарства",
        "",
        f"Название: {medication.name}",
        f"Дозировка: {medication.dosage or 'не указана'}",
        f"Инструкция: {medication.instructions or 'не указана'}",
        f"Важность: {IMPORTANCE_LABELS.get(medication.importance, IMPORTANCE_LABELS['normal'])}",
        "",
        "Выберите, что изменить.",
    ]
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_medication_edit_keyboard(medication_id),
    )
    return ConversationHandler.END


async def medication_edit_name_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new medication name."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    context.user_data["med_edit_id"] = medication_id

    await query.edit_message_text(
        "✏️ Введите новое название препарата:",
        reply_markup=get_medication_edit_text_keyboard(medication_id),
    )
    _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
    return MedicationStates.WAIT_EDIT_NAME


async def medication_edit_dosage_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new medication dosage."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    context.user_data["med_edit_id"] = medication_id

    await query.edit_message_text(
        "✏️ Укажите новую дозировку.\n\nМожно выбрать кнопку или написать свой вариант.",
        reply_markup=get_medication_edit_dosage_keyboard(medication_id),
    )
    _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
    return MedicationStates.WAIT_EDIT_DOSAGE


async def medication_edit_instructions_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for new medication instructions."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    context.user_data["med_edit_id"] = medication_id

    await query.edit_message_text(
        "✏️ Укажите новую инструкцию.\n\nМожно выбрать кнопку или написать свой вариант.",
        reply_markup=get_medication_edit_instructions_keyboard(medication_id),
    )
    _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
    return MedicationStates.WAIT_EDIT_INSTRUCTIONS


async def medication_edit_importance_start_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Show medication importance choices for editing."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        medication = await service.get_medication(medication_id, user_id)

    if not medication:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    await query.edit_message_text(
        "✏️ Выберите важность препарата:",
        reply_markup=get_medication_edit_importance_keyboard(medication_id, medication.importance),
    )
    return ConversationHandler.END


async def medication_edit_name_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save a new medication name."""
    medication_id = context.user_data.get("med_edit_id")
    value = update.message.text.strip() if update.message else ""
    await _delete_user_message(update)

    if not medication_id:
        await _show_wizard_step(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard("medications_list"))
        context.user_data.clear()
        return ConversationHandler.END

    if not value:
        await _show_wizard_step(
            update,
            context,
            "Название не должно быть пустым. Введите новое название препарата:",
            get_medication_edit_text_keyboard(medication_id),
        )
        return MedicationStates.WAIT_EDIT_NAME

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, name=value)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_edit_dosage_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save a new medication dosage from text."""
    medication_id = context.user_data.get("med_edit_id")
    value = update.message.text.strip() if update.message else ""
    await _delete_user_message(update)

    if not medication_id:
        await _show_wizard_step(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard("medications_list"))
        context.user_data.clear()
        return ConversationHandler.END

    dosage = "" if value == "-" else value
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, dosage=dosage)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_edit_instructions_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save new medication instructions from text."""
    medication_id = context.user_data.get("med_edit_id")
    value = update.message.text.strip() if update.message else ""
    await _delete_user_message(update)

    if not medication_id:
        await _show_wizard_step(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard("medications_list"))
        context.user_data.clear()
        return ConversationHandler.END

    instructions = "" if value == "-" else value
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, instructions=instructions)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_edit_dosage_value_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Save a new medication dosage from a preset button."""
    query = update.callback_query
    await query.answer("Сохранено")

    _, medication_id_str, key = query.data.split(":", 2)
    medication_id = int(medication_id_str)
    dosage = "" if key == "skip" else DOSAGE_PRESETS.get(key, "")

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, dosage=dosage)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_edit_instructions_value_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Save new medication instructions from a preset button."""
    query = update.callback_query
    await query.answer("Сохранено")

    _, medication_id_str, key = query.data.split(":", 2)
    medication_id = int(medication_id_str)
    instructions = "" if key == "skip" else INSTRUCTION_PRESETS.get(key, "")

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, instructions=instructions)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_edit_importance_value_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Save medication importance from a preset button."""
    query = update.callback_query
    await query.answer("Сохранено")

    _, medication_id_str, importance = query.data.split(":", 2)
    medication_id = int(medication_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        await service.update_medication(medication_id, user_id, importance=importance)
        await session.commit()

    return await _refresh_medication_screen(update, context, medication_id)


async def medication_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start medication creation."""
    query = update.callback_query
    await query.answer()
    for key in ("med_saved_id", "med_name", "med_dosage", "med_instructions", "med_importance"):
        context.user_data.pop(key, None)

    await _show_wizard_step(
        update,
        context,
        _wizard_summary("Шаг 1/5. Введите название препарата:", context),
        reply_markup=get_cancel_inline_keyboard(),
    )
    return MedicationStates.WAIT_NAME


async def _update_saved_medication(update: Update, context: ContextTypes.DEFAULT_TYPE, **fields) -> None:
    """Write a wizard step straight into the already saved medication."""
    medication_id = context.user_data.get("med_saved_id")
    if not medication_id:
        return
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        await MedicationService(session).update_medication(medication_id, user_id, **fields)
        await session.commit()


async def medication_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the medication right after its name; the other steps only refine it.

    Before, nothing was stored until the importance step, so a wizard left
    half-way lost everything.
    """
    name = update.message.text.strip()
    await _delete_user_message(update)
    if not name:
        await _show_wizard_step(
            update,
            context,
            _wizard_summary("Название не может быть пустым. Введите название препарата:", context),
            reply_markup=get_cancel_inline_keyboard(),
        )
        return MedicationStates.WAIT_NAME
    context.user_data["med_name"] = name
    if context.user_data.get("med_saved_id"):
        await _update_saved_medication(update, context, name=name)
    else:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            medication = await MedicationService(session).create_medication(user_id=user_id, name=name)
            await session.commit()
            context.user_data["med_saved_id"] = medication.id

    await _show_wizard_step(
        update,
        context,
        _wizard_summary(
            "Шаг 2/5. Укажите дозировку или краткий комментарий.\n\n"
            "Можно выбрать кнопку или написать свой вариант.",
            context,
        ),
        reply_markup=get_medication_dosage_keyboard(),
    )
    return MedicationStates.WAIT_DOSAGE


async def _ask_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for medication instructions."""
    await _show_wizard_step(
        update,
        context,
        _wizard_summary(
            "Шаг 3/5. Добавьте важную инструкцию: до еды, после еды, запить водой, курс и т.п.\n\n"
            "Можно выбрать кнопку или написать свой вариант.",
            context,
        ),
        reply_markup=get_medication_instructions_keyboard(),
    )
    return MedicationStates.WAIT_INSTRUCTIONS


async def _ask_importance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for medication importance."""
    await _show_wizard_step(
        update,
        context,
        _wizard_summary(
            "Шаг 4/5. Насколько это важно?\n\n"
            "Это поможет визуально отделить БАДы от действительно важных лекарств.",
            context,
        ),
        reply_markup=get_medication_importance_keyboard(),
    )
    return MedicationStates.WAIT_IMPORTANCE


async def medication_save_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store medication dosage."""
    value = update.message.text.strip()
    context.user_data["med_dosage"] = "" if value == "-" else value
    await _delete_user_message(update)
    await _update_saved_medication(update, context, dosage=context.user_data["med_dosage"])

    return await _ask_instructions(update, context)


async def medication_dosage_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store medication dosage from a button."""
    query = update.callback_query
    await query.answer()

    key = query.data.split(":", 1)[1]
    context.user_data["med_dosage"] = "" if key == "skip" else DOSAGE_PRESETS.get(key, "")
    await _update_saved_medication(update, context, dosage=context.user_data["med_dosage"])

    return await _ask_instructions(update, context)


async def medication_save_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store medication instructions from text."""
    value = update.message.text.strip()
    context.user_data["med_instructions"] = "" if value == "-" else value
    await _delete_user_message(update)
    await _update_saved_medication(update, context, instructions=context.user_data["med_instructions"])

    return await _ask_importance(update, context)


async def medication_instructions_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store medication instructions from a button."""
    query = update.callback_query
    await query.answer()

    key = query.data.split(":", 1)[1]
    context.user_data["med_instructions"] = "" if key == "skip" else INSTRUCTION_PRESETS.get(key, "")
    await _update_saved_medication(update, context, instructions=context.user_data["med_instructions"])

    return await _ask_importance(update, context)


async def medication_importance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create medication after choosing importance and offer reminder setup."""
    query = update.callback_query
    await query.answer()

    importance = query.data.split(":", 1)[1]
    if importance not in IMPORTANCE_LABELS:
        importance = "normal"
    context.user_data["med_importance"] = importance

    medication_id = context.user_data.get("med_saved_id")
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        medication = None
        if medication_id:
            medication = await service.update_medication(medication_id, user_id, importance=importance)
        if medication is None:
            medication = await service.create_medication(
                user_id=user_id,
                name=context.user_data.get("med_name", "Лекарство"),
                dosage=context.user_data.get("med_dosage") or None,
                instructions=context.user_data.get("med_instructions") or None,
                importance=importance,
            )
        await session.commit()
        medication_id = medication.id

    await _show_wizard_step(
        update,
        context,
        _wizard_summary(
            "Шаг 5/5. Лекарство добавлено.\n\n"
            "Выберите, когда напоминать о приеме. "
            "Если напоминание пока не нужно, нажмите «Пропустить».",
            context,
        ),
        reply_markup=get_medication_reminder_keyboard(medication_id),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def medication_importance_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep importance as a deliberate button choice."""
    await _delete_user_message(update)
    await _ask_importance(update, context)
    return MedicationStates.WAIT_IMPORTANCE


async def medication_mark_taken_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mark medication as taken."""
    query = update.callback_query

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        service = MedicationService(session)
        slot_utc = _parse_slot(query.data)
        if slot_utc is not None:
            intake, state = await service.mark_taken_for_slot(medication_id, user_id, user_timezone, slot_utc)
        else:
            intake, state = await service.mark_taken_for_current_slot(medication_id, user_id, user_timezone)
        await session.commit()

    if not intake:
        if state.reason == "not_found":
            await query.answer("Лекарство не найдено")
            await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
            return ConversationHandler.END
        await query.answer(_format_medication_action_alert(state, user_timezone), show_alert=True)
    else:
        name = getattr(intake, "medication_name_snapshot", None) or "лекарство"
        await query.answer(f"✅ {name}: принято")

    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def medication_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mark medication intake as skipped."""
    query = update.callback_query

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        service = MedicationService(session)
        slot_utc = _parse_slot(query.data)
        if slot_utc is not None:
            intake, state = await service.mark_skipped_for_slot(medication_id, user_id, user_timezone, slot_utc)
        else:
            intake, state = await service.mark_skipped_for_current_slot(medication_id, user_id, user_timezone)
        await session.commit()

    if not intake:
        if state.reason == "not_found":
            await query.answer("Лекарство не найдено")
            await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
            return ConversationHandler.END
        await query.answer(_format_medication_action_alert(state, user_timezone), show_alert=True)
    else:
        name = getattr(intake, "medication_name_snapshot", None) or "лекарство"
        await query.answer(f"⏭ {name}: пропущено. Ошиблись — исправьте в карточке.")

    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def medication_snooze_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Snooze medication reminder for 15 minutes."""
    query = update.callback_query
    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        if MedicationService.is_paused(await service.get_medication(medication_id, user_id)):
            await query.answer("Сейчас перерыв между курсами", show_alert=True)
            return ConversationHandler.END
    await query.answer("Напомню через 15 минут")

    async with async_session_maker() as session:
        service = MedicationService(session)
        reminder = await service.snooze_reminder(medication_id, user_id, minutes=15)
        await session.commit()

    if not reminder:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    await query.edit_message_text(
        "↩️ Отложено на 15 минут",
        reply_markup=get_medication_view_keyboard(medication_id),
    )
    return ConversationHandler.END


async def medication_remind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show medication reminder choices."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    await query.edit_message_text(
        "⏰ Когда напоминать о приеме?\n\n"
        "Выберите, сколько раз в день принимать препарат, затем укажите конкретное время. "
        "Разовые быстрые кнопки ниже создают одно ежедневное напоминание.",
        reply_markup=get_medication_reminder_keyboard(medication_id),
    )
    return ConversationHandler.END


async def medication_reminder_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip reminder setup after medication creation."""
    query = update.callback_query
    await query.answer("Можно настроить позже")

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)

    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    if not text:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


def _next_local_time_utc(hhmm: str, user_timezone: str) -> datetime:
    """Return next occurrence of HHMM in user's timezone as UTC."""
    now = datetime.now(ZoneInfo(user_timezone))
    local_time = time(hour=int(hhmm[:2]), minute=int(hhmm[2:]))
    local_dt = datetime.combine(now.date(), local_time, tzinfo=ZoneInfo(user_timezone))
    if local_dt <= now:
        local_dt += timedelta(days=1)
    return local_dt.astimezone(timezone.utc)


def _normalize_hhmm(value: str) -> str:
    """Normalize a user-entered clock token to HHMM."""
    value = value.strip()
    if not value:
        raise ValueError("empty time")

    if re.fullmatch(r"\d{1,2}", value):
        hour = int(value)
        minute = 0
    elif re.fullmatch(r"\d{3,4}", value):
        padded = value.zfill(4)
        hour = int(padded[:2])
        minute = int(padded[2:])
    else:
        match = re.fullmatch(r"(\d{1,2})[:.\-](\d{2})", value)
        if not match:
            raise ValueError("invalid time")
        hour = int(match.group(1))
        minute = int(match.group(2))

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("invalid time")

    return f"{hour:02d}{minute:02d}"


TIME_WORD_PRESETS = {
    "утро": "09:00",
    "утром": "09:00",
    "завтрак": "09:00",
    "завтраком": "09:00",
    "день": "14:00",
    "днем": "14:00",
    "днём": "14:00",
    "обед": "14:00",
    "обедом": "14:00",
    "вечер": "21:00",
    "вечером": "21:00",
    "ужин": "21:00",
    "ужином": "21:00",
    "ночь": "23:00",
    "ночью": "23:00",
}


def _extract_time_tokens(value: str) -> list[str]:
    """Extract flexible local time tokens from user text."""
    normalized = value.lower().replace("ё", "е")
    for word, replacement in TIME_WORD_PRESETS.items():
        normalized = re.sub(rf"\b{word.replace('ё', 'е')}\b", replacement, normalized)

    return re.findall(r"\b\d{1,2}[:.\-]\d{2}\b|\b\d{3,4}\b|\b\d{1,2}\b", normalized)


def _parse_local_time_list(value: str, expected_count: int, user_timezone: str) -> list[datetime]:
    """Parse several local HH:MM values into UTC datetimes."""
    tokens = _extract_time_tokens(value)
    if len(tokens) != expected_count:
        raise ValueError("wrong time count")

    hhmm_values = [_normalize_hhmm(token) for token in tokens]
    if len(set(hhmm_values)) != len(hhmm_values):
        raise ValueError("duplicate times")

    return [_next_local_time_utc(hhmm, user_timezone) for hhmm in hhmm_values]


def _format_local_time(remind_at_utc: datetime, user_timezone: str) -> str:
    """Format UTC reminder time in user's timezone."""
    local_dt = remind_at_utc.astimezone(ZoneInfo(user_timezone))
    return f"{local_dt.strftime('%d.%m.%Y %H:%M')} ({user_timezone})"


async def _create_medication_reminder(
    update: Update,
    medication_id: int,
    remind_at_utc: datetime,
) -> tuple[bool, str]:
    """Create daily medication reminder and return message text."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        service = MedicationService(session)
        reminders = await service.replace_daily_reminders(
            medication_id=medication_id,
            user_id=user_id,
            remind_at_utcs=[remind_at_utc],
        )
        await session.commit()

    if not reminders:
        return False, "❌ Лекарство не найдено"

    return True, (
        "✅ Ежедневное напоминание создано\n\n"
        f"Когда: {_format_local_time(remind_at_utc, user_timezone)}"
    )


async def _create_medication_reminders(
    update: Update,
    medication_id: int,
    remind_at_utcs: list[datetime],
) -> tuple[bool, str]:
    """Create several daily medication reminders."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        service = MedicationService(session)

        created = []
        reminders = await service.replace_daily_reminders(
            medication_id=medication_id,
            user_id=user_id,
            remind_at_utcs=remind_at_utcs,
        )
        if reminders:
            created = remind_at_utcs

        await session.commit()

    if not created:
        return False, "❌ Лекарство не найдено"

    lines = ["✅ Ежедневные напоминания созданы", ""]
    for remind_at_utc in created:
        lines.append(f"• {_format_local_time(remind_at_utc, user_timezone)}")
    return True, "\n".join(lines)


async def medication_reminder_frequency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for exact times after a frequency button."""
    query = update.callback_query
    await query.answer()

    _, medication_id_str, count_str = query.data.split(":", 2)
    medication_id = int(medication_id_str)
    count = int(count_str)
    if count not in {1, 2, 3}:
        count = 1

    async with async_session_maker() as session:
        context.user_data["user_timezone"] = await _get_user_timezone(update, session)

    context.user_data["med_reminder_id"] = medication_id
    context.user_data["med_reminder_count"] = count

    examples = {
        1: "09:00",
        2: "09:00, 21:00",
        3: "08:00, 14:00, 22:00",
    }
    await query.edit_message_text(
        f"Введите {count} {'время' if count == 1 else 'времени'} приема.\n\n"
        "Можно без запятых: 9 21, 09:00 21:00, утром вечером.\n"
        f"Пример: {examples[count]}",
        reply_markup=get_cancel_inline_keyboard(),
    )
    _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
    return MedicationStates.WAIT_REMINDER_TIME


async def medication_reminder_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create medication reminder from a quick time button."""
    query = update.callback_query
    await query.answer()

    _, medication_id_str, hhmm = query.data.split(":", 2)
    medication_id = int(medication_id_str)

    async with async_session_maker() as session:
        user_timezone = await _get_user_timezone(update, session)

    remind_at_utc = _next_local_time_utc(hhmm, user_timezone)
    ok, text = await _create_medication_reminder(update, medication_id, remind_at_utc)
    await query.edit_message_text(
        text,
        reply_markup=get_medication_view_keyboard(medication_id) if ok else get_back_home_inline_keyboard("medications_list"),
    )
    return ConversationHandler.END


async def medication_reminder_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for custom medication reminder time."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    context.user_data["med_reminder_id"] = medication_id

    async with async_session_maker() as session:
        context.user_data["user_timezone"] = await _get_user_timezone(update, session)

    await query.edit_message_text(
        "Введите время или фразу:\n\n"
        "10\n10:30\nзавтра 10\nчерез 8 часов",
        reply_markup=get_cancel_inline_keyboard(),
    )
    _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
    return MedicationStates.WAIT_REMINDER_TIME


async def medication_reminder_custom_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create medication reminder from custom text."""
    medication_id = context.user_data.get("med_reminder_id")
    reminder_count = context.user_data.get("med_reminder_count")

    if reminder_count:
        try:
            remind_at_utcs = _parse_local_time_list(
                update.message.text.strip(),
                int(reminder_count),
                context.user_data.get("user_timezone", "UTC"),
            )
        except ValueError:
            await _delete_user_message(update)
            await _show_wizard_step(
                update,
                context,
                f"❌ Не понял время. Введите ровно {reminder_count} "
                "значения любым удобным способом.\n\n"
                "Примеры: 9 21, 09:00 21:00, утром вечером.",
                get_cancel_inline_keyboard(),
            )
            return MedicationStates.WAIT_REMINDER_TIME

        await _delete_user_message(update)
        ok, text = await _create_medication_reminders(update, medication_id, remind_at_utcs)
        await _show_wizard_step(
            update,
            context,
            text,
            reply_markup=get_medication_view_keyboard(medication_id) if ok else get_back_home_inline_keyboard("medications_list"),
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        remind_at_utc = _parse_flexible_datetime(update.message.text.strip(), context)
    except ValueError:
        await _delete_user_message(update)
        await _show_wizard_step(
            update,
            context,
            "❌ Не понял время. Попробуйте так: 10, 10:30, завтра 10, через 8 часов",
            get_cancel_inline_keyboard(),
        )
        return MedicationStates.WAIT_REMINDER_TIME

    await _delete_user_message(update)

    ok, text = await _create_medication_reminder(update, medication_id, remind_at_utc)
    await _show_wizard_step(
        update,
        context,
        text,
        reply_markup=get_medication_view_keyboard(medication_id) if ok else get_back_home_inline_keyboard("medications_list"),
    )
    context.user_data.clear()
    return ConversationHandler.END


# =============================================================================
# Break between courses
# =============================================================================

PAUSE_MONTH_OPTIONS = (1, 2, 3, 4, 6)


def _add_months(day, months: int):
    import calendar

    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def _parse_pause_date(value: str, today):
    """«15.01.2027», «15.01.27» or «15.01» (next such date) → date, or None."""
    from datetime import date as date_cls

    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*", value or "")
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
    try:
        if year:
            year_value = int(year) + (2000 if len(year) == 2 else 0)
            return date_cls(year_value, month, day)
        candidate = date_cls(today.year, month, day)
        return candidate if candidate > today else date_cls(today.year + 1, month, day)
    except ValueError:
        return None


def _pause_period_keyboard(medication_id: int):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    labels = {1: "1 месяц", 2: "2 месяца", 3: "3 месяца", 4: "4 месяца", 6: "6 месяцев"}
    buttons = [
        InlineKeyboardButton(labels[months], callback_data=f"med_pause_set:{medication_id}:{months}")
        for months in PAUSE_MONTH_OPTIONS
    ]
    return InlineKeyboardMarkup([
        buttons[:3],
        buttons[3:],
        [InlineKeyboardButton("📅 Своя дата", callback_data=f"med_pause_custom:{medication_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"med_view:{medication_id}")],
    ])


async def medication_pause_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask how long the break between courses lasts."""
    query = update.callback_query
    await query.answer()
    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        medication = await MedicationService(session).get_medication(medication_id, user_id)
    if not medication:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END
    await query.edit_message_text(
        f"⏸ Перерыв между курсами: {medication.name}\n\n"
        "На сколько поставить паузу? Пока идёт перерыв, напоминания о приёме не приходят.\n"
        "Перед концом перерыва я напомню о скором курсе (срок выберете дальше), "
        "а в день начала курса напоминания вернутся сами в то же время.",
        reply_markup=_pause_period_keyboard(medication_id),
    )
    return ConversationHandler.END


PAUSE_NOTICE_OPTIONS = ((3, "За 3 дня"), (7, "За неделю"), (14, "За 2 недели"))


def _pause_notice_keyboard(medication_id: int, until, today):
    """Heads-up choices that fit into the break (a 5-day break cannot warn 2 weeks ahead)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    stamp = until.strftime("%Y%m%d")
    length = (until - today).days
    options = [
        InlineKeyboardButton(label, callback_data=f"med_pause_apply:{medication_id}:{stamp}:{days}")
        for days, label in PAUSE_NOTICE_OPTIONS
        if days < length
    ]
    rows = [options] if options else []
    rows.append([InlineKeyboardButton("🔕 Не напоминать", callback_data=f"med_pause_apply:{medication_id}:{stamp}:0")])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=f"med_view:{medication_id}")])
    return InlineKeyboardMarkup(rows)


def _pause_notice_question(until) -> str:
    return (
        f"⏸ Перерыв до {until.strftime('%d.%m.%Y')}.\n\n"
        "За сколько дней до начала курса напомнить? "
        "Например, чтобы успеть купить лекарство."
    )


async def medication_pause_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the break with the chosen heads-up."""
    from datetime import date as date_cls

    query = update.callback_query
    _, medication_id, stamp, days = query.data.split(":")
    until = date_cls(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
    try:
        text, keyboard = await _apply_pause(update, int(medication_id), until, notice_days=int(days))
    except ValueError:
        await query.answer("Эта дата уже прошла — выберите срок заново", show_alert=True)
        return ConversationHandler.END
    if not text:
        await query.answer()
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END
    await query.answer(f"Перерыв до {until.strftime('%d.%m.%Y')}")
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def _apply_pause(update: Update, medication_id: int, until, notice_days: Optional[int] = None) -> tuple[Optional[str], object]:
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        medication = await MedicationService(session).pause_course(
            medication_id, user_id, until, user_timezone, notice_days=notice_days
        )
        await session.commit()
    if not medication:
        return None, None
    return await _render_medication_view(medication_id, user_id, user_timezone)


async def medication_pause_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pause for N months from today."""
    query = update.callback_query
    _, medication_id, months = query.data.split(":")
    async with async_session_maker() as session:
        user_timezone = await _get_user_timezone(update, session)
    today = datetime.now(ZoneInfo(user_timezone)).date()
    until = _add_months(today, int(months))
    await query.answer()
    await query.edit_message_text(
        _pause_notice_question(until),
        reply_markup=_pause_notice_keyboard(int(medication_id), until, today),
    )
    return ConversationHandler.END


async def medication_pause_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for the date the next course starts."""
    query = update.callback_query
    await query.answer()
    medication_id = _parse_id(query.data)
    context.user_data["pause_medication_id"] = medication_id
    await _show_wizard_step(
        update,
        context,
        "📅 С какого дня снова начинается курс?\n\n"
        "Напишите дату, например 15.01.2027 или 15.01.",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return MedicationStates.WAIT_PAUSE_DATE


async def medication_pause_custom_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save a pause until the typed date."""
    medication_id = context.user_data.get("pause_medication_id")
    async with async_session_maker() as session:
        user_timezone = await _get_user_timezone(update, session)
    today = datetime.now(ZoneInfo(user_timezone)).date()
    until = _parse_pause_date(update.message.text, today)
    await _delete_user_message(update)
    if medication_id is None:
        return ConversationHandler.END
    if until is None or until <= today or (until - today).days > 3 * 366:
        await _show_wizard_step(
            update,
            context,
            "Не получилось понять дату. Напишите день начала следующего курса, "
            "например 15.01.2027 — дата должна быть в будущем (не дальше 3 лет).",
            reply_markup=get_cancel_inline_keyboard(),
        )
        return MedicationStates.WAIT_PAUSE_DATE
    await _show_wizard_step(
        update,
        context,
        _pause_notice_question(until),
        reply_markup=_pause_notice_keyboard(medication_id, until, today),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def medication_resume_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """End the break now."""
    query = update.callback_query
    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        user_timezone = await _get_user_timezone(update, session)
        medication = await MedicationService(session).resume_course(medication_id, user_id, user_timezone)
        await session.commit()
    if not medication:
        await query.answer()
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END
    await query.answer("Курс возобновлён")
    text, keyboard = await _render_medication_view(medication_id, user_id, user_timezone)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def medication_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for medication delete confirmation."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    await query.edit_message_text(
        "Удалить лекарство из активного списка?\n\nИстория отметок останется в базе.",
        reply_markup=get_medication_delete_confirm_keyboard(medication_id),
    )
    return ConversationHandler.END


async def medication_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Archive medication."""
    query = update.callback_query
    await query.answer()

    medication_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = MedicationService(session)
        deleted = await service.archive_medication(medication_id, user_id)
        await session.commit()

    if not deleted:
        await query.edit_message_text("❌ Лекарство не найдено", reply_markup=get_back_home_inline_keyboard("medications_list"))
        return ConversationHandler.END

    text, keyboard = await _render_medications_page(user_id, page=0)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current medication operation."""
    saved_id = context.user_data.get("med_saved_id")
    if saved_id:
        # «Отмена» while creating = do not keep the half-made medication.
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            await MedicationService(session).archive_medication(saved_id, user_id)
            await session.commit()
    if update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.edit_message_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard("medications_list"),
        )
    else:
        await update.message.reply_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard("medications_list"),
        )
    context.user_data.clear()
    return ConversationHandler.END


medication_create_conv = ConversationHandler(
    conversation_timeout=WIZARD_TIMEOUT_SECONDS,
    allow_reentry=True,
    entry_points=[CallbackQueryHandler(medication_create_start, pattern="^med_create$")],
    states={
        MedicationStates.WAIT_NAME: [
            MessageHandler(TEXT_INPUT, medication_save_name),
        ],
        MedicationStates.WAIT_DOSAGE: [
            CallbackQueryHandler(medication_dosage_preset_callback, pattern="^med_dosage:"),
            MessageHandler(TEXT_INPUT, medication_save_dosage),
        ],
        MedicationStates.WAIT_INSTRUCTIONS: [
            CallbackQueryHandler(medication_instructions_preset_callback, pattern="^med_instr:"),
            MessageHandler(TEXT_INPUT, medication_save_instructions),
        ],
        MedicationStates.WAIT_IMPORTANCE: [
            CallbackQueryHandler(medication_importance_callback, pattern="^med_importance:"),
            MessageHandler(TEXT_INPUT, medication_importance_text),
        ],
    },
    fallbacks=[
        *exit_fallbacks(),
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
        *leave_wizard_fallbacks(),
    ],
)


medication_edit_conv = ConversationHandler(
    conversation_timeout=WIZARD_TIMEOUT_SECONDS,
    allow_reentry=True,
    entry_points=[
        CallbackQueryHandler(medication_edit_name_start, pattern="^med_edit_name:"),
        CallbackQueryHandler(medication_edit_dosage_start, pattern="^med_edit_dosage:"),
        CallbackQueryHandler(medication_edit_instructions_start, pattern="^med_edit_instr:"),
    ],
    states={
        MedicationStates.WAIT_EDIT_NAME: [
            MessageHandler(TEXT_INPUT, medication_edit_name_save),
        ],
        MedicationStates.WAIT_EDIT_DOSAGE: [
            CallbackQueryHandler(medication_edit_dosage_value_callback, pattern="^med_edit_dosage_value:"),
            MessageHandler(TEXT_INPUT, medication_edit_dosage_save),
        ],
        MedicationStates.WAIT_EDIT_INSTRUCTIONS: [
            CallbackQueryHandler(medication_edit_instructions_value_callback, pattern="^med_edit_instr_value:"),
            MessageHandler(TEXT_INPUT, medication_edit_instructions_save),
        ],
    },
    fallbacks=[
        *exit_fallbacks(),
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
        *leave_wizard_fallbacks(),
    ],
)


medication_pause_conv = ConversationHandler(
    conversation_timeout=WIZARD_TIMEOUT_SECONDS,
    allow_reentry=True,
    entry_points=[CallbackQueryHandler(medication_pause_custom_start, pattern=r"^med_pause_custom:\d+$")],
    states={
        MedicationStates.WAIT_PAUSE_DATE: [MessageHandler(TEXT_INPUT, medication_pause_custom_save)],
    },
    fallbacks=[
        *exit_fallbacks(),
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
        *leave_wizard_fallbacks(),
    ],
)


medication_reminder_conv = ConversationHandler(
    conversation_timeout=WIZARD_TIMEOUT_SECONDS,
    allow_reentry=True,
    entry_points=[
        CallbackQueryHandler(medication_reminder_frequency_callback, pattern="^med_rem_freq:"),
        CallbackQueryHandler(medication_reminder_custom_start, pattern="^med_rem_custom:"),
    ],
    states={
        MedicationStates.WAIT_REMINDER_TIME: [
            MessageHandler(TEXT_INPUT, medication_reminder_custom_save),
        ],
    },
    fallbacks=[
        *exit_fallbacks(),
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
        *leave_wizard_fallbacks(),
    ],
)
