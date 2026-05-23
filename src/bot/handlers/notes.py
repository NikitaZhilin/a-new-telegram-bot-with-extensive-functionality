"""
Notes handlers.

CRUD operations for notes with pagination, archive, and basic editing.
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
    get_cancel_inline_keyboard,
    get_cancel_keyboard,
    get_note_edit_keyboard,
    get_note_view_keyboard,
    get_notes_list_keyboard,
)
from src.bot.states import NoteStates
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.note_service import NoteService

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 10


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID when the user is registered."""
    user_repo = UserRepository(session)
    user = await user_repo.get_by_telegram_id(update.effective_user.id)
    return user.id if user else update.effective_user.id


def _parse_id(data: str) -> int:
    """Parse numeric ID from callback data."""
    return int(data.split(":", 1)[1])


def _store_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember the edited bot message so text input can update it later."""
    query = update.callback_query
    if not query or not query.message:
        return

    context.user_data["note_prompt_chat_id"] = query.message.chat_id
    context.user_data["note_prompt_message_id"] = query.message.message_id


async def _edit_prompt_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit stored prompt after text input, or reply as fallback."""
    chat_id = context.user_data.pop("note_prompt_chat_id", None)
    message_id = context.user_data.pop("note_prompt_message_id", None)

    if chat_id and message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return

    await update.message.reply_text(text, reply_markup=reply_markup)


async def _render_notes_page(user_id: int, page: int = 0) -> tuple[str, object]:
    """Build text and keyboard for a notes page."""
    page = max(page, 0)

    async with async_session_maker() as session:
        note_service = NoteService(session)
        notes, total = await note_service.get_notes_list(
            user_id=user_id,
            archived=False,
            page=page,
            page_size=ITEMS_PER_PAGE,
        )

    if not notes and page > 0:
        return await _render_notes_page(user_id, page - 1)

    if not notes:
        text = "📝 Заметки\n\nУ вас пока нет заметок. Создайте первую."
    else:
        current_page = page + 1
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        lines = [f"📝 Заметки ({total} всего)", f"Страница {current_page}/{total_pages}", ""]
        for index, note in enumerate(notes, page * ITEMS_PER_PAGE + 1):
            title = note.title or "Без названия"
            lines.append(f"{index}. 📝 {title}")
        text = "\n".join(lines)

    keyboard = get_notes_list_keyboard(
        notes,
        page=page,
        has_next=(page + 1) * ITEMS_PER_PAGE < total,
    )
    return text, keyboard


async def _render_note_view(note_id: int, user_id: int) -> tuple[str | None, object | None]:
    """Build text and keyboard for one note."""
    async with async_session_maker() as session:
        note_service = NoteService(session)
        note = await note_service.get_note(note_id, user_id)

    if not note:
        return None, None

    title = note.title or "Без названия"
    body = note.text or "Пусто"
    status = "Архив" if note.is_archived else "Активная"
    text = f"📝 {title}\n\n{body}\n\nСтатус: {status}"
    return text, get_note_view_keyboard(note.id, note.is_archived)


async def _show_notes_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> int:
    """Show paginated notes list."""
    query = update.callback_query
    if query:
        await query.answer()

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_notes_page(user_id, page)

    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return ConversationHandler.END


async def notes_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show first page of notes."""
    return await _show_notes_page(update, context, page=0)


async def notes_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show selected page of notes."""
    page = _parse_id(update.callback_query.data)
    return await _show_notes_page(update, context, page)


async def note_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start note creation."""
    _store_prompt_message(update, context)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "📝 Создание заметки\n\nВведите заголовок:",
            reply_markup=get_cancel_inline_keyboard(),
        )
    else:
        await update.message.reply_text(
            "📝 Создание заметки\n\nВведите заголовок:",
            reply_markup=get_cancel_keyboard(),
        )

    return NoteStates.WAIT_TITLE


async def note_save_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save note title and ask for body."""
    title = update.message.text.strip()
    context.user_data["note_title"] = title

    await _edit_prompt_or_reply(
        update,
        context,
        f"Заголовок: {title}\n\nВведите текст заметки или отправьте /skip:",
        get_back_home_inline_keyboard(),
    )

    return NoteStates.WAIT_BODY


