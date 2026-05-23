"""
Lists handlers.

CRUD operations for todo/shopping lists and list items.
"""

import logging

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
    get_back_home_inline_keyboard,
    get_cancel_keyboard,
    get_cancel_inline_keyboard,
    get_list_delete_confirm_keyboard,
    get_list_item_delete_confirm_keyboard,
    get_list_item_keyboard,
    get_list_member_manage_keyboard,
    get_list_members_keyboard,
    get_list_share_keyboard,
    get_list_view_keyboard,
    get_lists_list_keyboard,
)
from src.bot.states import ListStates
from src.config import settings
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.list_service import ListService
from src.utils.text import truncate

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 10


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID when the user is registered."""
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(update.effective_user.id)
    return user.id if user else update.effective_user.id


def _parse_id(data: str) -> int:
    """Parse the numeric ID from callback data in action:id format."""
    return int(data.split(":", 1)[1])


def _parse_parts(data: str) -> list[str]:
    """Split callback data."""
    return data.split(":")


def _store_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember the bot message that should be edited after text input."""
    query = update.callback_query
    if not query or not query.message:
        return

    context.user_data["list_prompt_chat_id"] = query.message.chat_id
    context.user_data["list_prompt_message_id"] = query.message.message_id


async def _edit_prompt_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit the stored bot prompt after text input, or reply as fallback."""
    chat_id = context.user_data.pop("list_prompt_chat_id", None)
    message_id = context.user_data.pop("list_prompt_message_id", None)

    if chat_id and message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return

    await update.message.reply_text(text, reply_markup=reply_markup)


async def _delete_user_message(update: Update) -> None:
    """Best-effort cleanup for text input messages inside list flows."""
    if not update.message:
        return

    try:
        await update.message.delete()
    except Exception:
        logger.debug("Could not delete user input message", exc_info=True)


async def _render_lists_page(user_id: int, page: int) -> tuple[str, object]:
    """Build text and keyboard for a lists page."""
    page = max(page, 0)

    async with async_session_maker() as session:
        list_service = ListService(session)
        lists, total = await list_service.get_lists_list(
            user_id=user_id,
            page=page,
            page_size=ITEMS_PER_PAGE,
        )

    if not lists and page > 0:
        return await _render_lists_page(user_id, page - 1)

    if not lists:
        text = (
            "📋 Списки\n\n"
            "У вас пока нет списков. Создайте первый список дел или покупок."
        )
    else:
        current_page = page + 1
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        text = f"📋 Списки ({total} всего)\nСтраница {current_page}/{total_pages}"

    keyboard = get_lists_list_keyboard(
        lists,
        page=page,
        has_next=(page + 1) * ITEMS_PER_PAGE < total,
    )
    return text, keyboard


async def _render_list_view(
    list_id: int,
    user_id: int,
) -> tuple[str | None, object | None]:
    """Build text and keyboard for one list view."""
    async with async_session_maker() as session:
        list_service = ListService(session)
        list_obj = await list_service.get_list(list_id, user_id)

        if not list_obj:
            return None, None

        items = await list_service.get_list_items(list_id, user_id)
        role = await list_service.get_access_role(list_id, user_id)
        can_edit = role in {"owner", "editor"}
        can_manage = role == "owner"

    lines = [f"📋 {list_obj.title}"]
    if role == "editor":
        lines.append("👥 Общий список: редактор")
    elif role == "viewer":
        lines.append("👥 Общий список: только просмотр")

    if not items:
        lines.append("\nПока пусто. Добавьте первый пункт.")
    else:
        lines.append("")
        for index, item in enumerate(items, 1):
            status = "✅" if item.is_completed else "⬜"
            lines.append(f"{index}. {status} {truncate(item.text, 72)}")

    return "\n".join(lines), get_list_view_keyboard(
        list_id,
        items,
        can_edit=can_edit,
        can_manage=can_manage,
    )


async def _render_list_members_screen(
    list_id: int,
    user_id: int,
) -> tuple[str | None, object | None, list[dict] | None]:
    """Build shared list members management screen."""
    async with async_session_maker() as session:
        list_service = ListService(session)
        list_obj = await list_service.get_list(list_id, user_id)
        members = await list_service.get_list_members(list_id, user_id)

    if not list_obj or members is None:
        return None, None, None

    role_labels = {
        "owner": "владелец",
        "editor": "редактор",
        "viewer": "только просмотр",
    }
    lines = [f"👥 Участники списка\n\n📋 {list_obj.title}", ""]
    for member in members:
        role = member["role"]
        icon = "👑" if role == "owner" else "👤"
        lines.append(f"{icon} {member['display_name']} — {role_labels.get(role, role)}")

    return "\n".join(lines), get_list_members_keyboard(list_id, members), members


async def _show_lists_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> int:
    """Show a paginated list of user's lists."""
    query = update.callback_query
    if query:
        await query.answer()

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_lists_page(user_id, page)

    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return ConversationHandler.END


