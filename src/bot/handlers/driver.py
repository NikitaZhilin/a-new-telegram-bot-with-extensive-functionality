"""Driver assistant handlers."""

import logging
import re
from datetime import date, datetime, time, timezone

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from sqlalchemy import func, select

from src.bot.keyboards import (
    get_back_home_inline_keyboard,
    get_driver_fuel_delete_confirm_keyboard,
    get_driver_fuel_entry_keyboard,
    get_driver_fuel_history_keyboard,
    get_driver_fuel_keyboard,
    get_driver_full_tank_keyboard,
    get_driver_menu_keyboard,
    get_driver_document_delete_confirm_keyboard,
    get_driver_document_remind_keyboard,
    get_driver_document_type_keyboard,
    get_driver_document_view_keyboard,
    get_driver_documents_keyboard,
    get_driver_expense_category_keyboard,
    get_driver_expense_delete_confirm_keyboard,
    get_driver_expense_view_keyboard,
    get_driver_expenses_keyboard,
    get_driver_section_keyboard,
    get_driver_service_keyboard,
    get_driver_step_keyboard,
    get_driver_templates_keyboard,
    get_driver_vehicle_choice_keyboard,
    get_driver_vehicle_delete_confirm_keyboard,
    get_driver_vehicle_preset_confirm_keyboard,
    get_driver_vehicle_preset_keyboard,
    get_driver_vehicle_view_keyboard,
    get_driver_vehicles_keyboard,
)
from src.db.models import Reminder, ReminderStatus, TodoList
from src.bot.states import DriverStates
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.driver_service import DriverService
from src.services.list_service import ListService
from src.services.vehicle_presets import get_vehicle_preset, list_vehicle_presets

logger = logging.getLogger(__name__)

FUEL_PAGE_SIZE = 8

DRIVER_MENU_TEXT = (
    "🚗 Для водителя\n\n"
    "Автомобильный журнал: пробег, топливо, ТО, запчасти, документы и регулярный уход.\n\n"
    "Выберите раздел:"
)


def _format_driver_menu_text(
    overview: dict,
    driver_lists_count: int = 0,
    active_driver_reminders_count: int = 0,
) -> str:
    """Build driver hub text with an autonomous domain summary."""
    lines = [
        "🚗 Для водителя",
        "",
        "Автомобильный журнал: пробег, топливо, ТО, запчасти, документы и регулярный уход.",
        "",
        "Краткая сводка:",
        f"• авто: {overview['vehicles_count']}",
        f"• заправок: {overview['fuel_entries_count']}",
        f"• топливо: {_format_money(overview['fuel_total_cost'])}",
        f"• прочие расходы: {_format_money(overview.get('expense_total_cost', 0))}",
        f"• документов: {overview.get('documents_active_count', 0)}",
        f"• авто-списков: {driver_lists_count}",
        f"• авто-напоминаний: {active_driver_reminders_count}",
    ]
    if overview["avg_consumption"] is not None:
        lines.append(f"• средний расход: {overview['avg_consumption']:.1f} л/100 км")
    lines.extend(["", "Выберите раздел:"])
    return "\n".join(lines)

DRIVER_LIST_TEMPLATES = {
    "parts": (
        "🚗 Запчасти к покупке",
        [
            "Моторное масло",
            "Масляный фильтр",
            "Воздушный фильтр",
            "Салонный фильтр",
            "Щетки стеклоочистителя",
            "Омывающая жидкость",
        ],
    ),
    "trip_check": (
        "🚗 Проверка перед поездкой",
        [
            "Проверить давление в шинах",
            "Проверить уровень масла",
            "Проверить антифриз",
            "Долить омывайку",
            "Проверить свет",
            "Проверить документы",
        ],
    ),
    "fluids_check": (
        "💧 Проверка жидкостей",
        [
            "Моторное масло",
            "Антифриз",
            "Тормозная жидкость",
            "Омывайка",
            "Жидкость ГУР",
            "Масло АКПП/МКПП при необходимости",
        ],
    ),
}

DRIVER_REMINDER_TEMPLATES = {
    "oil": "Заменить моторное масло и масляный фильтр",
    "fluids": "Проверить уровни жидкостей: масло, антифриз, тормозная, омывайка",
    "wash": "Помыть кузов и убрать салон",
    "tire_pressure": "Проверить давление в шинах",
    "service": "Запланировать прохождение ТО",
}

DRIVER_SECTIONS = {
    "maintenance": (
        "🔧 ТО и регламент",
        [
            "последнее ТО и следующий срок",
            "контроль по пробегу и по дате",
            "быстрая отметка выполненного ТО",
        ],
    ),
    "fluids": (
        "💧 Проверка жидкостей",
        [
            "моторное масло",
            "антифриз",
            "тормозная жидкость",
            "омывайка",
            "жидкость ГУР и трансмиссионные жидкости при необходимости",
        ],
    ),
    "parts": (
        "🛒 Запчасти к покупке",
        [
            "артикул, бренд, количество и ссылка",
            "приоритет: срочно, планово, позже",
            "статусы: нужно купить, заказано, получено, установлено",
        ],
    ),
    "wash": (
        "🧼 Мойка и уборка",
        [
            "регулярная мойка кузова",
            "уборка салона",
            "зимние напоминания после реагентов",
        ],
    ),
    "tires": (
        "🛞 Шины",
        [
            "сезонная замена резины",
            "давление и износ протектора",
            "балансировка и сход-развал",
        ],
    ),
    "docs": (
        "📄 Документы и платежи",
        [
            "ОСАГО/КАСКО",
            "диагностическая карта",
            "водительское удостоверение",
            "налоги и штрафы",
        ],
    ),
    "costs": (
        "💰 Расходы",
        [
            "топливо, ремонт, ТО, мойка, запчасти, страховка",
            "стоимость владения",
            "средняя стоимость километра",
        ],
    ),
    "stats": (
        "📊 Статистика",
        [
            "динамика пробега",
            "средний расход топлива",
            "что скоро нужно обслужить или купить",
        ],
    ),
}

DRIVER_CONTEXT_KEYS = {
    "driver_vehicle_mode",
    "driver_vehicle_id",
    "driver_vehicle_data",
    "driver_mileage_vehicle_id",
    "driver_fuel_mode",
    "driver_fuel_vehicle_id",
    "driver_fuel_entry_id",
    "driver_fuel_data",
    "driver_service_vehicle_id",
    "driver_expense_mode",
    "driver_expense_id",
    "driver_expense_data",
    "driver_document_mode",
    "driver_document_id",
    "driver_document_data",
}


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID, creating user when needed."""
    repo = UserRepository(session)
    telegram_user = update.effective_user
    user = await repo.get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )
    await session.commit()
    return user.id


def _parse_callback_id(data: str, index: int = 1) -> int:
    """Parse a numeric callback part."""
    return int(data.split(":")[index])


def _parse_int(value: str, field_name: str, allow_zero: bool = True) -> int:
    """Parse integer from user input."""
    cleaned = value.strip().replace(" ", "")
    if not cleaned.isdigit():
        raise ValueError(field_name)
    parsed = int(cleaned)
    if parsed < 0 or (parsed == 0 and not allow_zero):
        raise ValueError(field_name)
    return parsed


def _parse_float(value: str, field_name: str) -> float:
    """Parse decimal number from user input."""
    cleaned = value.strip().replace(" ", "").replace(",", ".")
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(field_name) from exc
    if parsed <= 0:
        raise ValueError(field_name)
    return parsed


def _parse_bool(value: str) -> bool:
    """Parse yes/no full tank input."""
    normalized = value.strip().lower()
    yes_values = {"да", "yes", "y", "1", "полный", "полная", "full", "true", "+"}
    no_values = {"нет", "no", "n", "0", "частично", "неполный", "неполная", "partial", "false", "-"}
    if normalized in yes_values:
        return True
    if normalized in no_values:
        return False
    raise ValueError("полный бак")


def _limit_text(value: str, max_length: int) -> str:
    """Trim user text so it cannot overflow database columns."""
    return value.strip()[:max_length]


def _format_money(value: float) -> str:
    """Format ruble values compactly."""
    return f"{value:.0f} ₽" if value >= 100 else f"{value:.2f} ₽"


def _fuel_type_label(value: str | None) -> str:
    """Human-readable fuel type."""
    return {
        "petrol": "бензин",
        "diesel": "дизель",
        "hybrid": "гибрид",
        "electric": "электро",
        "lpg": "газ",
    }.get(value or "", value or "не указано")


def _transmission_label(value: str | None) -> str:
    """Human-readable transmission type."""
    return {
        "manual": "МКПП",
        "automatic": "АКПП",
        "robot": "робот",
        "cvt": "вариатор",
    }.get(value or "", value or "не указано")


def _drive_type_label(value: str | None) -> str:
    """Human-readable drive type."""
    return {
        "fwd": "передний",
        "rwd": "задний",
        "awd": "полный",
    }.get(value or "", value or "не указано")


def _format_consumption(
    city: float | None,
    highway: float | None,
    mixed: float | None,
) -> str:
    """Format expected vehicle fuel consumption."""
    parts = []
    if city is not None:
        parts.append(f"город {city:.1f}")
    if highway is not None:
        parts.append(f"трасса {highway:.1f}")
    if mixed is not None:
        parts.append(f"смешанный {mixed:.1f}")
    if not parts:
        return "не указан"
    return ", ".join(parts) + " л/100 км"


def _format_preset_details(preset) -> str:
    """Format curated vehicle preset for confirmation screens."""
    lines = [
        f"🚗 {preset.label}",
        "",
        f"Марка/модель: {preset.make} {preset.model}",
        f"Кузов: {preset.body_type}",
        f"Год: {preset.year if preset.year else 'уточняется вручную'}",
        f"Двигатель: {preset.engine_volume_l:.1f} л"
        + (f", {preset.engine_power_hp} л.с." if preset.engine_power_hp else ""),
        f"Топливо: {_fuel_type_label(preset.fuel_type)}",
        f"Коробка/привод: {_transmission_label(preset.transmission)} / {_drive_type_label(preset.drive_type)}",
        "Ориентир расхода: "
        f"{_format_consumption(preset.consumption_city_l_per_100, preset.consumption_highway_l_per_100, preset.consumption_mixed_l_per_100)}",
        "",
        preset.note,
    ]
    return "\n".join(lines)


def _format_date(value: datetime | None) -> str:
    """Format UTC datetime for compact bot output."""
    if not value:
        return "не указано"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d.%m.%Y")


def _parse_date(value: str) -> datetime:
    """Parse a simple date and store it as UTC noon."""
    raw = value.strip().replace("/", ".").replace("-", ".")
    today = datetime.now(timezone.utc).date()
    match = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?", raw)
    if not match:
        raise ValueError("date")
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3)) if match.group(3) else today.year
    if year < 100:
        year += 2000
    parsed = date(year, month, day)
    if parsed < today and not match.group(3):
        parsed = date(year + 1, month, day)
    return datetime.combine(parsed, time(hour=12), tzinfo=timezone.utc)


def _status_text(status: str) -> str:
    """Human-readable service status."""
    return {
        "overdue": "пора сделать",
        "soon": "скоро",
        "ok": "в норме",
        "unknown": "нет данных",
    }.get(status, "нет данных")


async def _delete_user_message(update: Update) -> None:
    """Best-effort cleanup for user text inputs."""
    if not update.message:
        return
    try:
        await update.message.delete()
    except Exception:
        logger.debug("Could not delete driver user input", exc_info=True)


def _remember_wizard_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    """Remember current driver wizard message for later edits."""
    context.user_data["driver_wizard_chat_id"] = chat_id
    context.user_data["driver_wizard_message_id"] = message_id


async def _show_driver_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit current driver wizard message when possible, otherwise send a new one."""
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(text, reply_markup=reply_markup)
        _remember_wizard_message(context, query.message.chat_id, query.message.message_id)
        return

    chat_id = context.user_data.get("driver_wizard_chat_id")
    message_id = context.user_data.get("driver_wizard_message_id")
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
            logger.debug("Could not edit driver wizard message", exc_info=True)

    message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
    )
    _remember_wizard_message(context, message.chat_id, message.message_id)


