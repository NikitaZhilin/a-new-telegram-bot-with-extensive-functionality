"""
Keyboards for Telegram bot.

Reply keyboards are only used for the main menu.
Inline keyboards are used for all CRUD operations.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup

from src.utils.text import truncate


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
        ["📋 Списки", "💊 Лекарства", "⏰ Напоминания", "🚗 Для водителя"],
        ["⚙️ Настройки", "👥 Поделиться ботом"],
        ["❓ Помощь"],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def get_main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline main menu for callback-based navigation."""
    keyboard = [
        [
            InlineKeyboardButton("📋 Списки", callback_data="lists_list"),
            InlineKeyboardButton("💊 Лекарства", callback_data="medications_list"),
            InlineKeyboardButton("⏰ Напоминания", callback_data="reminders_list"),
            InlineKeyboardButton("🚗 Для водителя", callback_data="driver_menu"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu"),
        ],
        [
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
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_driver_section_keyboard() -> InlineKeyboardMarkup:
    """Driver section navigation keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Список", callback_data="list_create"),
            InlineKeyboardButton("⏰ Напоминание", callback_data="reminder_create"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="driver_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
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


# =============================================================================
# Inline Keyboards - Notes
# =============================================================================

def get_notes_list_keyboard(
    notes: List,
    page: int = 0,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    """
    Keyboard for notes list with pagination.
    
    Args:
        notes: List of Note objects
        page: Current page number
        has_next: Whether there are more pages
    """
    keyboard = []
    
    # Notes buttons
    for note in notes:
        status_icon = "📦" if note.is_archived else "📝"
        title = note.title or "Без названия"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {title}",
                callback_data=f"note_view:{note.id}"
            )
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"notes_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"notes_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Action buttons
    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="note_create"),
    ])
    
    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_note_view_keyboard(note_id: int, is_archived: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for viewing a single note."""
    keyboard = []
    
    if not is_archived:
        keyboard.append([
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"note_edit:{note_id}"),
        ])
        keyboard.append([
            InlineKeyboardButton("🗑 Удалить", callback_data=f"note_delete:{note_id}"),
            InlineKeyboardButton("📦 Архивировать", callback_data=f"note_archive:{note_id}"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📤 Восстановить", callback_data=f"note_restore:{note_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"note_delete:{note_id}"),
        ])
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="notes_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_note_edit_keyboard(note_id: int) -> InlineKeyboardMarkup:
    """Keyboard for editing a note."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Заголовок", callback_data=f"note_edit_title:{note_id}"),
            InlineKeyboardButton("📝 Текст", callback_data=f"note_edit_body:{note_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=f"note_view:{note_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_notes_archive_keyboard(page: int = 0, has_next: bool = False) -> InlineKeyboardMarkup:
    """Keyboard for archived notes."""
    keyboard = []
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"notes_archive_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"notes_archive_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="notes_list"),
    ])
    
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
) -> InlineKeyboardMarkup:
    """Keyboard for viewing a single list with items."""
    keyboard = []

    for item in items or []:
        status_icon = "✅" if item.is_completed else "⬜"
        text = truncate(item.text, 30)
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {text}",
                callback_data=f"list_item:{item.id}"
            )
        ])

    if can_edit:
        keyboard.append([
            InlineKeyboardButton("➕ Добавить", callback_data=f"list_add_item:{list_id}"),
            InlineKeyboardButton("📦 Пачкой", callback_data=f"list_add_bulk:{list_id}"),
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
    toggle_text = "⬜ Снять отметку" if is_completed else "✅ Отметить"
    keyboard = []
    if can_edit:
        keyboard.append([
            InlineKeyboardButton(toggle_text, callback_data=f"list_item_toggle:{item_id}"),
            InlineKeyboardButton("✏️ Изменить", callback_data=f"list_item_edit:{item_id}"),
        ])
        keyboard.append([
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
        InlineKeyboardButton("🗑 Удалить", callback_data=f"med_delete:{medication_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="medications_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
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
    
    # Reminders buttons
    for reminder in reminders:
        time_str = reminder.remind_at_utc.strftime("%d.%m %H:%M")
        status_icon = "⏰" if reminder.status == "active" else "✅"
        text = reminder.text[:35] + "..." if len(reminder.text) > 35 else reminder.text
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} [{time_str}] {text}",
                callback_data=f"reminder_view:{reminder.id}"
            )
        ])
    
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"reminders_page:{page-1}"))
    if has_next:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"reminders_page:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Filter toggle
    filter_text = "📅 Активные" if show_active else "📜 История"
    filter_action = "reminders_filter_active" if show_active else "reminders_filter_history"
    
    keyboard.append([
        InlineKeyboardButton(filter_text, callback_data=filter_action),
    ])
    
    # Action buttons
    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="reminder_create"),
    ])
    
    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


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

    if show_active:
        keyboard.append([
            InlineKeyboardButton("📜 Завершенные", callback_data="reminders_filter_history"),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📅 Активные", callback_data="reminders_filter_active"),
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Создать", callback_data="reminder_create"),
    ])
    keyboard.append([
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])

    return InlineKeyboardMarkup(keyboard)


def get_reminder_view_keyboard(reminder_id: int, status: str = "active") -> InlineKeyboardMarkup:
    """Keyboard for viewing a single reminder."""
    keyboard = []

    if status == "active":
        keyboard.append([
            InlineKeyboardButton("✅ Выполнено", callback_data=f"reminder_done:{reminder_id}"),
            InlineKeyboardButton("🚫 Отменить", callback_data=f"reminder_cancel:{reminder_id}"),
        ])

    keyboard.append([
        InlineKeyboardButton("🗑 Удалить", callback_data=f"reminder_delete:{reminder_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="reminders_list"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])

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
            InlineKeyboardButton("🌐 Web-версия", callback_data="settings_web_login"),
        ],
        [
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ]
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