async def lists_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show first page of lists."""
    return await _show_lists_page(update, context, page=0)


async def lists_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show requested lists page."""
    page = _parse_id(update.callback_query.data)
    return await _show_lists_page(update, context, page=page)


async def list_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start list creation."""
    _store_prompt_message(update, context)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📋 Создание списка\n\nВведите название:",
            reply_markup=get_cancel_inline_keyboard(),
        )
    else:
        await update.message.reply_text(
            "📋 Создание списка\n\nВведите название:",
            reply_markup=get_cancel_keyboard(),
        )

    return ListStates.WAIT_TITLE


async def list_save_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save list title and show the created list."""
    title = update.message.text.strip()
    await _delete_user_message(update)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        list_obj = await list_service.create_list(user_id=user_id, title=title)
        await session.commit()
        list_id = list_obj.id

    text, keyboard = await _render_list_view(list_id, user_id)
    await _edit_prompt_or_reply(update, context, text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def list_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list with item buttons."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_list_view(list_id, user_id)
    if not text:
        await query.edit_message_text("❌ Список не найден")
        return ConversationHandler.END

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def list_add_item_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding a single item."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)
    context.user_data["current_list_id"] = list_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        "➕ Добавление пункта\n\nВведите текст:",
        reply_markup=get_cancel_inline_keyboard(),
    )

    return ListStates.WAIT_ADD_ITEM


async def list_save_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save a new item and refresh the list view."""
    text_value = update.message.text.strip()
    list_id = context.user_data.get("current_list_id")
    await _delete_user_message(update)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.add_item(list_id, user_id, text_value)
        await session.commit()

    if not item:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Список не найден",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    rendered_text, keyboard = await _render_list_view(list_id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def list_add_bulk_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start adding multiple items."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)
    context.user_data["current_list_id"] = list_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        "📦 Добавление пачкой\n\n"
        "Отправьте несколько строк текста. Каждая строка станет отдельным пунктом.",
        reply_markup=get_cancel_inline_keyboard(),
    )

    return ListStates.WAIT_ADD_ITEMS_BULK


async def list_save_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save multiple items and refresh the list view."""
    lines = [line.strip() for line in update.message.text.split("\n") if line.strip()]
    list_id = context.user_data.get("current_list_id")
    await _delete_user_message(update)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        items = await list_service.add_items_bulk(list_id, user_id, lines)
        await session.commit()

    rendered_text, keyboard = await _render_list_view(list_id, user_id)
    if not rendered_text or not items:
        rendered_text, keyboard = "❌ Список не найден", get_back_home_inline_keyboard()

    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def list_rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start list rename."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)
    context.user_data["current_list_id"] = list_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        "✏️ Переименование\n\nВведите новое название:",
        reply_markup=get_cancel_inline_keyboard(),
    )

    return ListStates.WAIT_EDIT_TITLE