def _clear_driver_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove driver flow data without touching unrelated bot state."""
    for key in list(context.user_data):
        if key.startswith("driver_"):
            context.user_data.pop(key, None)


def _format_section_text(section_key: str) -> str:
    """Build text for a driver subsection."""
    title, items = DRIVER_SECTIONS[section_key]
    lines = [title, ""]
    lines.append("Это раздел-шаблон: пока он помогает быстро создать список или напоминание.")
    lines.append("")
    lines.extend(f"• {item}" for item in items)
    lines.extend(["", "Для быстрых действий можно создать список или обычное напоминание."])
    return "\n".join(lines)


def _format_vehicle(vehicle) -> str:
    """Format vehicle profile."""
    lines = [
        f"🚗 {vehicle.title}",
        "",
        f"Пробег: {vehicle.current_mileage_km:,} км".replace(",", " "),
        f"Интервал ТО: {vehicle.service_interval_km:,} км / {vehicle.service_interval_months} мес.".replace(",", " "),
    ]
    if vehicle.make or vehicle.model or vehicle.body_type or vehicle.engine_volume_l:
        lines.append("")
        lines.append("Параметры:")
        make_model = " ".join(part for part in [vehicle.make, vehicle.model] if part)
        if make_model:
            if vehicle.year:
                make_model += f", {vehicle.year}"
            lines.append(f"• {make_model}")
        if vehicle.body_type:
            lines.append(f"• кузов: {vehicle.body_type}")
        if vehicle.engine_volume_l or vehicle.engine_power_hp:
            engine = f"{vehicle.engine_volume_l:.1f} л" if vehicle.engine_volume_l else "объем не указан"
            if vehicle.engine_power_hp:
                engine += f", {vehicle.engine_power_hp} л.с."
            lines.append(f"• двигатель: {engine}")
        if vehicle.fuel_type or vehicle.transmission or vehicle.drive_type:
            lines.append(
                "• топливо/КПП/привод: "
                f"{_fuel_type_label(vehicle.fuel_type)}, "
                f"{_transmission_label(vehicle.transmission)}, "
                f"{_drive_type_label(vehicle.drive_type)}"
            )
        if (
            vehicle.expected_consumption_city_l_per_100
            or vehicle.expected_consumption_highway_l_per_100
            or vehicle.expected_consumption_mixed_l_per_100
        ):
            lines.append(
                "• ориентир расхода: "
                f"{_format_consumption(vehicle.expected_consumption_city_l_per_100, vehicle.expected_consumption_highway_l_per_100, vehicle.expected_consumption_mixed_l_per_100)}"
            )
        if vehicle.vehicle_specs_note:
            lines.append(f"• примечание: {vehicle.vehicle_specs_note}")
    if vehicle.last_service_mileage_km is not None or vehicle.last_service_at_utc is not None:
        lines.append("")
        lines.append(
            "Последнее ТО: "
            f"{vehicle.last_service_mileage_km or 'не указан'} км, "
            f"{_format_date(vehicle.last_service_at_utc)}"
        )
    return "\n".join(lines)


def _format_service_plan(plan: dict) -> str:
    """Format regular service plan."""
    vehicle = plan["vehicle"]
    lines = [f"🔧 ТО: {vehicle.title}", ""]
    lines.append(f"Текущий пробег: {vehicle.current_mileage_km:,} км".replace(",", " "))
    lines.append(f"Интервал: {vehicle.service_interval_km:,} км / {vehicle.service_interval_months} мес.".replace(",", " "))
    lines.append("")
    lines.append(
        "Последнее ТО: "
        f"{vehicle.last_service_mileage_km or 'не указано'} км, "
        f"{_format_date(vehicle.last_service_at_utc)}"
    )

    if plan["next_mileage"] is None:
        lines.append("По пробегу: отметьте первое ТО, и я рассчитаю следующий срок.")
    else:
        remaining = plan["remaining_km"]
        if remaining is not None and remaining >= 0:
            lines.append(
                f"Следующее ТО по пробегу: {plan['next_mileage']:,} км, осталось {remaining:,} км "
                f"({_status_text(plan['mileage_status'])})".replace(",", " ")
            )
        else:
            lines.append(
                f"Следующее ТО по пробегу: {plan['next_mileage']:,} км, перепробег {abs(remaining):,} км "
                f"({_status_text(plan['mileage_status'])})".replace(",", " ")
            )

    if plan["next_date"] is None:
        lines.append("По дате: отметьте первое ТО, и я рассчитаю следующий срок.")
    else:
        days_left = plan["days_left"]
        if days_left is not None and days_left >= 0:
            lines.append(
                f"Следующее ТО по дате: {_format_date(plan['next_date'])}, осталось {days_left} дн. "
                f"({_status_text(plan['date_status'])})"
            )
        else:
            lines.append(
                f"Следующее ТО по дате: {_format_date(plan['next_date'])}, просрочено на {abs(days_left)} дн. "
                f"({_status_text(plan['date_status'])})"
            )

    return "\n".join(lines)


def _format_fuel_entry(entry) -> str:
    """Format one fuel entry."""
    lines = [
        "⛽ Заправка",
        "",
        f"Пробег: {entry.mileage_km:,} км".replace(",", " "),
        f"Топливо: {entry.liters:.2f} л",
        f"Сумма: {_format_money(entry.total_cost)}",
        f"Цена: {entry.price_per_liter:.2f} ₽/л" if entry.price_per_liter else "Цена: не рассчитана",
        f"Бак: {'полный' if entry.is_full_tank else 'неполный'}",
    ]
    if entry.station:
        lines.append(f"АЗС: {entry.station}")
    if entry.consumption_l_per_100 is not None:
        lines.append(f"Расход: {entry.consumption_l_per_100:.1f} л/100 км")
        lines.append(f"Стоимость: {entry.cost_per_km:.2f} ₽/км")
    elif not entry.is_full_tank:
        lines.append("Неполная заправка будет учтена при следующем полном баке.")
    else:
        lines.append("Расход появится после следующего полного бака.")
    return "\n".join(lines)


def _format_expense_category(value: str) -> str:
    """Human-readable expense category."""
    return {
        "service": "ТО и ремонт",
        "parts": "запчасти",
        "wash": "мойка",
        "insurance": "страховка",
        "parking": "парковка",
        "fine": "штраф",
        "other": "другое",
    }.get(value, value or "другое")


def _format_document_type(value: str) -> str:
    """Human-readable document type."""
    return {
        "insurance": "ОСАГО/КАСКО",
        "license": "права",
        "diagnostic": "диагностика",
        "tax": "налог",
        "fine": "штраф",
        "other": "другое",
    }.get(value, value or "другое")


def _format_expense(entry, vehicle_title: str | None = None) -> str:
    """Format one manual driver expense."""
    lines = [
        f"💰 {entry.title}",
        "",
        f"Сумма: {_format_money(entry.amount)}",
        f"Категория: {_format_expense_category(entry.category)}",
        f"Дата: {_format_date(entry.spent_at_utc)}",
    ]
    if vehicle_title:
        lines.append(f"Авто: {vehicle_title}")
    elif entry.vehicle_id:
        lines.append("Авто: привязано")
    else:
        lines.append("Авто: без привязки")
    if entry.note:
        lines.extend(["", entry.note])
    return "\n".join(lines)


def _format_document(document, vehicle_title: str | None = None) -> str:
    """Format one driver document."""
    lines = [
        f"📄 {document.title}",
        "",
        f"Тип: {_format_document_type(document.document_type)}",
        f"Статус: {'активен' if document.is_active else 'архив'}",
        f"Срок: {_format_date(document.expires_at_utc) if document.expires_at_utc else 'не указан'}",
        f"Напомнить за: {document.remind_before_days} дн.",
    ]
    if vehicle_title:
        lines.append(f"Авто: {vehicle_title}")
    elif document.vehicle_id:
        lines.append("Авто: привязано")
    else:
        lines.append("Авто: без привязки")
    if document.identifier:
        lines.append(f"Номер/пометка: {document.identifier}")
    if document.note:
        lines.extend(["", document.note])
    return "\n".join(lines)


async def _render_vehicles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render vehicle profiles."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicles = await DriverService(session).get_vehicles(user_id)

    if vehicles:
        lines = ["🚗 Авто", ""]
        for vehicle in vehicles:
            lines.append(f"• {vehicle.title} — {vehicle.current_mileage_km:,} км".replace(",", " "))
        text = "\n".join(lines)
    else:
        text = "🚗 Авто\n\nПрофилей пока нет. Добавьте машину, чтобы вести пробег, ТО и заправки."

    query = update.callback_query
    if query:
        await query.edit_message_text(text, reply_markup=get_driver_vehicles_keyboard(vehicles))
    else:
        await update.message.reply_text(text, reply_markup=get_driver_vehicles_keyboard(vehicles))
    return ConversationHandler.END


async def _render_fuel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render fuel journal summary."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        vehicles = await service.get_vehicles(user_id)
        entries = await service.get_fuel_entries(user_id, limit=5)
        summary = await service.get_fuel_summary(user_id)

    lines = ["⛽ Топливо и расход", ""]
    if not vehicles:
        lines.append("Сначала добавьте авто.")
    elif not entries:
        lines.append("Заправок пока нет. Добавьте первую запись из карточки авто.")
    else:
        lines.append(f"Заправок: {summary['count']}")
        lines.append(f"Всего потрачено: {_format_money(summary['total_cost'])}")
        if summary["avg_consumption"] is not None:
            lines.append(f"Средний расход: {summary['avg_consumption']:.1f} л/100 км")
        if summary["avg_cost_per_km"] is not None:
            lines.append(f"Средняя стоимость: {summary['avg_cost_per_km']:.2f} ₽/км")
        if summary["avg_consumption"] is None:
            lines.append("Расход появится после двух полных заправок.")
        lines.append("")
        lines.append("Последние записи:")
        for entry in entries:
            fuel_line = (
                f"• {entry.mileage_km:,} км: {entry.liters:.2f} л, "
                f"{_format_money(entry.total_cost)}"
            ).replace(",", " ")
            if entry.consumption_l_per_100 is not None:
                fuel_line += f", {entry.consumption_l_per_100:.1f} л/100 км"
            elif not entry.is_full_tank:
                fuel_line += ", неполный бак"
            lines.append(fuel_line)

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_driver_fuel_keyboard(vehicles),
    )
    return ConversationHandler.END


async def _render_fuel_history(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    vehicle_id: int,
    page: int = 0,
) -> int:
    """Render fuel history for one vehicle."""
    page = max(0, page)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        vehicle = await service.get_vehicle(vehicle_id, user_id)
        if not vehicle:
            await update.callback_query.edit_message_text(
                "❌ Авто не найдено",
                reply_markup=get_back_home_inline_keyboard(),
            )
            return ConversationHandler.END

        total = await service.count_fuel_entries(user_id, vehicle_id)
        entries = await service.get_fuel_entries(
            user_id,
            vehicle_id=vehicle_id,
            limit=FUEL_PAGE_SIZE,
            offset=page * FUEL_PAGE_SIZE,
        )
        summary = await service.get_fuel_summary(user_id, vehicle_id)

    if not entries and page > 0:
        return await _render_fuel_history(update, context, vehicle_id, page - 1)

    lines = [f"📜 Заправки: {vehicle.title}", ""]
    if not entries:
        lines.append("Записей пока нет.")
    else:
        total_pages = max(1, (total + FUEL_PAGE_SIZE - 1) // FUEL_PAGE_SIZE)
        lines.append(f"Всего записей: {total}")
        lines.append(f"Страница {page + 1}/{total_pages}")
        lines.append(f"Сумма: {_format_money(summary['total_cost'])}")
        if summary["avg_consumption"] is not None:
            lines.append(f"Средний расход: {summary['avg_consumption']:.1f} л/100 км")

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_driver_fuel_history_keyboard(
            vehicle_id,
            entries,
            page=page,
            has_next=(page + 1) * FUEL_PAGE_SIZE < total,
        ),
    )
    return ConversationHandler.END


async def _render_driver_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render real driver cost overview based on fuel and manual expenses."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        overview = await service.get_user_overview(user_id)
        expenses = await service.get_expenses(user_id, limit=10)

    lines = [
        "💰 Расходы",
        "",
        f"Авто: {overview['vehicles_count']}",
        f"Заправок: {overview['fuel_entries_count']}",
        f"Топливо: {_format_money(overview['fuel_total_cost'])}",
        f"Прочие расходы: {_format_money(overview.get('expense_total_cost', 0))}",
        f"Всего по авто: {_format_money(overview.get('driver_total_cost', overview['fuel_total_cost']))}",
    ]
    if overview["avg_cost_per_km"] is not None:
        lines.append(f"Средняя стоимость километра: {overview['avg_cost_per_km']:.2f} ₽/км")
    else:
        lines.append("Стоимость километра появится после двух полных заправок.")
    if expenses:
        lines.extend(["", "Последние ручные расходы:"])
        for item in expenses:
            lines.append(
                f"• {_format_date(item.spent_at_utc)}: {item.title}, "
                f"{_format_money(item.amount)} ({_format_expense_category(item.category)})"
            )
    else:
        lines.extend(["", "Ручных расходов пока нет. Добавьте первый расход кнопкой ниже."])

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_driver_expenses_keyboard(expenses),
    )
    return ConversationHandler.END


async def _render_driver_documents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render real driver documents."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        overview = await service.get_user_overview(user_id)
        documents = await service.get_documents(user_id, active_only=False, limit=20)

    lines = [
        "📄 Документы",
        "",
        f"Активных документов: {overview.get('documents_active_count', 0)}",
        f"Скоро истекают: {overview.get('documents_expiring_soon_count', 0)}",
        f"Просрочены: {overview.get('documents_expired_count', 0)}",
    ]
    if documents:
        lines.extend(["", "Документы:"])
        for item in documents:
            expires = _format_date(item.expires_at_utc) if item.expires_at_utc else "срок не указан"
            status = "активен" if item.is_active else "архив"
            lines.append(
                f"• {item.title}: {_format_document_type(item.document_type)}, "
                f"{expires}, {status}"
            )
    else:
        lines.extend(["", "Документов пока нет. Добавьте первый документ кнопкой ниже."])

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_driver_documents_keyboard(documents),
    )
    return ConversationHandler.END


async def _render_driver_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Render real driver statistics from vehicles and fuel history."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        overview = await service.get_user_overview(user_id)
        vehicles = await service.get_vehicles(user_id)

    lines = [
        "📊 Статистика",
        "",
        f"Авто: {overview['vehicles_count']}",
        f"Максимальный пробег: {overview['max_mileage_km']:,} км".replace(",", " "),
        f"Заправок: {overview['fuel_entries_count']}",
        f"Топливо: {_format_money(overview['fuel_total_cost'])}",
        f"Прочие расходы: {_format_money(overview.get('expense_total_cost', 0))}",
        f"Документы: {overview.get('documents_active_count', 0)}",
    ]
    if overview["avg_consumption"] is not None:
        lines.append(f"Средний расход: {overview['avg_consumption']:.1f} л/100 км")
    else:
        lines.append("Средний расход появится после двух полных заправок.")
    if overview["avg_cost_per_km"] is not None:
        lines.append(f"Средняя стоимость: {overview['avg_cost_per_km']:.2f} ₽/км")

    due_lines = []
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        for vehicle in vehicles:
            plan = await service.get_service_plan(vehicle.id, user_id)
            if plan and (plan["mileage_status"] in {"soon", "overdue"} or plan["date_status"] in {"soon", "overdue"}):
                due_lines.append(f"• {vehicle.title}: ТО {_status_text(plan['mileage_status'])}/{_status_text(plan['date_status'])}")

    if due_lines:
        lines.extend(["", "Ближайшее ТО:"])
        lines.extend(due_lines)

    await update.callback_query.edit_message_text(
        "\n".join(lines),
        reply_markup=get_driver_section_keyboard(),
    )
    return ConversationHandler.END


async def driver_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show the driver assistant hub."""
    query = update.callback_query
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        overview = await DriverService(session).get_user_overview(user_id)
        driver_lists_count = (
            await session.execute(
                select(func.count(TodoList.id)).where(
                    TodoList.user_id == user_id,
                    TodoList.source_module == "driver",
                )
            )
        ).scalar() or 0
        active_driver_reminders_count = (
            await session.execute(
                select(func.count(Reminder.id)).where(
                    Reminder.user_id == user_id,
                    Reminder.source_module == "driver",
                    Reminder.status == ReminderStatus.ACTIVE,
                )
            )
        ).scalar() or 0

    text = _format_driver_menu_text(
        overview,
        driver_lists_count=driver_lists_count,
        active_driver_reminders_count=active_driver_reminders_count,
    )

    if query:
        await query.answer()
        await query.edit_message_text(text, reply_markup=get_driver_menu_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=get_driver_menu_keyboard())
    return ConversationHandler.END