async def note_skip_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip note body and create note."""
    return await _save_note(update, context, text=None)


async def note_save_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save note body and create note."""
    return await _save_note(update, context, text=update.message.text.strip())


async def _save_note(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str | None,
) -> int:
    """Persist note and show it."""
    title = context.user_data.get("note_title", "Без названия")

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note_service = NoteService(session)
        note = await note_service.create_note(
            user_id=user_id,
            title=title,
            text=text,
        )
        await session.commit()
        note_id = note.id

    rendered_text, keyboard = await _render_note_view(note_id, user_id)
    await update.message.reply_text(rendered_text, reply_markup=keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def note_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show note view."""
    query = update.callback_query
    await query.answer()

    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_note_view(note_id, user_id)
    if not text:
        await query.edit_message_text("❌ Заметка не найдена")
        return ConversationHandler.END

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_edit_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show note edit menu."""
    query = update.callback_query
    await query.answer()

    note_id = _parse_id(query.data)
    await query.edit_message_text(
        "Что изменить?",
        reply_markup=get_note_edit_keyboard(note_id),
    )
    return ConversationHandler.END


async def note_edit_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new note title."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    context.user_data["editing_note_id"] = note_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        "✏️ Введите новый заголовок:",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_EDIT_TITLE


async def note_edit_body_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new note body."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    context.user_data["editing_note_id"] = note_id
    _store_prompt_message(update, context)

    await query.edit_message_text(
        "📝 Введите новый текст заметки:",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_EDIT_BODY


async def note_save_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save edited note title."""
    return await _save_note_edit(update, context, title=update.message.text.strip())


async def note_save_edit_body(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save edited note body."""
    return await _save_note_edit(update, context, text=update.message.text.strip())


async def _save_note_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    title: str | None = None,
    text: str | None = None,
) -> int:
    """Persist edited note and show it."""
    note_id = context.user_data.get("editing_note_id")

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note_service = NoteService(session)
        note = await note_service.update_note(
            note_id=note_id,
            user_id=user_id,
            title=title,
            text=text,
        )
        await session.commit()

    if not note:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Заметка не найдена",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    rendered_text, keyboard = await _render_note_view(note.id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)

    context.user_data.clear()
    return ConversationHandler.END


async def note_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Delete note and return to notes list."""
    query = update.callback_query
    await query.answer()

    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note_service = NoteService(session)
        await note_service.delete_note(note_id, user_id)
        await session.commit()

    text, keyboard = await _render_notes_page(user_id, page=0)
    await query.edit_message_text(text, reply_markup=keyboard)
    context.user_data.clear()
    return ConversationHandler.END


async def note_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Archive note and return to notes list."""
    query = update.callback_query
    await query.answer()

    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note_service = NoteService(session)
        await note_service.archive_note(note_id, user_id)
        await session.commit()

    text, keyboard = await _render_notes_page(user_id, page=0)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Restore archived note and show it."""
    query = update.callback_query
    await query.answer()

    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note_service = NoteService(session)
        note = await note_service.restore_note(note_id, user_id)
        await session.commit()

    if not note:
        await query.edit_message_text("❌ Заметка не найдена")
        return ConversationHandler.END

    text, keyboard = await _render_note_view(note.id, user_id)
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


note_create_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(note_create_start, pattern="^note_create$"),
    ],
    states={
        NoteStates.WAIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_title),
        ],
        NoteStates.WAIT_BODY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_body),
            CommandHandler("skip", note_skip_body),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)


note_edit_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(note_edit_title_start, pattern="^note_edit_title:"),
        CallbackQueryHandler(note_edit_body_start, pattern="^note_edit_body:"),
    ],
    states={
        NoteStates.WAIT_EDIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_edit_title),
        ],
        NoteStates.WAIT_EDIT_BODY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_edit_body),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)