async def list_save_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save new list name and refresh the list view."""
    new_title = update.message.text.strip()
    list_id = context.user_data.get("current_list_id")
    await _delete_user_message(update)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        list_obj = await list_service.update_list_title(list_id, user_id, new_title)
        await session.commit()

    if not list_obj:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Список не найден",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    rendered_text, keyboard = await _render_list_view(list_id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def list_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list text in the same message for copying."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        text = await list_service.format_list_as_text(list_id, user_id)
        share = await list_service.create_share_token(list_id, user_id)
        editor_share = await list_service.create_collaboration_token(list_id, user_id, role="editor")
        viewer_share = await list_service.create_collaboration_token(list_id, user_id, role="viewer")
        await session.commit()

    if not text or not share or not editor_share or not viewer_share:
        await query.edit_message_text("❌ Список не найден")
        return ConversationHandler.END

    import_command = f"/import_list {share.token}"
    editor_join_command = f"/join_list {editor_share.token}"
    viewer_join_command = f"/join_list {viewer_share.token}"
    if settings.BOT_USERNAME:
        share_link = f"https://t.me/{settings.BOT_USERNAME}?start=import_list_{share.token}"
        editor_join_link = f"https://t.me/{settings.BOT_USERNAME}?start=join_list_{editor_share.token}"
        viewer_join_link = f"https://t.me/{settings.BOT_USERNAME}?start=join_list_{viewer_share.token}"
    else:
        share_link = None
        editor_join_link = None
        viewer_join_link = None

    export_text = (
        "📤 Поделиться списком\n\n"
        "Есть два режима:\n"
        "• Копия — другой пользователь получит отдельный список.\n"
        "• Общий доступ — вы будете работать в одном списке.\n\n"
        f"{text}\n\n"
        f"Копия:\n{import_command}\n\n"
        f"Общий доступ, редактор:\n{editor_join_command}\n\n"
        f"Общий доступ, только просмотр:\n{viewer_join_command}"
    )
    if share_link:
        export_text += f"\n\nСсылка на копию:\n{share_link}"
    if editor_join_link:
        export_text += f"\n\nСсылка редактора:\n{editor_join_link}"
    if viewer_join_link:
        export_text += f"\n\nСсылка просмотра:\n{viewer_join_link}"
    await query.edit_message_text(
        truncate(export_text, 3900),
        reply_markup=get_list_share_keyboard(list_id),
    )
    return ConversationHandler.END


async def list_members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show shared list members for owner management."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard, _ = await _render_list_members_screen(list_id, user_id)
    if not text:
        await query.edit_message_text("❌ Управление участниками доступно только владельцу списка")
        return ConversationHandler.END

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
    )
    return ConversationHandler.END


async def list_member_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show controls for one shared list member."""
    query = update.callback_query
    await query.answer()

    _, list_id_str, member_id_str = _parse_parts(query.data)
    list_id = int(list_id_str)
    member_id = int(member_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        members = await list_service.get_list_members(list_id, user_id)

    if members is None:
        await query.edit_message_text("❌ Управление участниками доступно только владельцу списка")
        return ConversationHandler.END

    member = next((item for item in members if item.get("member_id") == member_id), None)
    if not member:
        await query.edit_message_text("❌ Участник не найден")
        return ConversationHandler.END

    role_labels = {
        "editor": "редактор",
        "viewer": "только просмотр",
    }
    await query.edit_message_text(
        "👤 Участник\n\n"
        f"{member['display_name']}\n"
        f"Роль: {role_labels.get(member['role'], member['role'])}",
        reply_markup=get_list_member_manage_keyboard(list_id, member_id, member["role"]),
    )
    return ConversationHandler.END


async def list_member_role_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Change shared list member role."""
    query = update.callback_query
    await query.answer("Роль обновлена")

    _, list_id_str, member_id_str, role = _parse_parts(query.data)
    list_id = int(list_id_str)
    member_id = int(member_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        member = await list_service.update_member_role(list_id, user_id, member_id, role)
        await session.commit()

    if not member:
        await query.edit_message_text("❌ Не удалось изменить роль")
        return ConversationHandler.END

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
    text, keyboard, _ = await _render_list_members_screen(list_id, user_id)
    await query.edit_message_text(
        text or "❌ Управление участниками доступно только владельцу списка",
        reply_markup=keyboard or get_back_home_inline_keyboard(),
    )
    return ConversationHandler.END


async def list_member_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Revoke shared list member access."""
    query = update.callback_query
    await query.answer("Доступ отозван")

    _, list_id_str, member_id_str = _parse_parts(query.data)
    list_id = int(list_id_str)
    member_id = int(member_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        removed = await list_service.remove_member(list_id, user_id, member_id)
        await session.commit()

    if not removed:
        await query.edit_message_text("❌ Не удалось отозвать доступ")
        return ConversationHandler.END

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
    text, keyboard, _ = await _render_list_members_screen(list_id, user_id)
    await query.edit_message_text(
        text or "❌ Управление участниками доступно только владельцу списка",
        reply_markup=keyboard or get_back_home_inline_keyboard(),
    )
    return ConversationHandler.END


async def import_list_token(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    token: str,
) -> None:
    """Import a shared list token into the current user's account."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        new_list = await list_service.import_shared_list(token, user_id)
        await session.commit()

    if not new_list:
        await update.message.reply_text(
            "❌ Не удалось импортировать список. Ссылка могла устареть или быть использована слишком много раз.",
            reply_markup=get_back_home_inline_keyboard(),
        )
        return

    text, keyboard = await _render_list_view(new_list.id, user_id)
    await update.message.reply_text(
        "✅ Список импортирован как отдельная копия.\n\n"
        f"{text}",
        reply_markup=keyboard,
    )


async def import_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Import a shared list by token."""
    if not context.args:
        await update.message.reply_text(
            "Отправьте команду так:\n/import_list TOKEN",
            reply_markup=get_back_home_inline_keyboard(),
        )
        return

    await import_list_token(update, context, context.args[0])


async def join_list_token(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    token: str,
) -> None:
    """Join a shared list collaboration token."""
    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        list_obj = await list_service.join_shared_list(token, user_id)
        await session.commit()

    if not list_obj:
        await update.message.reply_text(
            "❌ Не удалось присоединиться к списку. Ссылка могла устареть или быть использована слишком много раз.",
            reply_markup=get_back_home_inline_keyboard(),
        )
        return

    text, keyboard = await _render_list_view(list_obj.id, user_id)
    await update.message.reply_text(
        "✅ Вы присоединились к общему списку.\n\n"
        f"{text}",
        reply_markup=keyboard,
    )


async def join_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Join a shared list by token."""
    if not context.args:
        await update.message.reply_text(
            "Отправьте команду так:\n/join_list TOKEN",
            reply_markup=get_back_home_inline_keyboard(),
        )
        return

    await join_list_token(update, context, context.args[0])


async def list_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for list deletion confirmation."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)

    await query.edit_message_text(
        "Удалить список вместе со всеми пунктами?",
        reply_markup=get_list_delete_confirm_keyboard(list_id),
    )
    return ConversationHandler.END


async def list_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete list and return to lists page."""
    query = update.callback_query
    await query.answer()

    list_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        deleted = await list_service.delete_list(list_id, user_id)
        await session.commit()

    if not deleted:
        await query.edit_message_text("❌ Список не найден")
        return ConversationHandler.END

    text, keyboard = await _render_lists_page(user_id, page=0)
    await query.edit_message_text(text, reply_markup=keyboard)
    context.user_data.clear()
    return ConversationHandler.END


async def list_item_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for new item text."""
    query = update.callback_query
    await query.answer()

    item_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.get_item_by_id(item_id, user_id)

    if not item:
        await query.edit_message_text("❌ Пункт не найден")
        return ConversationHandler.END

    context.user_data["editing_item_id"] = item_id
    context.user_data["current_list_id"] = item.list_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        f"✏️ Новый текст для пункта:\n\n{item.text}",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return ListStates.WAIT_EDIT_ITEM


async def list_save_item_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save edited item text and refresh list."""
    item_id = context.user_data.get("editing_item_id")
    list_id = context.user_data.get("current_list_id")
    new_text = update.message.text.strip()
    await _delete_user_message(update)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.update_item_text_by_id(item_id, user_id, new_text)
        await session.commit()

    if not item:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Пункт не найден",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    rendered_text, keyboard = await _render_list_view(list_id or item.list_id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def list_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list item actions."""
    query = update.callback_query
    await query.answer()

    item_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.get_item_by_id(item_id, user_id)
        role = await list_service.get_access_role(item.list_id, user_id) if item else None

    if not item:
        await query.edit_message_text("❌ Пункт не найден")
        return ConversationHandler.END

    status = "✅ Выполнено" if item.is_completed else "⬜ Не выполнено"
    await query.edit_message_text(
        f"{status}\n\n{item.text}",
        reply_markup=get_list_item_keyboard(
            item.list_id,
            item.id,
            item.is_completed,
            can_edit=role in {"owner", "editor"},
        ),
    )
    return ConversationHandler.END


async def list_item_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle item completion and refresh the list view."""
    query = update.callback_query
    await query.answer()

    item_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.toggle_item_by_id(item_id, user_id)
        await session.commit()

    if not item:
        await query.edit_message_text("❌ Пункт не найден")
        return ConversationHandler.END

    text, keyboard = await _render_list_view(item.list_id, user_id)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def list_item_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for item deletion confirmation."""
    query = update.callback_query
    await query.answer()

    item_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.get_item_by_id(item_id, user_id)

    if not item:
        await query.edit_message_text("❌ Пункт не найден")
        return ConversationHandler.END

    await query.edit_message_text(
        f"Удалить пункт?\n\n{item.text}",
        reply_markup=get_list_item_delete_confirm_keyboard(item.list_id, item.id),
    )
    return ConversationHandler.END


async def list_item_delete_confirm_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """Delete item and refresh the list view."""
    query = update.callback_query
    await query.answer()

    item_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        list_service = ListService(session)
        item = await list_service.get_item_by_id(item_id, user_id)
        list_id = item.list_id if item else None
        deleted = await list_service.delete_item_by_id(item_id, user_id)
        await session.commit()

    if not deleted or list_id is None:
        await query.edit_message_text("❌ Пункт не найден")
        return ConversationHandler.END

    text, keyboard = await _render_list_view(list_id, user_id)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current operation."""
    if update.message:
        await update.message.reply_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard(),
        )
    elif update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.edit_message_text(
            "❌ Отменено",
            reply_markup=get_back_home_inline_keyboard(),
        )

    context.user_data.clear()
    return ConversationHandler.END


# Conversation handlers
list_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(list_create_start, pattern="^list_create$"),
    ],
    states={
        ListStates.WAIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, list_save_title),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)

list_add_item_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(list_add_item_start, pattern="^list_add_item:"),
    ],
    states={
        ListStates.WAIT_ADD_ITEM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, list_save_item),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)

list_add_bulk_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(list_add_bulk_start, pattern="^list_add_bulk:"),
    ],
    states={
        ListStates.WAIT_ADD_ITEMS_BULK: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, list_save_bulk),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)

list_rename_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(list_rename_start, pattern="^list_rename:"),
    ],
    states={
        ListStates.WAIT_EDIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, list_save_rename),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)


list_edit_item_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(list_item_edit_start, pattern="^list_item_edit:"),
    ],
    states={
        ListStates.WAIT_EDIT_ITEM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, list_save_item_edit),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)


import_list_handler = CommandHandler("import_list", import_list_command)
join_list_handler = CommandHandler("join_list", join_list_command)