async def driver_section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one driver assistant section."""
    query = update.callback_query
    await query.answer()

    section_key = query.data.split(":", 1)[1]
    if section_key == "templates":
        await query.edit_message_text(
            "⚡ Шаблоны\n\nСоздайте готовый список или начните напоминание с уже заполненным текстом.",
            reply_markup=get_driver_templates_keyboard(),
        )
        return ConversationHandler.END
    if section_key == "vehicles":
        return await _render_vehicles(update, context)
    if section_key == "fuel":
        return await _render_fuel(update, context)
    if section_key == "costs":
        return await _render_driver_costs(update, context)
    if section_key == "docs":
        return await _render_driver_documents(update, context)
    if section_key == "stats":
        return await _render_driver_stats(update, context)
    if section_key not in DRIVER_SECTIONS:
        await query.edit_message_text(DRIVER_MENU_TEXT, reply_markup=get_driver_menu_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_section_text(section_key),
        reply_markup=get_driver_section_keyboard(),
    )
    return ConversationHandler.END


async def driver_list_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create a ready-made list from a driver template."""
    query = update.callback_query
    await query.answer()

    template_key = query.data.split(":", 1)[1]
    template = DRIVER_LIST_TEMPLATES.get(template_key)
    if not template:
        await query.edit_message_text("❌ Шаблон не найден", reply_markup=get_driver_templates_keyboard())
        return ConversationHandler.END

    title, items = template
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ListService(session)
        list_obj = await service.create_list(user_id, title, source_module="driver")
        await service.add_items_bulk(list_obj.id, user_id, items)
        await session.commit()

    await query.edit_message_text(
        f"✅ Список создан\n\n📋 {title}\nПунктов: {len(items)}",
        reply_markup=get_back_home_inline_keyboard(),
    )
    return ConversationHandler.END


