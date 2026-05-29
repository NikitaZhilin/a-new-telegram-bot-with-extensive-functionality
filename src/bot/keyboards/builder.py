"""
Keyboards for Telegram bot.

Reply keyboards are only used for the main menu.
Inline keyboards are used for all CRUD operations.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from src.config import settings
from src.utils.text import truncate
from src.utils.public_url import is_https_url, normalize_public_base_url


def _plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Return a Russian plural form for count."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


# =============================================================================
# Reply Keyboards (Main Menu Only)
# =============================================================================

def _public_base_url() -> Optional[str]:
    """Return the configured public HTTPS base URL."""
    base_url = normalize_public_base_url(settings.WEB_PUBLIC_URL or settings.APP_BASE_URL)
    if not is_https_url(base_url):
        return None
    return base_url


def _mini_app_url() -> Optional[str]:
    """Return HTTPS Mini App URL suitable for Telegram web_app buttons."""
    base_url = _public_base_url()
    if not base_url:
        return None
    return f"{base_url}/miniapp"


def get_web_entry_keyboard() -> InlineKeyboardMarkup:
    """Let the user choose between Telegram Mini App and standalone web login."""
    keyboard = []
    mini_app_url = _mini_app_url()
    if mini_app_url:
        keyboard.append([InlineKeyboardButton("📱 Открыть приложение", web_app=WebAppInfo(url=mini_app_url))])
    else:
        keyboard.append([InlineKeyboardButton("📱 Открыть приложение", callback_data="mini_app_unavailable")])
    keyboard.append([InlineKeyboardButton("🌐 Web-версия", callback_data="settings_web_login")])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="home"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def _web_entry_inline_button() -> InlineKeyboardButton:
    """Return a chooser button instead of opening either web surface directly."""
    return InlineKeyboardButton("🌐 Web / приложение", callback_data="web_entry")


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with cancel button for FSM states."""
    keyboard = [["❌ Отмена"]]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_cancel_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline cancel button for edited callback messages."""
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main menu reply keyboard."""
    keyboard = [
        ["📋 Списки", "📝 Заметки"],
        ["💊 Лекарства", "⏰ Напоминания"],
        ["🚗 Водитель", "🌐 Web / приложение"],
        ["⚙️ Настройки", "👥 Поделиться ботом"],
        ["⌨️ Скрыть меню"],
        ["❓ Помощь"],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=False,
    )