async def driver_vehicle_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show vehicle profile."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_vehicle(vehicle),
        reply_markup=get_driver_vehicle_view_keyboard(vehicle.id),
    )
    return ConversationHandler.END


async def driver_vehicle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for vehicle deletion confirmation."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        f"Удалить авто «{vehicle.title}»?\n\nЗаправки и данные ТО по этому авто тоже будут удалены.",
        reply_markup=get_driver_vehicle_delete_confirm_keyboard(vehicle_id),
    )
    return ConversationHandler.END


async def driver_vehicle_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete vehicle after confirmation."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        deleted = await DriverService(session).delete_vehicle(vehicle_id, user_id)
        await session.commit()

    if not deleted:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    return await _render_vehicles(update, context)


async def driver_fuel_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show fuel history for one vehicle."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    vehicle_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0
    return await _render_fuel_history(update, context, vehicle_id, page)


async def driver_fuel_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one fuel entry."""
    query = update.callback_query
    await query.answer()
    entry_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        entry = await DriverService(session).get_fuel_entry(entry_id, user_id)

    if not entry:
        await query.edit_message_text("❌ Заправка не найдена", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_fuel_entry(entry),
        reply_markup=get_driver_fuel_entry_keyboard(entry.id, entry.vehicle_id),
    )
    return ConversationHandler.END


async def driver_fuel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for fuel entry deletion confirmation."""
    query = update.callback_query
    await query.answer()
    entry_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        entry = await DriverService(session).get_fuel_entry(entry_id, user_id)

    if not entry:
        await query.edit_message_text("❌ Заправка не найдена", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        "Удалить эту заправку?\n\nПосле удаления расход по истории будет пересчитан.",
        reply_markup=get_driver_fuel_delete_confirm_keyboard(entry.id, entry.vehicle_id),
    )
    return ConversationHandler.END


async def driver_fuel_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete fuel entry after confirmation."""
    query = update.callback_query
    await query.answer()
    entry_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        entry = await service.get_fuel_entry(entry_id, user_id)
        if not entry:
            await query.edit_message_text("❌ Заправка не найдена", reply_markup=get_back_home_inline_keyboard())
            return ConversationHandler.END
        vehicle_id = entry.vehicle_id
        await service.delete_fuel_entry(entry_id, user_id)
        await session.commit()

    return await _render_fuel_history(update, context, vehicle_id, page=0)


async def driver_service_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show vehicle service plan."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        plan = await DriverService(session).get_service_plan(vehicle_id, user_id)

    if not plan:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_service_plan(plan),
        reply_markup=get_driver_service_keyboard(vehicle_id),
    )
    return ConversationHandler.END


async def driver_expense_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one manual driver expense."""
    query = update.callback_query
    await query.answer()
    expense_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        expense = await service.get_expense(expense_id, user_id)
        vehicle_title = None
        if expense and expense.vehicle_id:
            vehicle = await service.get_vehicle(expense.vehicle_id, user_id)
            vehicle_title = vehicle.title if vehicle else None

    if not expense:
        await query.edit_message_text("❌ Расход не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_expense(expense, vehicle_title),
        reply_markup=get_driver_expense_view_keyboard(expense.id),
    )
    return ConversationHandler.END


async def driver_expense_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask to confirm manual expense deletion."""
    query = update.callback_query
    await query.answer()
    expense_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        expense = await DriverService(session).get_expense(expense_id, user_id)

    if not expense:
        await query.edit_message_text("❌ Расход не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        "Удалить этот расход?\n\n" + _format_expense(expense),
        reply_markup=get_driver_expense_delete_confirm_keyboard(expense.id),
    )
    return ConversationHandler.END


async def driver_expense_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete manual expense after confirmation."""
    query = update.callback_query
    await query.answer()
    expense_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        await DriverService(session).delete_expense(expense_id, user_id)
        await session.commit()

    return await _render_driver_costs(update, context)


async def driver_document_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one driver document."""
    query = update.callback_query
    await query.answer()
    document_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        document = await service.get_document(document_id, user_id)
        vehicle_title = None
        if document and document.vehicle_id:
            vehicle = await service.get_vehicle(document.vehicle_id, user_id)
            vehicle_title = vehicle.title if vehicle else None

    if not document:
        await query.edit_message_text("❌ Документ не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        _format_document(document, vehicle_title),
        reply_markup=get_driver_document_view_keyboard(document.id),
    )
    return ConversationHandler.END


async def driver_document_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask to confirm driver document deletion."""
    query = update.callback_query
    await query.answer()
    document_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        document = await DriverService(session).get_document(document_id, user_id)

    if not document:
        await query.edit_message_text("❌ Документ не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        "Удалить этот документ?\n\n" + _format_document(document),
        reply_markup=get_driver_document_delete_confirm_keyboard(document.id),
    )
    return ConversationHandler.END


async def driver_document_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete driver document after confirmation."""
    query = update.callback_query
    await query.answer()
    document_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        await DriverService(session).delete_document(document_id, user_id)
        await session.commit()

    return await _render_driver_documents(update, context)


async def _ask_vehicle_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for vehicle title."""
    mode = context.user_data.get("driver_vehicle_mode", "create")
    data = context.user_data.setdefault("driver_vehicle_data", {})
    current = data.get("title")
    text = "🚗 Авто\n\nШаг 1/4. Введите название авто."
    if current:
        text += f"\n\nТекущее: {current}"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=mode == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_VEHICLE_TITLE


async def _ask_vehicle_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for quick vehicle preset or manual input."""
    await _show_driver_step(
        update,
        context,
        "🚗 Новое авто\n\nВыберите готовый вариант или введите автомобиль вручную.",
        get_driver_vehicle_preset_keyboard(list_vehicle_presets()),
    )
    return DriverStates.WAIT_VEHICLE_PRESET


def _apply_vehicle_preset_to_context(context: ContextTypes.DEFAULT_TYPE, slug: str) -> bool:
    """Put selected vehicle preset into FSM context."""
    preset = get_vehicle_preset(slug)
    if not preset:
        return False
    data = context.user_data.setdefault("driver_vehicle_data", {})
    data.update(
        {
            "title": preset.title,
            "service_interval_km": preset.service_interval_km,
            "service_interval_months": preset.service_interval_months,
            **preset.vehicle_kwargs(),
        }
    )
    context.user_data["driver_vehicle_preset_slug"] = slug
    return True


async def _ask_vehicle_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for current mileage."""
    data = context.user_data.setdefault("driver_vehicle_data", {})
    current = data.get("current_mileage_km")
    text = "🚗 Авто\n\nШаг 2/4. Укажите текущий пробег в км."
    if current is not None:
        text += f"\n\nТекущий вариант: {current} км"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=True, skip_text="Оставить" if current is not None else "Пропустить"),
    )
    return DriverStates.WAIT_VEHICLE_MILEAGE