def get_main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline main menu for callback-based navigation."""
    keyboard = [
        [
            InlineKeyboardButton("📋 Списки", callback_data="lists_list"),
            InlineKeyboardButton("📝 Заметки", callback_data="notes_list"),
        ],
        [
            InlineKeyboardButton("💊 Лекарства", callback_data="medications_list"),
            InlineKeyboardButton("⏰ Напоминания", callback_data="reminders_list"),
        ],
        [
            InlineKeyboardButton("🚗 Водитель", callback_data="driver_menu"),
            _web_entry_inline_button(),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"),
            InlineKeyboardButton("👥 Поделиться ботом", callback_data="share_bot"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Driver
# =============================================================================

def get_driver_menu_keyboard() -> InlineKeyboardMarkup:
    """Driver hub keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("⚡ Шаблоны", callback_data="driver_section:templates"),
        ],
        [
            InlineKeyboardButton("🚗 Авто", callback_data="driver_section:vehicles"),
            InlineKeyboardButton("⛽ Топливо", callback_data="driver_section:fuel"),
        ],
        [
            InlineKeyboardButton("🔧 ТО", callback_data="driver_section:maintenance"),
            InlineKeyboardButton("💧 Жидкости", callback_data="driver_section:fluids"),
        ],
        [
            InlineKeyboardButton("🛒 Запчасти", callback_data="driver_section:parts"),
            InlineKeyboardButton("🧼 Мойка", callback_data="driver_section:wash"),
        ],
        [
            InlineKeyboardButton("🛞 Шины", callback_data="driver_section:tires"),
            InlineKeyboardButton("📄 Документы", callback_data="driver_section:docs"),
        ],
        [
            InlineKeyboardButton("💰 Расходы", callback_data="driver_section:costs"),
            InlineKeyboardButton("📊 Статистика", callback_data="driver_section:stats"),
        ],
        [
            InlineKeyboardButton("🧾 Журнал авто", callback_data="driver_section:journal"),
        ],
        [
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_section_keyboard(section_key: Optional[str] = None) -> InlineKeyboardMarkup:
    """Driver section navigation keyboard."""
    keyboard = []

    if section_key == "maintenance":
        keyboard.append([
            InlineKeyboardButton("🔧 Напомнить про масло", callback_data="driver_reminder_template:oil"),
        ])
    elif section_key == "fluids":
        keyboard.append([
            InlineKeyboardButton("💧 Чек-лист жидкостей", callback_data="driver_list_template:fluids_check"),
        ])
        keyboard.append([
            InlineKeyboardButton("⏰ Напомнить проверить", callback_data="driver_reminder_template:fluids"),
        ])
    elif section_key == "parts":
        keyboard.append([
            InlineKeyboardButton("🛒 Список запчастей", callback_data="driver_list_template:parts"),
        ])
    elif section_key == "wash":
        keyboard.append([
            InlineKeyboardButton("✅ Мойка сделана", callback_data="driver_journal_quick:wash"),
        ])
        keyboard.append([
            InlineKeyboardButton("⏰ Напомнить про мойку", callback_data="driver_reminder_template:wash"),
        ])
        keyboard.append([
            InlineKeyboardButton("💰 Записать расход", callback_data="driver_expense_add"),
        ])
    elif section_key == "tires":
        keyboard.append([
            InlineKeyboardButton("✅ Давление проверено", callback_data="driver_journal_quick:tire_pressure"),
        ])
        keyboard.append([
            InlineKeyboardButton("🛞 Настроить контроль давления", callback_data="driver_reminder_template:tire_pressure"),
        ])
        keyboard.append([
            InlineKeyboardButton("✅ Проверка перед поездкой", callback_data="driver_list_template:trip_check"),
        ])

    keyboard.extend([
        [
            InlineKeyboardButton("⚡ Шаблоны водителя", callback_data="driver_section:templates"),
        ],
        [
            _web_entry_inline_button(),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_reminder_repeat_keyboard() -> InlineKeyboardMarkup:
    """Repeat choices for ready-made driver reminders."""
    keyboard = [
        [
            InlineKeyboardButton("Разово", callback_data="driver_rem_repeat:none"),
            InlineKeyboardButton("Еженедельно", callback_data="driver_rem_repeat:weekly"),
        ],
        [
            InlineKeyboardButton("Ежемесячно", callback_data="driver_rem_repeat:monthly"),
            InlineKeyboardButton("Ежедневно", callback_data="driver_rem_repeat:daily"),
        ],
        [
            InlineKeyboardButton("⬅️ К шаблонам", callback_data="driver_section:templates"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_expenses_keyboard(expenses: List) -> InlineKeyboardMarkup:
    """Manual driver expenses keyboard."""
    keyboard = []
    for expense in expenses:
        keyboard.append([
            InlineKeyboardButton(
                f"💰 {truncate(expense.title, 28)} · {expense.amount:.0f} ₽",
                callback_data=f"driver_expense_view:{expense.id}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("➕ Добавить расход", callback_data="driver_expense_add"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_expense_view_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    """Manual driver expense view keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"driver_expense_edit:{expense_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"driver_expense_delete:{expense_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К расходам", callback_data="driver_section:costs"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_expense_delete_confirm_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    """Confirm manual expense deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить расход", callback_data=f"driver_expense_delete_confirm:{expense_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К расходу", callback_data=f"driver_expense_view:{expense_id}"),
            InlineKeyboardButton("💰 Расходы", callback_data="driver_section:costs"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_expense_category_keyboard() -> InlineKeyboardMarkup:
    """Manual expense category choices."""
    keyboard = [
        [
            InlineKeyboardButton("🔧 ТО/ремонт", callback_data="driver_expense_category:service"),
            InlineKeyboardButton("🧩 Запчасти", callback_data="driver_expense_category:parts"),
        ],
        [
            InlineKeyboardButton("🧼 Мойка", callback_data="driver_expense_category:wash"),
            InlineKeyboardButton("📄 Страховка", callback_data="driver_expense_category:insurance"),
        ],
        [
            InlineKeyboardButton("🅿️ Парковка", callback_data="driver_expense_category:parking"),
            InlineKeyboardButton("⚠️ Штраф", callback_data="driver_expense_category:fine"),
        ],
        [
            InlineKeyboardButton("Другое", callback_data="driver_expense_category:other"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicle_choice_keyboard(
    vehicles: List,
    callback_prefix: str,
    can_skip: bool = False,
) -> InlineKeyboardMarkup:
    """Vehicle choice keyboard for expense/document flows."""
    keyboard = []
    for vehicle in vehicles:
        keyboard.append([
            InlineKeyboardButton(
                f"🚗 {truncate(vehicle.title, 32)}",
                callback_data=f"{callback_prefix}:{vehicle.id}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("Без привязки к авто", callback_data=f"{callback_prefix}:none"),
    ])
    if can_skip:
        keyboard.append([
            InlineKeyboardButton("Оставить как есть", callback_data="driver_skip"),
        ])
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_documents_keyboard(documents: List) -> InlineKeyboardMarkup:
    """Driver documents keyboard."""
    keyboard = []
    for document in documents:
        status_icon = "📄" if document.is_active else "📦"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {truncate(document.title, 34)}",
                callback_data=f"driver_document_view:{document.id}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("➕ Добавить документ", callback_data="driver_document_add"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_document_view_keyboard(document_id: int) -> InlineKeyboardMarkup:
    """Driver document view keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"driver_document_edit:{document_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"driver_document_delete:{document_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К документам", callback_data="driver_section:docs"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_document_delete_confirm_keyboard(document_id: int) -> InlineKeyboardMarkup:
    """Confirm driver document deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить документ", callback_data=f"driver_document_delete_confirm:{document_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К документу", callback_data=f"driver_document_view:{document_id}"),
            InlineKeyboardButton("📄 Документы", callback_data="driver_section:docs"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_document_type_keyboard() -> InlineKeyboardMarkup:
    """Driver document type choices."""
    keyboard = [
        [
            InlineKeyboardButton("ОСАГО/КАСКО", callback_data="driver_document_type:insurance"),
            InlineKeyboardButton("Права", callback_data="driver_document_type:license"),
        ],
        [
            InlineKeyboardButton("Диагностика", callback_data="driver_document_type:diagnostic"),
            InlineKeyboardButton("Налог", callback_data="driver_document_type:tax"),
        ],
        [
            InlineKeyboardButton("Штраф", callback_data="driver_document_type:fine"),
            InlineKeyboardButton("Другое", callback_data="driver_document_type:other"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_document_remind_keyboard() -> InlineKeyboardMarkup:
    """Driver document reminder offset choices."""
    keyboard = [
        [
            InlineKeyboardButton("За 7 дней", callback_data="driver_document_remind:7"),
            InlineKeyboardButton("За 14 дней", callback_data="driver_document_remind:14"),
        ],
        [
            InlineKeyboardButton("За 30 дней", callback_data="driver_document_remind:30"),
            InlineKeyboardButton("Не напоминать заранее", callback_data="driver_document_remind:0"),
        ],
        [
            InlineKeyboardButton("Ввести число", callback_data="driver_document_remind:custom"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_templates_keyboard() -> InlineKeyboardMarkup:
    """Quick driver templates keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🛒 Список запчастей", callback_data="driver_list_template:parts"),
        ],
        [
            InlineKeyboardButton("✅ Проверка перед поездкой", callback_data="driver_list_template:trip_check"),
        ],
        [
            InlineKeyboardButton("💧 Чек-лист жидкостей", callback_data="driver_list_template:fluids_check"),
        ],
        [
            InlineKeyboardButton("🔧 Замена масла", callback_data="driver_reminder_template:oil"),
            InlineKeyboardButton("💧 Проверить жидкости", callback_data="driver_reminder_template:fluids"),
        ],
        [
            InlineKeyboardButton("🧼 Мойка", callback_data="driver_reminder_template:wash"),
            InlineKeyboardButton("🛞 Давление", callback_data="driver_reminder_template:tire_pressure"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_created_list_keyboard(list_id: int) -> InlineKeyboardMarkup:
    """Keyboard shown after creating a driver checklist template."""
    keyboard = [
        [
            InlineKeyboardButton("▶️ Пройти чек-лист", callback_data=f"checklist_start:{list_id}"),
        ],
        [
            InlineKeyboardButton("⚡ К шаблонам", callback_data="driver_section:templates"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_journal_keyboard(
    page: int = 0,
    event_filter: str = "all",
    vehicle_id: Optional[int] = None,
    has_more: bool = False,
    entries: Optional[List[object]] = None,
    offset: int = 0,
) -> InlineKeyboardMarkup:
    """Driver journal navigation keyboard."""
    vehicle_part = vehicle_id if vehicle_id is not None else "all"
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Все" if event_filter == "all" else "Все",
                callback_data=f"driver_journal_filter:all:0:{vehicle_part}",
            ),
            InlineKeyboardButton(
                "✅ ТО" if event_filter == "service" else "ТО",
                callback_data=f"driver_journal_filter:service:0:{vehicle_part}",
            ),
            InlineKeyboardButton(
                "✅ Заправки" if event_filter == "fuel" else "Заправки",
                callback_data=f"driver_journal_filter:fuel:0:{vehicle_part}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Чек-листы" if event_filter == "checklists" else "Чек-листы",
                callback_data=f"driver_journal_filter:checklists:0:{vehicle_part}",
            ),
            InlineKeyboardButton(
                "✅ Расходы" if event_filter == "expenses" else "Расходы",
                callback_data=f"driver_journal_filter:expenses:0:{vehicle_part}",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Документы" if event_filter == "documents" else "Документы",
                callback_data=f"driver_journal_filter:documents:0:{vehicle_part}",
            ),
            InlineKeyboardButton(
                "✅ Ручные" if event_filter == "manual" else "Ручные",
                callback_data=f"driver_journal_filter:manual:0:{vehicle_part}",
            ),
        ],
        [
            InlineKeyboardButton("🚗 По авто", callback_data=f"driver_journal_vehicle_filter:{event_filter}:{page}"),
            InlineKeyboardButton("Сброс авто", callback_data=f"driver_journal_filter:{event_filter}:0:all"),
        ],
    ]
    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅️ Назад", callback_data=f"driver_journal_filter:{event_filter}:{page - 1}:{vehicle_part}")
        )
    if has_more:
        nav_row.append(
            InlineKeyboardButton("Ещё ➡️", callback_data=f"driver_journal_filter:{event_filter}:{page + 1}:{vehicle_part}")
        )
    if nav_row:
        keyboard.append(nav_row)
    entry_buttons = []
    for index, entry in enumerate(entries or [], start=offset + 1):
        metadata = getattr(entry, "metadata_json", None) or {}
        if isinstance(metadata, dict) and metadata.get("manual"):
            entry_buttons.append(
                InlineKeyboardButton(f"✏️ #{index}", callback_data=f"driver_journal_view:{entry.id}")
            )
    for start in range(0, len(entry_buttons), 2):
        keyboard.append(entry_buttons[start : start + 2])
    keyboard.extend([
        [
            InlineKeyboardButton("➕ Запись", callback_data="driver_journal_add"),
        ],
        [
            InlineKeyboardButton("⬅️ Для водителя", callback_data="driver_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_journal_entry_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    """Manual journal entry action keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"driver_journal_edit:{entry_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"driver_journal_delete:{entry_id}"),
        ],
        [
            InlineKeyboardButton("🧾 Журнал авто", callback_data="driver_section:journal"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_journal_delete_confirm_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    """Manual journal entry delete confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"driver_journal_delete_confirm:{entry_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К записи", callback_data=f"driver_journal_view:{entry_id}"),
            InlineKeyboardButton("🧾 Журнал", callback_data="driver_section:journal"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_journal_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting manual driver journal event type."""
    keyboard = [
        [
            InlineKeyboardButton("🔧 Ремонт", callback_data="driver_journal_type:repair"),
            InlineKeyboardButton("🔎 Диагностика", callback_data="driver_journal_type:diagnostic"),
        ],
        [
            InlineKeyboardButton("🧩 Замена детали", callback_data="driver_journal_type:parts"),
            InlineKeyboardButton("🧽 Мойка", callback_data="driver_journal_type:wash"),
        ],
        [
            InlineKeyboardButton("🛞 Давление шин", callback_data="driver_journal_type:tire_pressure"),
            InlineKeyboardButton("📝 Заметка", callback_data="driver_journal_type:note"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicles_keyboard(vehicles: List) -> InlineKeyboardMarkup:
    """Vehicle list keyboard."""
    keyboard = []
    for vehicle in vehicles:
        keyboard.append([
            InlineKeyboardButton(
                f"🚗 {truncate(vehicle.title, 32)}",
                callback_data=f"driver_vehicle_view:{vehicle.id}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Добавить авто", callback_data="driver_vehicle_create"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicle_preset_keyboard(presets: List) -> InlineKeyboardMarkup:
    """Vehicle preset selection keyboard."""
    keyboard = []
    for preset in presets:
        keyboard.append([
            InlineKeyboardButton(
                f"🚗 {truncate(preset.label, 46)}",
                callback_data=f"driver_vehicle_preset:{preset.slug}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("✍️ Ввести вручную", callback_data="driver_vehicle_manual"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ К авто", callback_data="driver_section:vehicles"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicle_preset_confirm_keyboard() -> InlineKeyboardMarkup:
    """Vehicle preset confirmation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Выбрать", callback_data="driver_vehicle_preset_confirm"),
        ],
        [
            InlineKeyboardButton("🚗 Другой вариант", callback_data="driver_vehicle_create"),
            InlineKeyboardButton("✍️ Вручную", callback_data="driver_vehicle_manual"),
        ],
        [
            InlineKeyboardButton("⬅️ К авто", callback_data="driver_section:vehicles"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicle_view_keyboard(vehicle_id: int) -> InlineKeyboardMarkup:
    """Vehicle profile keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📍 Обновить пробег", callback_data=f"driver_vehicle_mileage:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("⛽ Добавить заправку", callback_data=f"driver_fuel_add:{vehicle_id}"),
            InlineKeyboardButton("📜 История", callback_data=f"driver_fuel_history:{vehicle_id}:0"),
        ],
        [
            InlineKeyboardButton("🔧 ТО", callback_data=f"driver_service_view:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"driver_vehicle_edit:{vehicle_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"driver_vehicle_delete:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К авто", callback_data="driver_section:vehicles"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_vehicle_delete_confirm_keyboard(vehicle_id: int) -> InlineKeyboardMarkup:
    """Confirm vehicle deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить авто", callback_data=f"driver_vehicle_delete_confirm:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К авто", callback_data=f"driver_vehicle_view:{vehicle_id}"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_service_keyboard(vehicle_id: int) -> InlineKeyboardMarkup:
    """Vehicle service plan keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✅ ТО выполнено", callback_data=f"driver_service_done:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Интервалы", callback_data=f"driver_vehicle_edit:{vehicle_id}"),
            InlineKeyboardButton("🚗 К авто", callback_data=f"driver_vehicle_view:{vehicle_id}"),
        ],
        [
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_fuel_history_keyboard(
    vehicle_id: int,
    entries: List,
    page: int = 0,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    """Fuel entry history keyboard."""
    keyboard = []
    for entry in entries:
        full_icon = "⛽" if entry.is_full_tank else "◐"
        keyboard.append([
            InlineKeyboardButton(
                f"{full_icon} {entry.mileage_km} км · {entry.liters:.1f} л · {entry.total_cost:.0f} ₽",
                callback_data=f"driver_fuel_view:{entry.id}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"driver_fuel_history:{vehicle_id}:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"driver_fuel_history:{vehicle_id}:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton("➕ Заправка", callback_data=f"driver_fuel_add:{vehicle_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("🚗 К авто", callback_data=f"driver_vehicle_view:{vehicle_id}"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_driver_fuel_entry_keyboard(entry_id: int, vehicle_id: int) -> InlineKeyboardMarkup:
    """Fuel entry view keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Изменить", callback_data=f"driver_fuel_edit:{entry_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"driver_fuel_delete:{entry_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ История", callback_data=f"driver_fuel_history:{vehicle_id}:0"),
            InlineKeyboardButton("🚗 К авто", callback_data=f"driver_vehicle_view:{vehicle_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_fuel_delete_confirm_keyboard(entry_id: int, vehicle_id: int) -> InlineKeyboardMarkup:
    """Confirm fuel entry deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"driver_fuel_delete_confirm:{entry_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К записи", callback_data=f"driver_fuel_view:{entry_id}"),
            InlineKeyboardButton("📜 История", callback_data=f"driver_fuel_history:{vehicle_id}:0"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_step_keyboard(
    can_skip: bool = False,
    skip_text: str = "Пропустить",
) -> InlineKeyboardMarkup:
    """Keyboard for step-by-step driver forms."""
    keyboard = []
    if can_skip:
        keyboard.append([InlineKeyboardButton(skip_text, callback_data="driver_skip")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def get_driver_full_tank_keyboard() -> InlineKeyboardMarkup:
    """Fuel full-tank choice keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("Полный бак", callback_data="driver_fuel_full:yes"),
            InlineKeyboardButton("Неполный", callback_data="driver_fuel_full:no"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_fuel_keyboard(vehicles: List) -> InlineKeyboardMarkup:
    """Fuel journal keyboard."""
    keyboard = []
    if len(vehicles) == 1:
        keyboard.append([
            InlineKeyboardButton("➕ Заправка", callback_data=f"driver_fuel_add:{vehicles[0].id}"),
        ])
    elif len(vehicles) > 1:
        for vehicle in vehicles:
            keyboard.append([
                InlineKeyboardButton(
                    f"➕ {truncate(vehicle.title, 28)}",
                    callback_data=f"driver_fuel_add:{vehicle.id}",
                )
            ])
    else:
        keyboard.append([
            InlineKeyboardButton("➕ Добавить авто", callback_data="driver_vehicle_create"),
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Navigation
# =============================================================================

def get_back_inline_keyboard() -> InlineKeyboardMarkup:
    """Back button to return to previous menu."""
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)


def get_home_inline_keyboard() -> InlineKeyboardMarkup:
    """Home button to return to main menu."""
    keyboard = [[InlineKeyboardButton("🏠 В меню", callback_data="home")]]
    return InlineKeyboardMarkup(keyboard)


def get_back_home_inline_keyboard() -> InlineKeyboardMarkup:
    """Back and Home buttons."""
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="back"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_settings_back_home_keyboard() -> InlineKeyboardMarkup:
    """Back to settings and Home buttons."""
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Настройки", callback_data="settings_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_web_login_keyboard(url: Optional[str]) -> InlineKeyboardMarkup:
    """Web login actions with a direct URL button when available."""
    keyboard = []
    if url:
        keyboard.append([InlineKeyboardButton("🌐 Открыть web-версию", url=url)])
    keyboard.append([
        InlineKeyboardButton("⬅️ Настройки", callback_data="settings_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Notes
# =============================================================================

def get_notes_list_keyboard(
    notes: List,
    page: int = 0,
    has_next: bool = False,
    search_active: bool = False,
    category_active: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard for notes list with pagination."""
    keyboard = []
    for note in notes:
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {truncate(note.title, 32)}",
                callback_data=f"note_view:{note.id}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"notes_page:{page - 1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"notes_page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="note_create"),
        InlineKeyboardButton("🔎 Поиск", callback_data="notes_search"),
    ])
    keyboard.append([
        InlineKeyboardButton("🏷 Категория", callback_data="notes_filter"),
    ])
    if search_active or category_active:
        keyboard.append([InlineKeyboardButton("↩️ Все заметки", callback_data="notes_search_clear")])
    keyboard.append([InlineKeyboardButton("🏠 В меню", callback_data="home")])
    return InlineKeyboardMarkup(keyboard)


def get_note_view_keyboard(note_id: int) -> InlineKeyboardMarkup:
    """Keyboard for viewing one note."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Название", callback_data=f"note_edit_title:{note_id}"),
            InlineKeyboardButton("📝 Текст", callback_data=f"note_edit_text:{note_id}"),
        ],
        [
            InlineKeyboardButton("🏷 Категория", callback_data=f"note_edit_category:{note_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"note_delete:{note_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К заметкам", callback_data="notes_list"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_note_category_keyboard(
    *,
    prefix: str = "note_category",
    note_id: Optional[int] = None,
    selected: Optional[str] = None,
    include_all: bool = False,
    back_callback: str = "notes_list",
) -> InlineKeyboardMarkup:
    """Keyboard for note category choice and filters."""
    categories = [
        ("recipe", "🍲 Рецепт"),
        ("instruction", "📌 Инструкция"),
        ("idea", "💡 Идея"),
        ("personal", "👤 Личное"),
        ("other", "📎 Другое"),
    ]
    keyboard = []
    if include_all:
        label = "✅ Все категории" if not selected else "Все категории"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{prefix}:all")])
    for category, label in categories:
        text = f"✅ {label}" if selected == category else label
        callback_data = f"{prefix}:{category}" if note_id is None else f"{prefix}:{note_id}:{category}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)


def get_note_delete_confirm_keyboard(note_id: int) -> InlineKeyboardMarkup:
    """Confirm note deletion/archive."""
    keyboard = [
        [InlineKeyboardButton("🗑 Да, удалить", callback_data=f"note_delete_confirm:{note_id}")],
        [
            InlineKeyboardButton("⬅️ К заметке", callback_data=f"note_view:{note_id}"),
            InlineKeyboardButton("📝 К заметкам", callback_data="notes_list"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Lists
# =============================================================================

def get_lists_list_keyboard(
    lists: List,
    page: int = 0,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard for lists list with pagination."""
    keyboard = []
    
    # Lists buttons
    for lst in lists:
        items_count = len(lst.items) if hasattr(lst, 'items') else 0
        title = truncate(lst.title, 28)
        item_word = _plural_ru(items_count, "пункт", "пункта", "пунктов")
        role = getattr(lst, "_access_role", "owner")
        prefix = "👥 " if role in {"editor", "viewer"} else "📋 "
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix}{title} ({items_count} {item_word})",
                callback_data=f"list_view:{lst.id}"
            )
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"lists_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"lists_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Action buttons
    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="list_create"),
    ])
    
    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_list_view_keyboard(
    list_id: int,
    items: Optional[List] = None,
    can_edit: bool = True,
    can_manage: bool = True,
    manage_items: bool = False,
    checked_source_item_ids: Optional[set[int]] = None,
) -> InlineKeyboardMarkup:
    """Keyboard for viewing a single list with items."""
    keyboard = []
    checked_source_item_ids = checked_source_item_ids or set()

    for item in items or []:
        status_icon = "✏️" if manage_items else ("✅" if item.id in checked_source_item_ids else "⬜")
        text = truncate(item.text, 30)
        callback_data = f"list_item:{item.id}" if manage_items else f"checklist_start_item:{list_id}:{item.id}"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {text}",
                callback_data=callback_data,
            )
        ])

    if can_edit:
        keyboard.append([
            InlineKeyboardButton("➕ Добавить", callback_data=f"list_add_item:{list_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("📦 Пачкой", callback_data=f"list_add_bulk:{list_id}"),
        ])
        if items and not manage_items:
            keyboard.append([
                InlineKeyboardButton("✏️ Редактировать пункты", callback_data=f"list_manage_items:{list_id}"),
            ])

    if can_manage:
        keyboard.append([
            InlineKeyboardButton("✏️ Переименовать", callback_data=f"list_rename:{list_id}"),
            InlineKeyboardButton("📤 Поделиться", callback_data=f"list_share:{list_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("👥 Участники", callback_data=f"list_members:{list_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"list_delete:{list_id}"),
        ])

    if can_manage:
        keyboard.append([
            InlineKeyboardButton("⏰ Напомнить", callback_data=f"list_remind:{list_id}"),
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="lists_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_voice_list_preview_keyboard(
    mode: str,
    list_id: Optional[int] = None,
) -> InlineKeyboardMarkup:
    """Keyboard for dictated list preview."""
    if mode == "add" and list_id:
        confirm = InlineKeyboardButton("✅ Добавить в список", callback_data="list_voice_confirm")
        back = InlineKeyboardButton("⬅️ К списку", callback_data=f"list_view:{list_id}")
    else:
        confirm = InlineKeyboardButton("✅ Создать список", callback_data="list_voice_confirm")
        back = InlineKeyboardButton("⬅️ К спискам", callback_data="lists_list")

    keyboard = [
        [confirm],
        [
            InlineKeyboardButton("✏️ Исправить текст", callback_data="list_voice_edit_text"),
            InlineKeyboardButton("❌ Отмена", callback_data="list_voice_cancel"),
        ],
        [back, InlineKeyboardButton("🏠 В меню", callback_data="home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_list_share_keyboard(list_id: int) -> InlineKeyboardMarkup:
    """Keyboard for the list export screen."""
    keyboard = [
        [
            InlineKeyboardButton("⬅️ К списку", callback_data=f"list_view:{list_id}"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_list_members_keyboard(list_id: int, members: List[dict]) -> InlineKeyboardMarkup:
    """Keyboard for shared list members."""
    role_labels = {
        "owner": "владелец",
        "editor": "редактор",
        "viewer": "просмотр",
    }
    keyboard = []
    for member in members:
        role = member.get("role", "viewer")
        name = truncate(member.get("display_name", "Пользователь"), 24)
        if role == "owner":
            keyboard.append([
                InlineKeyboardButton(f"👑 {name} ({role_labels[role]})", callback_data=f"list_view:{list_id}"),
            ])
            continue

        keyboard.append([
            InlineKeyboardButton(
                f"👤 {name} ({role_labels.get(role, role)})",
                callback_data=f"list_member:{list_id}:{member['member_id']}",
            ),
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ К списку", callback_data=f"list_view:{list_id}"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_list_member_manage_keyboard(
    list_id: int,
    member_id: int,
    role: str,
) -> InlineKeyboardMarkup:
    """Keyboard for one shared list member."""
    keyboard = []
    if role != "editor":
        keyboard.append([
            InlineKeyboardButton("Сделать редактором", callback_data=f"list_member_role:{list_id}:{member_id}:editor"),
        ])
    if role != "viewer":
        keyboard.append([
            InlineKeyboardButton("Только просмотр", callback_data=f"list_member_role:{list_id}:{member_id}:viewer"),
        ])
    keyboard.append([
        InlineKeyboardButton("🚫 Отозвать доступ", callback_data=f"list_member_remove:{list_id}:{member_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Участники", callback_data=f"list_members:{list_id}"),
        InlineKeyboardButton("📋 К списку", callback_data=f"list_view:{list_id}"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_list_item_keyboard(
    list_id: int,
    item_id: int,
    is_completed: bool = False,
    can_edit: bool = True,
) -> InlineKeyboardMarkup:
    """Keyboard for a single list item."""
    keyboard = []
    if can_edit:
        keyboard.append([
            InlineKeyboardButton("✏️ Изменить", callback_data=f"list_item_edit:{item_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"list_item_delete:{item_id}"),
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ К списку", callback_data=f"list_view:{list_id}"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_list_delete_confirm_keyboard(list_id: int) -> InlineKeyboardMarkup:
    """Confirm list deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"list_delete_confirm:{list_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К списку", callback_data=f"list_view:{list_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_list_item_delete_confirm_keyboard(list_id: int, item_id: int) -> InlineKeyboardMarkup:
    """Confirm list item deletion."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"list_item_delete_confirm:{item_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К пункту", callback_data=f"list_item:{item_id}"),
            InlineKeyboardButton("📋 К списку", callback_data=f"list_view:{list_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def _list_callback_for_source(list_id: int, source_module: Optional[str] = None) -> str:
    """Return the correct list view callback for a domain-owned list."""
    if source_module == "driver":
        return "driver_menu"
    return f"list_view:{list_id}"


def _lists_hub_callback_for_source(source_module: Optional[str] = None) -> str:
    """Return the correct list hub callback for a domain-owned list."""
    if source_module == "driver":
        return "driver_menu"
    return "lists_list"


def get_checklist_run_keyboard(
    run,
    source_list_id: Optional[int] = None,
    source_module: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Keyboard for an active personal checklist run."""
    keyboard = []
    for item in run.items:
        status_icon = "✅" if item.checked else "⬜"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {truncate(item.text_snapshot, 34)}",
                callback_data=f"checklist_toggle:{run.id}:{item.id}",
            )
        ])

    all_checked = bool(run.items) and all(item.checked for item in run.items)
    if not all_checked:
        keyboard.append([
            InlineKeyboardButton("☑️ Отметить все пункты", callback_data=f"checklist_check_all:{run.id}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("✅ Завершить чек-лист", callback_data=f"checklist_finish:{run.id}"),
        ])

    keyboard.append([
        InlineKeyboardButton("❌ Отменить", callback_data=f"checklist_cancel:{run.id}"),
    ])
    if source_list_id:
        if source_module == "driver":
            keyboard.append([
                InlineKeyboardButton("⬅️ Для водителя", callback_data="driver_menu"),
                InlineKeyboardButton("🏠 В меню", callback_data="home"),
            ])
            return InlineKeyboardMarkup(keyboard)
        keyboard.append([
            InlineKeyboardButton("⬅️ К списку", callback_data=_list_callback_for_source(source_list_id, source_module)),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📋 К спискам", callback_data="lists_list"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ])

    return InlineKeyboardMarkup(keyboard)


def get_checklist_finished_keyboard(
    source_list_id: Optional[int] = None,
    source_module: Optional[str] = None,
) -> InlineKeyboardMarkup:
    """Keyboard for finished or canceled checklist run screen."""
    if source_list_id:
        if source_module == "driver":
            keyboard = [
                [
                    InlineKeyboardButton("🧾 Журнал авто", callback_data="driver_section:journal"),
                    InlineKeyboardButton("🚗 Для водителя", callback_data="driver_menu"),
                ],
                [
                    InlineKeyboardButton("🏠 В меню", callback_data="home"),
                ],
            ]
            return InlineKeyboardMarkup(keyboard)
        keyboard = [
            [
                InlineKeyboardButton("⬅️ К списку", callback_data=_list_callback_for_source(source_list_id, source_module)),
                InlineKeyboardButton("📋 К разделу", callback_data=_lists_hub_callback_for_source(source_module)),
            ],
            [
                InlineKeyboardButton("🏠 В меню", callback_data="home"),
            ],
        ]
    else:
        keyboard = [
            [
                InlineKeyboardButton("📋 К спискам", callback_data="lists_list"),
                InlineKeyboardButton("🏠 В меню", callback_data="home"),
            ],
        ]
    return InlineKeyboardMarkup(keyboard)


def get_list_items_keyboard(
    list_id: int,
    items: List,
) -> InlineKeyboardMarkup:
    """Keyboard for list items with toggle/edit."""
    keyboard = []
    
    for item in items:
        status_icon = "✅" if item.is_completed else "⬜"
        text = truncate(item.text, 30)
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {text}",
                callback_data=f"list_item:{item.id}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data=f"list_view:{list_id}"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Medications
# =============================================================================

def get_medications_list_keyboard(
    medications: List,
    page: int = 0,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard for medication list with pagination."""
    keyboard = []

    for medication in medications:
        title = truncate(medication.name, 32)
        importance = getattr(medication, "importance", "normal")
        icon = {
            "supplement": "🌿",
            "normal": "💊",
            "important": "❗",
            "critical": "🚨",
        }.get(importance, "💊")
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {title}",
                callback_data=f"med_view:{medication.id}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"med_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"med_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton("➕ Добавить", callback_data="med_create"),
    ])
    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])

    return InlineKeyboardMarkup(keyboard)


def get_medication_view_keyboard(
    medication_id: int,
    can_mark: bool = True,
) -> InlineKeyboardMarkup:
    """Keyboard for one medication."""
    keyboard = []
    if can_mark:
        keyboard.append([
            InlineKeyboardButton("✅ Принял", callback_data=f"med_taken:{medication_id}"),
            InlineKeyboardButton("⏭ Пропустил", callback_data=f"med_skip:{medication_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("↩️ Отложить 15 мин", callback_data=f"med_snooze:{medication_id}"),
            InlineKeyboardButton("⏰ Напомнить", callback_data=f"med_remind:{medication_id}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("⏰ Напомнить", callback_data=f"med_remind:{medication_id}"),
        ])

    keyboard.append([
        InlineKeyboardButton("✏️ Изменить", callback_data=f"med_edit:{medication_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("🗑 Удалить", callback_data=f"med_delete:{medication_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="medications_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_medication_edit_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Field selector for medication editing."""
    keyboard = [
        [
            InlineKeyboardButton("Название", callback_data=f"med_edit_name:{medication_id}"),
            InlineKeyboardButton("Дозировка", callback_data=f"med_edit_dosage:{medication_id}"),
        ],
        [
            InlineKeyboardButton("Инструкция", callback_data=f"med_edit_instr:{medication_id}"),
            InlineKeyboardButton("Важность", callback_data=f"med_edit_importance:{medication_id}"),
        ],
        [
            InlineKeyboardButton("⏰ Время приема", callback_data=f"med_remind:{medication_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_edit_text_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Back keyboard for medication text edit prompts."""
    keyboard = [
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_edit_dosage_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Preset dosage choices for medication editing."""
    keyboard = [
        [
            InlineKeyboardButton("1 таблетка", callback_data=f"med_edit_dosage_value:{medication_id}:tablet1"),
            InlineKeyboardButton("1/2 таблетки", callback_data=f"med_edit_dosage_value:{medication_id}:tablet_half"),
        ],
        [
            InlineKeyboardButton("1 капля", callback_data=f"med_edit_dosage_value:{medication_id}:drop1"),
            InlineKeyboardButton("5 мл", callback_data=f"med_edit_dosage_value:{medication_id}:ml5"),
        ],
        [
            InlineKeyboardButton("Очистить", callback_data=f"med_edit_dosage_value:{medication_id}:skip"),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_edit_instructions_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Preset instruction choices for medication editing."""
    keyboard = [
        [
            InlineKeyboardButton("После еды", callback_data=f"med_edit_instr_value:{medication_id}:after_food"),
            InlineKeyboardButton("До еды", callback_data=f"med_edit_instr_value:{medication_id}:before_food"),
        ],
        [
            InlineKeyboardButton("Во время еды", callback_data=f"med_edit_instr_value:{medication_id}:during_food"),
        ],
        [
            InlineKeyboardButton("Запить водой", callback_data=f"med_edit_instr_value:{medication_id}:with_water"),
            InlineKeyboardButton("Не смешивать", callback_data=f"med_edit_instr_value:{medication_id}:separate"),
        ],
        [
            InlineKeyboardButton("Очистить", callback_data=f"med_edit_instr_value:{medication_id}:skip"),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_edit_importance_keyboard(medication_id: int, current: str = "normal") -> InlineKeyboardMarkup:
    """Importance choices for medication editing."""
    labels = {
        "supplement": "🌿 БАД",
        "normal": "💊 Обычное",
        "important": "❗ Важное",
        "critical": "🚨 Критичное",
    }
    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅' if current == 'supplement' else '⬜'} {labels['supplement']}",
                callback_data=f"med_edit_importance_value:{medication_id}:supplement",
            ),
            InlineKeyboardButton(
                f"{'✅' if current == 'normal' else '⬜'} {labels['normal']}",
                callback_data=f"med_edit_importance_value:{medication_id}:normal",
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if current == 'important' else '⬜'} {labels['important']}",
                callback_data=f"med_edit_importance_value:{medication_id}:important",
            ),
            InlineKeyboardButton(
                f"{'✅' if current == 'critical' else '⬜'} {labels['critical']}",
                callback_data=f"med_edit_importance_value:{medication_id}:critical",
            ),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_delete_confirm_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Confirm medication archiving."""
    keyboard = [
        [
            InlineKeyboardButton("🗑 Да, удалить", callback_data=f"med_delete_confirm:{medication_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_dosage_keyboard() -> InlineKeyboardMarkup:
    """Preset choices for medication dosage."""
    keyboard = [
        [
            InlineKeyboardButton("1 таблетка", callback_data="med_dosage:tablet1"),
            InlineKeyboardButton("1/2 таблетки", callback_data="med_dosage:tablet_half"),
        ],
        [
            InlineKeyboardButton("1 капля", callback_data="med_dosage:drop1"),
            InlineKeyboardButton("5 мл", callback_data="med_dosage:ml5"),
        ],
        [
            InlineKeyboardButton("Пропустить", callback_data="med_dosage:skip"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_instructions_keyboard() -> InlineKeyboardMarkup:
    """Preset choices for medication instructions."""
    keyboard = [
        [
            InlineKeyboardButton("После еды", callback_data="med_instr:after_food"),
            InlineKeyboardButton("До еды", callback_data="med_instr:before_food"),
        ],
        [
            InlineKeyboardButton("Во время еды", callback_data="med_instr:during_food"),
        ],
        [
            InlineKeyboardButton("Запить водой", callback_data="med_instr:with_water"),
            InlineKeyboardButton("Не смешивать", callback_data="med_instr:separate"),
        ],
        [
            InlineKeyboardButton("Пропустить", callback_data="med_instr:skip"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_importance_keyboard() -> InlineKeyboardMarkup:
    """Importance choices for medication."""
    keyboard = [
        [
            InlineKeyboardButton("🌿 БАД", callback_data="med_importance:supplement"),
            InlineKeyboardButton("💊 Обычное", callback_data="med_importance:normal"),
        ],
        [
            InlineKeyboardButton("❗ Важное", callback_data="med_importance:important"),
            InlineKeyboardButton("🚨 Критичное", callback_data="med_importance:critical"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_medication_reminder_keyboard(medication_id: int) -> InlineKeyboardMarkup:
    """Quick reminder time choices for medication."""
    keyboard = [
        [
            InlineKeyboardButton("1 раз в день", callback_data=f"med_rem_freq:{medication_id}:1"),
        ],
        [
            InlineKeyboardButton("2 раза в день", callback_data=f"med_rem_freq:{medication_id}:2"),
        ],
        [
            InlineKeyboardButton("3 раза в день", callback_data=f"med_rem_freq:{medication_id}:3"),
        ],
        [
            InlineKeyboardButton("09:00", callback_data=f"med_rem_time:{medication_id}:0900"),
            InlineKeyboardButton("21:00", callback_data=f"med_rem_time:{medication_id}:2100"),
            InlineKeyboardButton("✍️ Ввести", callback_data=f"med_rem_custom:{medication_id}"),
        ],
        [
            InlineKeyboardButton("Пропустить", callback_data=f"med_rem_skip:{medication_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К лекарству", callback_data=f"med_view:{medication_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Reminders
# =============================================================================

def get_reminders_list_keyboard(
    reminders: List,
    page: int = 0,
    has_next: bool = False,
    show_active: bool = True,
) -> InlineKeyboardMarkup:
    """Keyboard for reminders list with pagination and filter."""
    keyboard = []

    for reminder in reminders:
        time_str = reminder.remind_at_utc.strftime("%d.%m %H:%M")
        status_icon = "⏰" if reminder.status.value == "active" else "✅"
        text = reminder.text[:35] + "..." if len(reminder.text) > 35 else reminder.text
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} [{time_str}] {text}",
                callback_data=f"reminder_view:{reminder.id}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"reminders_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"reminders_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="reminder_create"),
    ])

    if show_active:
        keyboard.append([
            InlineKeyboardButton("📜 Завершенные", callback_data="reminders_filter_history"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📅 Активные", callback_data="reminders_filter_active"),
        ])

    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])

    return InlineKeyboardMarkup(keyboard)


def get_reminder_view_keyboard(
    reminder_id: int,
    status: str = "active",
    list_id: Optional[int] = None,
    source_module: Optional[str] = "general",
) -> InlineKeyboardMarkup:
    """Keyboard for viewing a single reminder."""
    keyboard = []

    if status == "active":
        keyboard.append([
            InlineKeyboardButton("✅ Выполнено", callback_data=f"reminder_done:{reminder_id}"),
            InlineKeyboardButton("✏️ Изменить", callback_data=f"reminder_edit_menu:{reminder_id}"),
        ])
        if source_module in (None, "general"):
            keyboard.append([
                InlineKeyboardButton("➕ Следующее напоминание", callback_data="reminder_create"),
            ])

    if list_id:
        keyboard.append([
            InlineKeyboardButton("📋 Открыть список", callback_data=f"list_view:{list_id}"),
            InlineKeyboardButton("▶️ Чек-лист", callback_data=f"checklist_start:{list_id}"),
        ])

    keyboard.append([
        InlineKeyboardButton("🗑 Удалить", callback_data=f"reminder_delete:{reminder_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="reminders_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])

    return InlineKeyboardMarkup(keyboard)


def get_reminder_edit_keyboard(reminder_id: int) -> InlineKeyboardMarkup:
    """Keyboard with reminder edit choices."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Текст", callback_data=f"reminder_edit_text:{reminder_id}"),
            InlineKeyboardButton("🕒 Время", callback_data=f"reminder_edit_time:{reminder_id}"),
            InlineKeyboardButton("🔁 Повтор", callback_data=f"reminder_edit_repeat:{reminder_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ К напоминанию", callback_data=f"reminder_view:{reminder_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reminder_edit_repeat_keyboard(reminder_id: int, current: str = "none") -> InlineKeyboardMarkup:
    """Repeat choices for editing an existing reminder."""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Нет" if current == "none" else "⬜ Нет",
                callback_data=f"reminder_edit_repeat_value:{reminder_id}:none",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Ежедневно" if current == "daily" else "⬜ Ежедневно",
                callback_data=f"reminder_edit_repeat_value:{reminder_id}:daily",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Еженедельно" if current == "weekly" else "⬜ Еженедельно",
                callback_data=f"reminder_edit_repeat_value:{reminder_id}:weekly",
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Ежемесячно" if current == "monthly" else "⬜ Ежемесячно",
                callback_data=f"reminder_edit_repeat_value:{reminder_id}:monthly",
            ),
        ],
        [
            InlineKeyboardButton("⬅️ К напоминанию", callback_data=f"reminder_view:{reminder_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reminder_date_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting reminder date."""
    keyboard = [
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="rem_date_today"),
            InlineKeyboardButton("📅 Завтра", callback_data="rem_date_tomorrow"),
        ],
        [
            InlineKeyboardButton("📅 Послезавтра", callback_data="rem_date_after_tomorrow"),
            InlineKeyboardButton("📆 Через неделю", callback_data="rem_date_next_week"),
        ],
        [
            InlineKeyboardButton("✍️ Ввести дату/фразу", callback_data="rem_date_custom"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="rem_cancel_create"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reminder_time_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting reminder time (presets)."""
    keyboard = [
        [
            InlineKeyboardButton("⏰ 10 мин", callback_data="rem_time_10min"),
            InlineKeyboardButton("⏰ 30 мин", callback_data="rem_time_30min"),
        ],
        [
            InlineKeyboardButton("⏰ 1 час", callback_data="rem_time_1hour"),
            InlineKeyboardButton("⏰ 2 часа", callback_data="rem_time_2hour"),
        ],
        [
            InlineKeyboardButton("09:00", callback_data="rem_time_clock_0900"),
            InlineKeyboardButton("12:00", callback_data="rem_time_clock_1200"),
            InlineKeyboardButton("18:00", callback_data="rem_time_clock_1800"),
        ],
        [
            InlineKeyboardButton("21:00", callback_data="rem_time_clock_2100"),
        ],
        [
            InlineKeyboardButton("✍️ Ввести время/фразу", callback_data="rem_time_custom"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад к дате", callback_data="rem_time_back"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reminder_confirm_keyboard(
    remind_at_utc,
    repeat_rule: str = "none",
) -> InlineKeyboardMarkup:
    """Keyboard for confirming reminder creation."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="rem_confirm_create"),
        ],
        [
            InlineKeyboardButton("🔁 Повтор", callback_data="rem_repeat_set"),
            InlineKeyboardButton("🕒 Изменить время", callback_data="rem_time_change"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="rem_cancel_create"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reminder_repeat_keyboard(current: str = "none") -> InlineKeyboardMarkup:
    """Keyboard for selecting repeat rule."""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Нет" if current == "none" else "⬜ Нет",
                callback_data="rem_repeat_none"
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Ежедневно" if current == "daily" else "⬜ Ежедневно",
                callback_data="rem_repeat_daily"
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Еженедельно" if current == "weekly" else "⬜ Еженедельно",
                callback_data="rem_repeat_weekly"
            ),
        ],
        [
            InlineKeyboardButton(
                "✅ Ежемесячно" if current == "monthly" else "⬜ Ежемесячно",
                callback_data="rem_repeat_monthly"
            ),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="rem_confirm_back"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Inline Keyboards - Settings
# =============================================================================

def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for settings menu."""
    keyboard = [
        [
            InlineKeyboardButton("🌍 Часовой пояс", callback_data="settings_timezone"),
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="settings_stats"),
        ],
        [
            InlineKeyboardButton("💳 Подписка", callback_data="settings_subscription"),
        ],
        [
            InlineKeyboardButton("ℹ️ О боте", callback_data="settings_about"),
        ],
        [
            _web_entry_inline_button(),
        ],
        [
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_about_keyboard(
    github_url: str = "",
    changelog_url: str = "",
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """Keyboard for app version/about screen."""
    keyboard = []
    links = []
    if github_url:
        links.append(InlineKeyboardButton("📦 GitHub", url=github_url))
    if changelog_url:
        links.append(InlineKeyboardButton("📝 История изменений", url=changelog_url))
    if links:
        keyboard.append(links)
    keyboard.append([
        InlineKeyboardButton("📜 История версий", callback_data="settings_release_history"),
    ])
    if is_admin:
        keyboard.append([
            InlineKeyboardButton("🔧 Технический статус", callback_data="settings_technical_status"),
        ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Настройки", callback_data="settings_menu"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    return InlineKeyboardMarkup(keyboard)


def get_timezone_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for timezone selection."""
    keyboard = [
        [
            InlineKeyboardButton("🇪🇺 Europe/Moscow", callback_data="tz_europe_moscow"),
        ],
        [
            InlineKeyboardButton("🇺🇸 America/New_York", callback_data="tz_america_new_york"),
            InlineKeyboardButton("🇺🇸 America/Los_Angeles", callback_data="tz_america_los_angeles"),
        ],
        [
            InlineKeyboardButton("🇬🇧 Europe/London", callback_data="tz_europe_london"),
            InlineKeyboardButton("🇪🇺 Europe/Berlin", callback_data="tz_europe_berlin"),
        ],
        [
            InlineKeyboardButton("✏️ Ввести вручную", callback_data="tz_custom"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


# =============================================================================
# Callback Data Helpers
# =============================================================================

def parse_callback_data(data: str) -> tuple[str, Optional[str]]:
    """
    Parse callback data in format 'action:id'.
    
    Returns:
        Tuple of (action, id) or (action, None)
    """
    if ":" in data:
        action, id_str = data.split(":", 1)
        return action, id_str
    return data, None