async def _ask_vehicle_service_km(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for service interval by mileage."""
    data = context.user_data.setdefault("driver_vehicle_data", {})
    current = data.get("service_interval_km", 10000)
    await _show_driver_step(
        update,
        context,
        "🚗 Авто\n\nШаг 3/4. Через сколько километров обычно делать ТО?\n\n"
        f"Текущий вариант: {current} км",
        get_driver_step_keyboard(can_skip=True, skip_text="Оставить"),
    )
    return DriverStates.WAIT_VEHICLE_SERVICE_KM


async def _ask_vehicle_service_months(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for service interval by months."""
    data = context.user_data.setdefault("driver_vehicle_data", {})
    current = data.get("service_interval_months", 12)
    await _show_driver_step(
        update,
        context,
        "🚗 Авто\n\nШаг 4/4. Через сколько месяцев обычно делать ТО?\n\n"
        f"Текущий вариант: {current} мес.",
        get_driver_step_keyboard(can_skip=True, skip_text="Оставить"),
    )
    return DriverStates.WAIT_VEHICLE_SERVICE_MONTHS


async def driver_vehicle_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start vehicle creation."""
    query = update.callback_query
    await query.answer()
    _clear_driver_context(context)
    context.user_data["driver_vehicle_mode"] = "create"
    context.user_data["driver_vehicle_data"] = {
        "current_mileage_km": 0,
        "service_interval_km": 10000,
        "service_interval_months": 12,
    }
    return await _ask_vehicle_preset(update, context)


async def driver_vehicle_manual_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Continue vehicle creation with manual input."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_vehicle_data", {}).update(
        {
            "preset_slug": None,
            "make": None,
            "model": None,
            "year": None,
            "body_type": None,
            "engine_volume_l": None,
            "engine_power_hp": None,
            "fuel_type": None,
            "transmission": None,
            "drive_type": None,
            "expected_consumption_city_l_per_100": None,
            "expected_consumption_highway_l_per_100": None,
            "expected_consumption_mixed_l_per_100": None,
            "vehicle_specs_note": None,
        }
    )
    return await _ask_vehicle_title(update, context)


async def driver_vehicle_preset_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show selected vehicle preset before continuing."""
    query = update.callback_query
    await query.answer()
    slug = query.data.split(":", 1)[1]
    preset = get_vehicle_preset(slug)
    if not preset or not _apply_vehicle_preset_to_context(context, slug):
        await _show_driver_step(
            update,
            context,
            "❌ Не нашёл такой вариант авто. Выберите другой или введите вручную.",
            get_driver_vehicle_preset_keyboard(list_vehicle_presets()),
        )
        return DriverStates.WAIT_VEHICLE_PRESET

    await _show_driver_step(
        update,
        context,
        _format_preset_details(preset),
        get_driver_vehicle_preset_confirm_keyboard(),
    )
    return DriverStates.WAIT_VEHICLE_PRESET


async def driver_vehicle_preset_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm selected vehicle preset."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("driver_vehicle_data", {}).get("title"):
        return await _ask_vehicle_preset(update, context)
    return await _ask_vehicle_mileage(update, context)


async def driver_vehicle_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start vehicle editing."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    _clear_driver_context(context)
    context.user_data["driver_vehicle_mode"] = "edit"
    context.user_data["driver_vehicle_id"] = vehicle_id
    context.user_data["driver_vehicle_data"] = {
        "title": vehicle.title,
        "current_mileage_km": vehicle.current_mileage_km,
        "service_interval_km": vehicle.service_interval_km,
        "service_interval_months": vehicle.service_interval_months,
    }
    return await _ask_vehicle_title(update, context)


async def driver_vehicle_title_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save vehicle title."""
    title = _limit_text(update.message.text, 255)
    await _delete_user_message(update)
    if not title:
        await _ask_vehicle_title(update, context)
        return DriverStates.WAIT_VEHICLE_TITLE
    context.user_data.setdefault("driver_vehicle_data", {})["title"] = title
    return await _ask_vehicle_mileage(update, context)


async def driver_vehicle_title_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep current vehicle title while editing."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("driver_vehicle_data", {}).get("title"):
        return await _ask_vehicle_title(update, context)
    return await _ask_vehicle_mileage(update, context)


async def driver_vehicle_mileage_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save vehicle mileage in create/edit wizard."""
    try:
        mileage = _parse_int(update.message.text, "пробег")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(
            update,
            context,
            "Не понял пробег. Введите число, например 126500.",
            get_driver_step_keyboard(can_skip=True),
        )
        return DriverStates.WAIT_VEHICLE_MILEAGE

    await _delete_user_message(update)
    context.user_data.setdefault("driver_vehicle_data", {})["current_mileage_km"] = mileage
    return await _ask_vehicle_service_km(update, context)


async def driver_vehicle_mileage_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep current vehicle mileage."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_vehicle_data", {}).setdefault("current_mileage_km", 0)
    return await _ask_vehicle_service_km(update, context)


async def driver_vehicle_service_km_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save service interval in kilometers."""
    try:
        interval = _parse_int(update.message.text, "интервал ТО", allow_zero=False)
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(
            update,
            context,
            "Не понял интервал. Введите число, например 10000.",
            get_driver_step_keyboard(can_skip=True, skip_text="Оставить"),
        )
        return DriverStates.WAIT_VEHICLE_SERVICE_KM

    await _delete_user_message(update)
    context.user_data.setdefault("driver_vehicle_data", {})["service_interval_km"] = interval
    return await _ask_vehicle_service_months(update, context)


async def driver_vehicle_service_km_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep service km interval."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_vehicle_data", {}).setdefault("service_interval_km", 10000)
    return await _ask_vehicle_service_months(update, context)


async def driver_vehicle_service_months_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save service interval in months and finish vehicle wizard."""
    try:
        interval = _parse_int(update.message.text, "интервал ТО", allow_zero=False)
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(
            update,
            context,
            "Не понял интервал. Введите число месяцев, например 12.",
            get_driver_step_keyboard(can_skip=True, skip_text="Оставить"),
        )
        return DriverStates.WAIT_VEHICLE_SERVICE_MONTHS

    await _delete_user_message(update)
    context.user_data.setdefault("driver_vehicle_data", {})["service_interval_months"] = interval
    return await _finish_vehicle_wizard(update, context)


async def driver_vehicle_service_months_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep service month interval and finish vehicle wizard."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_vehicle_data", {}).setdefault("service_interval_months", 12)
    return await _finish_vehicle_wizard(update, context)


async def _finish_vehicle_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create or update vehicle from collected wizard data."""
    mode = context.user_data.get("driver_vehicle_mode", "create")
    vehicle_id = context.user_data.get("driver_vehicle_id")
    data = context.user_data.get("driver_vehicle_data", {})

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        if mode == "edit":
            vehicle = await service.update_vehicle(
                vehicle_id=vehicle_id,
                user_id=user_id,
                title=data["title"],
                current_mileage_km=data.get("current_mileage_km", 0),
                service_interval_km=data.get("service_interval_km", 10000),
                service_interval_months=data.get("service_interval_months", 12),
            )
        else:
            vehicle = await service.create_vehicle(
                user_id=user_id,
                title=data["title"],
                current_mileage_km=data.get("current_mileage_km", 0),
                service_interval_km=data.get("service_interval_km", 10000),
                service_interval_months=data.get("service_interval_months", 12),
                preset_slug=data.get("preset_slug"),
                make=data.get("make"),
                model=data.get("model"),
                year=data.get("year"),
                body_type=data.get("body_type"),
                engine_volume_l=data.get("engine_volume_l"),
                engine_power_hp=data.get("engine_power_hp"),
                fuel_type=data.get("fuel_type"),
                transmission=data.get("transmission"),
                drive_type=data.get("drive_type"),
                expected_consumption_city_l_per_100=data.get("expected_consumption_city_l_per_100"),
                expected_consumption_highway_l_per_100=data.get("expected_consumption_highway_l_per_100"),
                expected_consumption_mixed_l_per_100=data.get("expected_consumption_mixed_l_per_100"),
                vehicle_specs_note=data.get("vehicle_specs_note"),
            )
        await session.commit()

    if not vehicle:
        await _show_driver_step(update, context, "❌ Авто не найдено", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    text = "✅ Авто обновлено\n\n" if mode == "edit" else "✅ Авто добавлено\n\n"
    await _show_driver_step(
        update,
        context,
        text + _format_vehicle(vehicle),
        get_driver_vehicle_view_keyboard(vehicle.id),
    )
    _clear_driver_context(context)
    return ConversationHandler.END


async def driver_vehicle_mileage_update_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start quick vehicle mileage update."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    _clear_driver_context(context)
    context.user_data["driver_mileage_vehicle_id"] = vehicle_id
    await _show_driver_step(
        update,
        context,
        f"📍 Пробег: {vehicle.title}\n\nВведите текущий пробег в км.",
        get_driver_step_keyboard(),
    )
    return DriverStates.WAIT_VEHICLE_MILEAGE


async def driver_vehicle_mileage_update_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save quick vehicle mileage update."""
    try:
        mileage = _parse_int(update.message.text, "пробег")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(
            update,
            context,
            "Не понял пробег. Введите число, например 126500.",
            get_driver_step_keyboard(),
        )
        return DriverStates.WAIT_VEHICLE_MILEAGE

    await _delete_user_message(update)
    vehicle_id = context.user_data.get("driver_mileage_vehicle_id")
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).update_mileage(vehicle_id, user_id, mileage)
        await session.commit()

    if not vehicle:
        await _show_driver_step(update, context, "❌ Авто не найдено", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    await _show_driver_step(
        update,
        context,
        "✅ Пробег обновлен\n\n" + _format_vehicle(vehicle),
        get_driver_vehicle_view_keyboard(vehicle.id),
    )
    _clear_driver_context(context)
    return ConversationHandler.END


async def _ask_fuel_mileage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for fuel entry mileage."""
    data = context.user_data.setdefault("driver_fuel_data", {})
    current = data.get("mileage_km")
    text = "⛽ Заправка\n\nШаг 1/5. Укажите пробег на момент заправки."
    if current is not None:
        text += f"\n\nТекущий вариант: {current} км"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=context.user_data.get("driver_fuel_mode") == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_FUEL_MILEAGE


async def _ask_fuel_liters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for fuel liters."""
    data = context.user_data.setdefault("driver_fuel_data", {})
    current = data.get("liters")
    text = "⛽ Заправка\n\nШаг 2/5. Сколько литров заправили?"
    if current is not None:
        text += f"\n\nТекущий вариант: {current:.2f} л"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=context.user_data.get("driver_fuel_mode") == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_FUEL_LITERS


async def _ask_fuel_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for fuel total cost."""
    data = context.user_data.setdefault("driver_fuel_data", {})
    current = data.get("total_cost")
    text = "⛽ Заправка\n\nШаг 3/5. Какая была сумма?"
    if current is not None:
        text += f"\n\nТекущий вариант: {_format_money(current)}"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=context.user_data.get("driver_fuel_mode") == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_FUEL_COST


async def _ask_fuel_full(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask whether it was a full tank."""
    await _show_driver_step(
        update,
        context,
        "⛽ Заправка\n\nШаг 4/5. Это был полный бак?",
        get_driver_full_tank_keyboard(),
    )
    return DriverStates.WAIT_FUEL_FULL


async def _ask_fuel_station(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional fuel station."""
    data = context.user_data.setdefault("driver_fuel_data", {})
    current = data.get("station")
    text = "⛽ Заправка\n\nШаг 5/5. Укажите АЗС или короткий комментарий."
    if current:
        text += f"\n\nТекущий вариант: {current}"
    await _show_driver_step(update, context, text, get_driver_step_keyboard(can_skip=True))
    return DriverStates.WAIT_FUEL_STATION


async def driver_fuel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start fuel entry creation."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    _clear_driver_context(context)
    context.user_data["driver_fuel_mode"] = "create"
    context.user_data["driver_fuel_vehicle_id"] = vehicle_id
    context.user_data["driver_fuel_data"] = {"mileage_km": vehicle.current_mileage_km}
    return await _ask_fuel_mileage(update, context)


async def driver_fuel_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start fuel entry editing."""
    query = update.callback_query
    await query.answer()
    entry_id = _parse_callback_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        entry = await DriverService(session).get_fuel_entry(entry_id, user_id)

    if not entry:
        await query.edit_message_text("❌ Заправка не найдена", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    _clear_driver_context(context)
    context.user_data["driver_fuel_mode"] = "edit"
    context.user_data["driver_fuel_entry_id"] = entry_id
    context.user_data["driver_fuel_vehicle_id"] = entry.vehicle_id
    context.user_data["driver_fuel_data"] = {
        "mileage_km": entry.mileage_km,
        "liters": entry.liters,
        "total_cost": entry.total_cost,
        "is_full_tank": entry.is_full_tank,
        "station": entry.station,
    }
    return await _ask_fuel_mileage(update, context)


async def driver_fuel_mileage_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save fuel mileage."""
    try:
        mileage = _parse_int(update.message.text, "пробег")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите пробег числом.", get_driver_step_keyboard())
        return DriverStates.WAIT_FUEL_MILEAGE

    await _delete_user_message(update)
    context.user_data.setdefault("driver_fuel_data", {})["mileage_km"] = mileage
    return await _ask_fuel_liters(update, context)


async def driver_fuel_mileage_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep fuel mileage while editing."""
    query = update.callback_query
    await query.answer()
    if "mileage_km" not in context.user_data.get("driver_fuel_data", {}):
        return await _ask_fuel_mileage(update, context)
    return await _ask_fuel_liters(update, context)


async def driver_fuel_liters_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save fuel liters."""
    try:
        liters = _parse_float(update.message.text, "литры")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите литры числом, например 45.2.", get_driver_step_keyboard())
        return DriverStates.WAIT_FUEL_LITERS

    await _delete_user_message(update)
    context.user_data.setdefault("driver_fuel_data", {})["liters"] = liters
    return await _ask_fuel_cost(update, context)


async def driver_fuel_liters_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep fuel liters while editing."""
    query = update.callback_query
    await query.answer()
    if "liters" not in context.user_data.get("driver_fuel_data", {}):
        return await _ask_fuel_liters(update, context)
    return await _ask_fuel_cost(update, context)


async def driver_fuel_cost_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save fuel total cost."""
    try:
        total_cost = _parse_float(update.message.text, "сумма")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите сумму числом, например 2800.", get_driver_step_keyboard())
        return DriverStates.WAIT_FUEL_COST

    await _delete_user_message(update)
    context.user_data.setdefault("driver_fuel_data", {})["total_cost"] = total_cost
    return await _ask_fuel_full(update, context)


async def driver_fuel_cost_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep fuel total cost while editing."""
    query = update.callback_query
    await query.answer()
    if "total_cost" not in context.user_data.get("driver_fuel_data", {}):
        return await _ask_fuel_cost(update, context)
    return await _ask_fuel_full(update, context)


async def driver_fuel_full_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save full-tank choice."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_fuel_data", {})["is_full_tank"] = query.data.endswith(":yes")
    return await _ask_fuel_station(update, context)


async def driver_fuel_full_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save full-tank choice from text."""
    try:
        is_full_tank = _parse_bool(update.message.text)
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(
            update,
            context,
            "Не понял ответ. Выберите кнопку или напишите: да / нет.",
            get_driver_full_tank_keyboard(),
        )
        return DriverStates.WAIT_FUEL_FULL

    await _delete_user_message(update)
    context.user_data.setdefault("driver_fuel_data", {})["is_full_tank"] = is_full_tank
    return await _ask_fuel_station(update, context)


async def driver_fuel_station_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save optional fuel station and finish fuel wizard."""
    station = _limit_text(update.message.text, 255)
    await _delete_user_message(update)
    context.user_data.setdefault("driver_fuel_data", {})["station"] = station or None
    return await _finish_fuel_wizard(update, context)


async def driver_fuel_station_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip optional fuel station."""
    query = update.callback_query
    await query.answer()
    if context.user_data.get("driver_fuel_mode") != "edit":
        context.user_data.setdefault("driver_fuel_data", {})["station"] = None
    return await _finish_fuel_wizard(update, context)


async def _finish_fuel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create or update fuel entry from collected data."""
    mode = context.user_data.get("driver_fuel_mode", "create")
    vehicle_id = context.user_data.get("driver_fuel_vehicle_id")
    entry_id = context.user_data.get("driver_fuel_entry_id")
    data = context.user_data.get("driver_fuel_data", {})

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        if mode == "edit":
            entry = await service.update_fuel_entry(
                entry_id=entry_id,
                user_id=user_id,
                mileage_km=data["mileage_km"],
                liters=data["liters"],
                total_cost=data["total_cost"],
                is_full_tank=data.get("is_full_tank", True),
                station=data.get("station"),
            )
        else:
            entry = await service.add_fuel_entry(
                user_id=user_id,
                vehicle_id=vehicle_id,
                mileage_km=data["mileage_km"],
                liters=data["liters"],
                total_cost=data["total_cost"],
                is_full_tank=data.get("is_full_tank", True),
                station=data.get("station"),
            )
        await session.commit()

    if not entry:
        await _show_driver_step(update, context, "❌ Заправка не сохранена", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    prefix = "✅ Заправка обновлена\n\n" if mode == "edit" else "✅ Заправка добавлена\n\n"
    await _show_driver_step(
        update,
        context,
        prefix + _format_fuel_entry(entry),
        get_driver_fuel_entry_keyboard(entry.id, entry.vehicle_id),
    )
    _clear_driver_context(context)
    return ConversationHandler.END


async def driver_service_done_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start marking regular service as done."""
    query = update.callback_query
    await query.answer()
    vehicle_id = _parse_callback_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)

    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    _clear_driver_context(context)
    context.user_data["driver_service_vehicle_id"] = vehicle_id
    await _show_driver_step(
        update,
        context,
        f"🔧 ТО выполнено: {vehicle.title}\n\nВведите пробег, на котором сделано ТО.",
        get_driver_step_keyboard(can_skip=True, skip_text=f"Текущий пробег: {vehicle.current_mileage_km}"),
    )
    return DriverStates.WAIT_SERVICE_MILEAGE


async def driver_service_done_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save service done mileage from text."""
    try:
        mileage = _parse_int(update.message.text, "пробег")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите пробег числом.", get_driver_step_keyboard())
        return DriverStates.WAIT_SERVICE_MILEAGE
    await _delete_user_message(update)
    return await _finish_service_done(update, context, mileage)


async def driver_service_done_current(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Use current mileage for service done mark."""
    query = update.callback_query
    await query.answer()
    vehicle_id = context.user_data.get("driver_service_vehicle_id")
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicle = await DriverService(session).get_vehicle(vehicle_id, user_id)
    if not vehicle:
        await query.edit_message_text("❌ Авто не найдено", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END
    return await _finish_service_done(update, context, vehicle.current_mileage_km)


async def _finish_service_done(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    mileage: int,
) -> int:
    """Persist service done mark and show updated plan."""
    vehicle_id = context.user_data.get("driver_service_vehicle_id")
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        vehicle = await service.mark_service_done(vehicle_id, user_id, mileage)
        plan = await service.get_service_plan(vehicle_id, user_id) if vehicle else None
        await session.commit()

    if not plan:
        await _show_driver_step(update, context, "❌ Авто не найдено", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    await _show_driver_step(
        update,
        context,
        "✅ ТО отмечено\n\n" + _format_service_plan(plan),
        get_driver_service_keyboard(vehicle_id),
    )
    _clear_driver_context(context)
    return ConversationHandler.END


async def _ask_expense_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for manual expense title."""
    mode = context.user_data.get("driver_expense_mode", "create")
    current = context.user_data.setdefault("driver_expense_data", {}).get("title")
    text = "💰 Расход\n\nШаг 1/5. Что это за расход?\n\nНапример: мойка, ремонт, страховка."
    if current:
        text += f"\n\nТекущее значение: {current}"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=mode == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_EXPENSE_TITLE


async def _ask_expense_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for manual expense amount."""
    current = context.user_data.setdefault("driver_expense_data", {}).get("amount")
    text = "💰 Расход\n\nШаг 2/5. Какая сумма?"
    if current is not None:
        text += f"\n\nТекущее значение: {_format_money(current)}"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(
            can_skip=context.user_data.get("driver_expense_mode") == "edit",
            skip_text="Оставить",
        ),
    )
    return DriverStates.WAIT_EXPENSE_AMOUNT


async def _ask_expense_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for manual expense category."""
    await _show_driver_step(
        update,
        context,
        "💰 Расход\n\nШаг 3/5. Выберите категорию.",
        get_driver_expense_category_keyboard(),
    )
    return DriverStates.WAIT_EXPENSE_CATEGORY


async def _ask_expense_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional vehicle binding."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicles = await DriverService(session).get_vehicles(user_id)
    await _show_driver_step(
        update,
        context,
        "💰 Расход\n\nШаг 4/5. К какому авто привязать расход?",
        get_driver_vehicle_choice_keyboard(
            vehicles,
            "driver_expense_vehicle",
            can_skip=context.user_data.get("driver_expense_mode") == "edit",
        ),
    )
    return DriverStates.WAIT_EXPENSE_VEHICLE


async def _ask_expense_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional manual expense note."""
    current = context.user_data.setdefault("driver_expense_data", {}).get("note")
    text = "💰 Расход\n\nШаг 5/5. Добавьте комментарий или пропустите."
    if current:
        text += f"\n\nТекущее значение: {current}"
    await _show_driver_step(update, context, text, get_driver_step_keyboard(can_skip=True))
    return DriverStates.WAIT_EXPENSE_NOTE


async def driver_expense_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start manual expense creation."""
    query = update.callback_query
    await query.answer()
    _clear_driver_context(context)
    context.user_data["driver_expense_mode"] = "create"
    context.user_data["driver_expense_data"] = {}
    return await _ask_expense_title(update, context)


async def driver_expense_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start manual expense editing."""
    query = update.callback_query
    await query.answer()
    expense_id = _parse_callback_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        expense = await DriverService(session).get_expense(expense_id, user_id)
    if not expense:
        await query.edit_message_text("❌ Расход не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END
    _clear_driver_context(context)
    context.user_data["driver_expense_mode"] = "edit"
    context.user_data["driver_expense_id"] = expense_id
    context.user_data["driver_expense_data"] = {
        "title": expense.title,
        "amount": expense.amount,
        "category": expense.category,
        "vehicle_id": expense.vehicle_id,
        "spent_at_utc": expense.spent_at_utc,
        "note": expense.note,
    }
    return await _ask_expense_title(update, context)


async def driver_expense_title_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save manual expense title."""
    title = _limit_text(update.message.text, 255)
    await _delete_user_message(update)
    if not title:
        return await _ask_expense_title(update, context)
    context.user_data.setdefault("driver_expense_data", {})["title"] = title
    return await _ask_expense_amount(update, context)


async def driver_expense_title_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep manual expense title while editing."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("driver_expense_data", {}).get("title"):
        return await _ask_expense_title(update, context)
    return await _ask_expense_amount(update, context)


async def driver_expense_amount_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save manual expense amount."""
    try:
        amount = _parse_float(update.message.text, "сумма")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите сумму числом, например 1500.", get_driver_step_keyboard())
        return DriverStates.WAIT_EXPENSE_AMOUNT
    await _delete_user_message(update)
    context.user_data.setdefault("driver_expense_data", {})["amount"] = amount
    return await _ask_expense_category(update, context)


async def driver_expense_amount_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep manual expense amount while editing."""
    query = update.callback_query
    await query.answer()
    if "amount" not in context.user_data.get("driver_expense_data", {}):
        return await _ask_expense_amount(update, context)
    return await _ask_expense_category(update, context)


async def driver_expense_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save expense category."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_expense_data", {})["category"] = query.data.split(":", 1)[1]
    return await _ask_expense_vehicle(update, context)


async def driver_expense_vehicle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save optional expense vehicle binding."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]
    context.user_data.setdefault("driver_expense_data", {})["vehicle_id"] = None if value == "none" else int(value)
    return await _ask_expense_note(update, context)


async def driver_expense_vehicle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep expense vehicle binding while editing."""
    query = update.callback_query
    await query.answer()
    return await _ask_expense_note(update, context)


async def driver_expense_note_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save manual expense note and finish."""
    note = _limit_text(update.message.text, 1000)
    await _delete_user_message(update)
    context.user_data.setdefault("driver_expense_data", {})["note"] = note or None
    return await _finish_expense_wizard(update, context)


async def driver_expense_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip manual expense note."""
    query = update.callback_query
    await query.answer()
    if context.user_data.get("driver_expense_mode") != "edit":
        context.user_data.setdefault("driver_expense_data", {})["note"] = None
    return await _finish_expense_wizard(update, context)


async def _finish_expense_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create or update manual expense."""
    mode = context.user_data.get("driver_expense_mode", "create")
    expense_id = context.user_data.get("driver_expense_id")
    data = context.user_data.get("driver_expense_data", {})

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        if mode == "edit":
            expense = await service.update_expense(
                expense_id=expense_id,
                user_id=user_id,
                title=data["title"],
                amount=data["amount"],
                category=data.get("category", "other"),
                vehicle_id=data.get("vehicle_id"),
                spent_at_utc=data.get("spent_at_utc"),
                note=data.get("note"),
            )
        else:
            expense = await service.create_expense(
                user_id=user_id,
                title=data["title"],
                amount=data["amount"],
                category=data.get("category", "other"),
                vehicle_id=data.get("vehicle_id"),
                note=data.get("note"),
            )
        await session.commit()

    if not expense:
        await _show_driver_step(update, context, "❌ Расход не сохранен", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    text = "✅ Расход обновлен\n\n" if mode == "edit" else "✅ Расход добавлен\n\n"
    await _show_driver_step(update, context, text + _format_expense(expense), get_driver_expense_view_keyboard(expense.id))
    _clear_driver_context(context)
    return ConversationHandler.END


async def _ask_document_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for document title."""
    mode = context.user_data.get("driver_document_mode", "create")
    current = context.user_data.setdefault("driver_document_data", {}).get("title")
    text = "📄 Документ\n\nШаг 1/6. Что это за документ?\n\nНапример: ОСАГО, права, диагностика."
    if current:
        text += f"\n\nТекущее значение: {current}"
    await _show_driver_step(
        update,
        context,
        text,
        get_driver_step_keyboard(can_skip=mode == "edit", skip_text="Оставить"),
    )
    return DriverStates.WAIT_DOCUMENT_TITLE


async def _ask_document_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for document type."""
    await _show_driver_step(update, context, "📄 Документ\n\nШаг 2/7. Выберите тип.", get_driver_document_type_keyboard())
    return DriverStates.WAIT_DOCUMENT_TYPE


async def _ask_document_vehicle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional document vehicle binding."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        vehicles = await DriverService(session).get_vehicles(user_id)
    await _show_driver_step(
        update,
        context,
        "📄 Документ\n\nШаг 3/7. К какому авто привязать документ?",
        get_driver_vehicle_choice_keyboard(
            vehicles,
            "driver_document_vehicle",
            can_skip=context.user_data.get("driver_document_mode") == "edit",
        ),
    )
    return DriverStates.WAIT_DOCUMENT_VEHICLE


async def _ask_document_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional document identifier."""
    current = context.user_data.setdefault("driver_document_data", {}).get("identifier")
    text = "📄 Документ\n\nШаг 4/7. Укажите номер или короткую пометку."
    if current:
        text += f"\n\nТекущее значение: {current}"
    await _show_driver_step(update, context, text, get_driver_step_keyboard(can_skip=True))
    return DriverStates.WAIT_DOCUMENT_IDENTIFIER


async def _ask_document_expires(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for document expiry date."""
    current = context.user_data.setdefault("driver_document_data", {}).get("expires_at_utc")
    text = "📄 Документ\n\nШаг 5/7. До какой даты действует документ?\n\nНапример: 25.12.2026 или 25.12."
    if current:
        text += f"\n\nТекущее значение: {_format_date(current)}"
    await _show_driver_step(update, context, text, get_driver_step_keyboard(can_skip=True, skip_text="Без срока/оставить"))
    return DriverStates.WAIT_DOCUMENT_EXPIRES


async def _ask_document_remind_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for document reminder offset."""
    await _show_driver_step(
        update,
        context,
        "📄 Документ\n\nШаг 6/7. За сколько дней напомнить о сроке?",
        get_driver_document_remind_keyboard(),
    )
    return DriverStates.WAIT_DOCUMENT_REMIND_DAYS


async def _ask_document_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for optional document note."""
    current = context.user_data.setdefault("driver_document_data", {}).get("note")
    text = "📄 Документ\n\nШаг 7/7. Добавьте комментарий или пропустите."
    if current:
        text += f"\n\nТекущее значение: {current}"
    await _show_driver_step(update, context, text, get_driver_step_keyboard(can_skip=True))
    return DriverStates.WAIT_DOCUMENT_NOTE


async def driver_document_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start driver document creation."""
    query = update.callback_query
    await query.answer()
    _clear_driver_context(context)
    context.user_data["driver_document_mode"] = "create"
    context.user_data["driver_document_data"] = {"remind_before_days": 14, "is_active": True}
    return await _ask_document_title(update, context)


async def driver_document_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start driver document editing."""
    query = update.callback_query
    await query.answer()
    document_id = _parse_callback_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        document = await DriverService(session).get_document(document_id, user_id)
    if not document:
        await query.edit_message_text("❌ Документ не найден", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END
    _clear_driver_context(context)
    context.user_data["driver_document_mode"] = "edit"
    context.user_data["driver_document_id"] = document_id
    context.user_data["driver_document_data"] = {
        "title": document.title,
        "document_type": document.document_type,
        "vehicle_id": document.vehicle_id,
        "identifier": document.identifier,
        "expires_at_utc": document.expires_at_utc,
        "remind_before_days": document.remind_before_days,
        "note": document.note,
        "is_active": document.is_active,
    }
    return await _ask_document_title(update, context)


async def driver_document_title_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document title."""
    title = _limit_text(update.message.text, 255)
    await _delete_user_message(update)
    if not title:
        return await _ask_document_title(update, context)
    context.user_data.setdefault("driver_document_data", {})["title"] = title
    return await _ask_document_type(update, context)


async def driver_document_title_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep document title while editing."""
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("driver_document_data", {}).get("title"):
        return await _ask_document_title(update, context)
    return await _ask_document_type(update, context)


async def driver_document_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document type."""
    query = update.callback_query
    await query.answer()
    context.user_data.setdefault("driver_document_data", {})["document_type"] = query.data.split(":", 1)[1]
    return await _ask_document_vehicle(update, context)


async def driver_document_vehicle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save optional document vehicle binding."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]
    context.user_data.setdefault("driver_document_data", {})["vehicle_id"] = None if value == "none" else int(value)
    return await _ask_document_identifier(update, context)


async def driver_document_vehicle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Keep document vehicle binding while editing."""
    query = update.callback_query
    await query.answer()
    return await _ask_document_identifier(update, context)


async def driver_document_identifier_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save optional document identifier."""
    identifier = _limit_text(update.message.text, 255)
    await _delete_user_message(update)
    context.user_data.setdefault("driver_document_data", {})["identifier"] = identifier or None
    return await _ask_document_expires(update, context)


async def driver_document_identifier_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip or keep document identifier."""
    query = update.callback_query
    await query.answer()
    if context.user_data.get("driver_document_mode") != "edit":
        context.user_data.setdefault("driver_document_data", {})["identifier"] = None
    return await _ask_document_expires(update, context)


async def driver_document_expires_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document expiry date."""
    raw = update.message.text.strip().lower()
    try:
        expires_at = None if raw in {"-", "нет", "без срока", "пропустить"} else _parse_date(raw)
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите дату в формате 25.12.2026 или нажмите кнопку пропуска.", get_driver_step_keyboard(can_skip=True))
        return DriverStates.WAIT_DOCUMENT_EXPIRES
    await _delete_user_message(update)
    context.user_data.setdefault("driver_document_data", {})["expires_at_utc"] = expires_at
    return await _ask_document_remind_days(update, context)


async def driver_document_expires_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip or keep document expiry date."""
    query = update.callback_query
    await query.answer()
    if context.user_data.get("driver_document_mode") != "edit":
        context.user_data.setdefault("driver_document_data", {})["expires_at_utc"] = None
    return await _ask_document_remind_days(update, context)


async def driver_document_remind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document reminder offset from button."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]
    if value == "custom":
        await _show_driver_step(update, context, "Введите количество дней числом.", get_driver_step_keyboard())
        return DriverStates.WAIT_DOCUMENT_REMIND_DAYS
    context.user_data.setdefault("driver_document_data", {})["remind_before_days"] = int(value)
    return await _ask_document_note(update, context)


async def driver_document_remind_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document reminder offset from text."""
    try:
        days = _parse_int(update.message.text, "дни")
    except ValueError:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "Введите число дней, например 14.", get_driver_document_remind_keyboard())
        return DriverStates.WAIT_DOCUMENT_REMIND_DAYS
    await _delete_user_message(update)
    context.user_data.setdefault("driver_document_data", {})["remind_before_days"] = days
    return await _ask_document_note(update, context)


async def driver_document_note_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save document note and finish."""
    note = _limit_text(update.message.text, 1000)
    await _delete_user_message(update)
    context.user_data.setdefault("driver_document_data", {})["note"] = note or None
    return await _finish_document_wizard(update, context)


async def driver_document_note_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip document note."""
    query = update.callback_query
    await query.answer()
    if context.user_data.get("driver_document_mode") != "edit":
        context.user_data.setdefault("driver_document_data", {})["note"] = None
    return await _finish_document_wizard(update, context)


async def _finish_document_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create or update driver document."""
    mode = context.user_data.get("driver_document_mode", "create")
    document_id = context.user_data.get("driver_document_id")
    data = context.user_data.get("driver_document_data", {})

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = DriverService(session)
        if mode == "edit":
            document = await service.update_document(
                document_id=document_id,
                user_id=user_id,
                title=data["title"],
                document_type=data.get("document_type", "other"),
                vehicle_id=data.get("vehicle_id"),
                identifier=data.get("identifier"),
                expires_at_utc=data.get("expires_at_utc"),
                remind_before_days=data.get("remind_before_days", 14),
                note=data.get("note"),
                is_active=data.get("is_active", True),
            )
        else:
            document = await service.create_document(
                user_id=user_id,
                title=data["title"],
                document_type=data.get("document_type", "other"),
                vehicle_id=data.get("vehicle_id"),
                identifier=data.get("identifier"),
                expires_at_utc=data.get("expires_at_utc"),
                remind_before_days=data.get("remind_before_days", 14),
                note=data.get("note"),
                is_active=True,
            )
        await session.commit()

    if not document:
        await _show_driver_step(update, context, "❌ Документ не сохранен", get_back_home_inline_keyboard())
        _clear_driver_context(context)
        return ConversationHandler.END

    text = "✅ Документ обновлен\n\n" if mode == "edit" else "✅ Документ добавлен\n\n"
    await _show_driver_step(update, context, text + _format_document(document), get_driver_document_view_keyboard(document.id))
    _clear_driver_context(context)
    return ConversationHandler.END


async def driver_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel driver assistant input."""
    _clear_driver_context(context)
    if update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.edit_message_text("❌ Отменено", reply_markup=get_driver_menu_keyboard())
    else:
        await _delete_user_message(update)
        await _show_driver_step(update, context, "❌ Отменено", get_back_home_inline_keyboard())
    return ConversationHandler.END


driver_vehicle_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(driver_vehicle_create_start, pattern="^driver_vehicle_create$"),
        CallbackQueryHandler(driver_vehicle_edit_start, pattern="^driver_vehicle_edit:"),
    ],
    states={
        DriverStates.WAIT_VEHICLE_PRESET: [
            CallbackQueryHandler(driver_vehicle_create_start, pattern="^driver_vehicle_create$"),
            CallbackQueryHandler(driver_section_callback, pattern="^driver_section:"),
            CallbackQueryHandler(driver_vehicle_manual_start, pattern="^driver_vehicle_manual$"),
            CallbackQueryHandler(driver_vehicle_preset_confirm, pattern="^driver_vehicle_preset_confirm$"),
            CallbackQueryHandler(driver_vehicle_preset_select, pattern="^driver_vehicle_preset:"),
        ],
        DriverStates.WAIT_VEHICLE_TITLE: [
            CallbackQueryHandler(driver_vehicle_title_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_vehicle_title_save),
        ],
        DriverStates.WAIT_VEHICLE_MILEAGE: [
            CallbackQueryHandler(driver_vehicle_mileage_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_vehicle_mileage_save),
        ],
        DriverStates.WAIT_VEHICLE_SERVICE_KM: [
            CallbackQueryHandler(driver_vehicle_service_km_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_vehicle_service_km_save),
        ],
        DriverStates.WAIT_VEHICLE_SERVICE_MONTHS: [
            CallbackQueryHandler(driver_vehicle_service_months_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_vehicle_service_months_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)


driver_vehicle_mileage_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(driver_vehicle_mileage_update_start, pattern="^driver_vehicle_mileage:")],
    states={
        DriverStates.WAIT_VEHICLE_MILEAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_vehicle_mileage_update_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)


driver_fuel_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(driver_fuel_add_start, pattern="^driver_fuel_add:"),
        CallbackQueryHandler(driver_fuel_edit_start, pattern="^driver_fuel_edit:"),
    ],
    states={
        DriverStates.WAIT_FUEL_MILEAGE: [
            CallbackQueryHandler(driver_fuel_mileage_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fuel_mileage_save),
        ],
        DriverStates.WAIT_FUEL_LITERS: [
            CallbackQueryHandler(driver_fuel_liters_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fuel_liters_save),
        ],
        DriverStates.WAIT_FUEL_COST: [
            CallbackQueryHandler(driver_fuel_cost_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fuel_cost_save),
        ],
        DriverStates.WAIT_FUEL_FULL: [
            CallbackQueryHandler(driver_fuel_full_callback, pattern="^driver_fuel_full:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fuel_full_text_save),
        ],
        DriverStates.WAIT_FUEL_STATION: [
            CallbackQueryHandler(driver_fuel_station_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_fuel_station_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)


driver_expense_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(driver_expense_add_start, pattern="^driver_expense_add$"),
        CallbackQueryHandler(driver_expense_edit_start, pattern="^driver_expense_edit:"),
    ],
    states={
        DriverStates.WAIT_EXPENSE_TITLE: [
            CallbackQueryHandler(driver_expense_title_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_expense_title_save),
        ],
        DriverStates.WAIT_EXPENSE_AMOUNT: [
            CallbackQueryHandler(driver_expense_amount_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_expense_amount_save),
        ],
        DriverStates.WAIT_EXPENSE_CATEGORY: [
            CallbackQueryHandler(driver_expense_category_callback, pattern="^driver_expense_category:"),
        ],
        DriverStates.WAIT_EXPENSE_VEHICLE: [
            CallbackQueryHandler(driver_expense_vehicle_skip, pattern="^driver_skip$"),
            CallbackQueryHandler(driver_expense_vehicle_callback, pattern="^driver_expense_vehicle:"),
        ],
        DriverStates.WAIT_EXPENSE_NOTE: [
            CallbackQueryHandler(driver_expense_note_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_expense_note_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)


driver_document_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(driver_document_add_start, pattern="^driver_document_add$"),
        CallbackQueryHandler(driver_document_edit_start, pattern="^driver_document_edit:"),
    ],
    states={
        DriverStates.WAIT_DOCUMENT_TITLE: [
            CallbackQueryHandler(driver_document_title_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_document_title_save),
        ],
        DriverStates.WAIT_DOCUMENT_TYPE: [
            CallbackQueryHandler(driver_document_type_callback, pattern="^driver_document_type:"),
        ],
        DriverStates.WAIT_DOCUMENT_VEHICLE: [
            CallbackQueryHandler(driver_document_vehicle_skip, pattern="^driver_skip$"),
            CallbackQueryHandler(driver_document_vehicle_callback, pattern="^driver_document_vehicle:"),
        ],
        DriverStates.WAIT_DOCUMENT_IDENTIFIER: [
            CallbackQueryHandler(driver_document_identifier_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_document_identifier_save),
        ],
        DriverStates.WAIT_DOCUMENT_EXPIRES: [
            CallbackQueryHandler(driver_document_expires_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_document_expires_save),
        ],
        DriverStates.WAIT_DOCUMENT_REMIND_DAYS: [
            CallbackQueryHandler(driver_document_remind_callback, pattern="^driver_document_remind:"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_document_remind_save),
        ],
        DriverStates.WAIT_DOCUMENT_NOTE: [
            CallbackQueryHandler(driver_document_note_skip, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_document_note_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)


driver_service_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(driver_service_done_start, pattern="^driver_service_done:")],
    states={
        DriverStates.WAIT_SERVICE_MILEAGE: [
            CallbackQueryHandler(driver_service_done_current, pattern="^driver_skip$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, driver_service_done_save),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", driver_cancel_handler),
        CallbackQueryHandler(driver_cancel_handler, pattern="^cancel$"),
    ],
)
