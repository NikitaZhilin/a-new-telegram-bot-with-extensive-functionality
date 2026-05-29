"""Telegram handlers for standalone text notes."""

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
    get_note_category_keyboard,
    get_note_delete_confirm_keyboard,
    get_note_view_keyboard,
    get_notes_list_keyboard,
)
from src.bot.states import NoteStates
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.note_service import (
    DEFAULT_NOTE_CATEGORY,
    NOTE_CATEGORIES,
    NoteService,
    note_category_label,
)
from src.utils.text import truncate

logger = logging.getLogger(__name__)

NOTES_PER_PAGE = 8


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID, creating the user when needed."""
    telegram_user = update.effective_user
    user = await UserRepository(session).get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )
    await session.commit()
    return user.id


def _parse_id(data: str) -> int:
    """Parse note ID from callback data."""
    return int(data.split(":", 1)[1])


def _store_prompt_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember bot prompt message for later edits after user text input."""
    query = update.callback_query
    if not query or not query.message:
        return
    context.user_data["note_prompt_chat_id"] = query.message.chat_id
    context.user_data["note_prompt_message_id"] = query.message.message_id


def _clear_prompt_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forget stored prompt message after a one-step text flow."""
    context.user_data.pop("note_prompt_chat_id", None)
    context.user_data.pop("note_prompt_message_id", None)


def _notes_category_filter(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Return current notes category filter."""
    value = context.user_data.get("notes_category_filter")
    return value if value in NOTE_CATEGORIES else None


def _notes_pinned_filter(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return whether the current notes list shows only pinned notes."""
    return bool(context.user_data.get("notes_pinned_only"))


async def _edit_prompt_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup,
) -> None:
    """Edit stored bot prompt after user text input, or reply as fallback."""
    chat_id = context.user_data.get("note_prompt_chat_id")
    message_id = context.user_data.get("note_prompt_message_id")
    if chat_id and message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        return
    await update.message.reply_text(text, reply_markup=reply_markup)


async def _delete_user_message(update: Update) -> None:
    """Best-effort cleanup for typed note content."""
    if not update.message:
        return
    try:
        await update.message.delete()
    except Exception:
        logger.debug("Could not delete note input message", exc_info=True)


def _render_note_text(note) -> str:
    """Build a compact note view."""
    body = (note.text or "").strip()
    if not body:
        body = "Текст заметки пока пуст."
    category = note_category_label(getattr(note, "category", None))
    pin_line = "📌 Закреплена\n" if getattr(note, "is_pinned", False) else ""
    return f"📝 {note.title}\n{pin_line}🏷 Категория: {category}\n\n{truncate(body, 3500)}"


async def _render_notes_page(
    user_id: int,
    page: int,
    *,
    search_query: str | None = None,
    category: str | None = None,
    pinned_only: bool = False,
) -> tuple[str, object]:
    """Build notes list text and keyboard."""
    page = max(page, 0)
    search_value = (search_query or "").strip()
    category_value = category if category in NOTE_CATEGORIES else None
    async with async_session_maker() as session:
        notes, total = await NoteService(session).list_notes(
            user_id,
            page=page,
            page_size=NOTES_PER_PAGE,
            search_query=search_value,
            category=category_value,
            pinned_only=pinned_only,
        )
    if not notes and page > 0:
        return await _render_notes_page(
            user_id,
            page - 1,
            search_query=search_value,
            category=category_value,
            pinned_only=pinned_only,
        )

    header_lines = ["📝 Заметки"]
    if pinned_only:
        header_lines.append("Фильтр: закрепленные")
    if search_value:
        header_lines.append(f"Поиск: «{search_value}»")
    if category_value:
        header_lines.append(f"Категория: {note_category_label(category_value)}")

    if not notes:
        if search_value or category_value or pinned_only:
            header = "\n".join(header_lines)
            text = f"{header}\n\nНичего не найдено."
        else:
            text = (
                "📝 Заметки\n\n"
                "Заметок пока нет. Создайте первую заметку для рецепта, инструкции или любого текста, который нужно просто хранить и читать."
            )
    else:
        current_page = page + 1
        total_pages = max(1, (total + NOTES_PER_PAGE - 1) // NOTES_PER_PAGE)
        if search_value or category_value or pinned_only:
            header_lines.append(f"Найдено: {total}")
            header_lines.append(f"Страница {current_page}/{total_pages}")
            text = "\n".join(header_lines)
        else:
            text = f"📝 Заметки ({total} всего)\nСтраница {current_page}/{total_pages}"

    return text, get_notes_list_keyboard(
        notes,
        page=page,
        has_next=(page + 1) * NOTES_PER_PAGE < total,
        search_active=bool(search_value),
        category_active=bool(category_value),
        pinned_active=pinned_only,
    )


async def _render_note_view(note_id: int, user_id: int) -> tuple[str | None, object | None]:
    """Build one note view with ownership check."""
    async with async_session_maker() as session:
        note = await NoteService(session).get_note(note_id, user_id)
    if not note:
        return None, None
    return _render_note_text(note), get_note_view_keyboard(note.id, is_pinned=note.is_pinned)


async def notes_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show user's notes."""
    query = update.callback_query
    if query:
        await query.answer()

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    search_query = context.user_data.get("notes_search_query")
    category = _notes_category_filter(context)
    pinned_only = _notes_pinned_filter(context)
    text, keyboard = await _render_notes_page(
        user_id,
        page=0,
        search_query=search_query,
        category=category,
        pinned_only=pinned_only,
    )
    if query:
        await query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def notes_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show paginated notes page."""
    query = update.callback_query
    await query.answer()
    page = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    search_query = context.user_data.get("notes_search_query")
    category = _notes_category_filter(context)
    pinned_only = _notes_pinned_filter(context)
    text, keyboard = await _render_notes_page(
        user_id,
        page=page,
        search_query=search_query,
        category=category,
        pinned_only=pinned_only,
    )
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def notes_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a note search query."""
    query = update.callback_query
    await query.answer()
    _store_prompt_message(update, context)
    await query.edit_message_text(
        "🔎 Поиск по заметкам\n\nВведите слово или фразу из названия или текста заметки.",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_SEARCH


async def notes_search_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save search query and show filtered notes."""
    search_query = (update.message.text or "").strip()
    await _delete_user_message(update)
    if not search_query:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Поисковый запрос не может быть пустым. Введите слово или фразу.",
            get_cancel_inline_keyboard(),
        )
        return NoteStates.WAIT_SEARCH

    context.user_data["notes_search_query"] = search_query
    try:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
        category = _notes_category_filter(context)
        text, keyboard = await _render_notes_page(
            user_id,
            page=0,
            search_query=search_query,
            category=category,
            pinned_only=_notes_pinned_filter(context),
        )
    except ValueError as exc:
        await _edit_prompt_or_reply(update, context, f"❌ {exc}", get_cancel_inline_keyboard())
        return NoteStates.WAIT_SEARCH

    await _edit_prompt_or_reply(update, context, text, keyboard)
    _clear_prompt_context(context)
    return ConversationHandler.END


async def notes_search_clear_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Clear current note search filter."""
    query = update.callback_query
    await query.answer("Фильтры сброшены")
    context.user_data.pop("notes_search_query", None)
    context.user_data.pop("notes_category_filter", None)
    context.user_data.pop("notes_pinned_only", None)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_notes_page(
        user_id,
        page=0,
        search_query=context.user_data.get("notes_search_query"),
        category=_notes_category_filter(context),
        pinned_only=_notes_pinned_filter(context),
    )
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def notes_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show note category filter choices."""
    query = update.callback_query
    await query.answer()
    current = _notes_category_filter(context)
    await query.edit_message_text(
        "🏷 Фильтр заметок\n\nВыберите категорию или покажите все заметки.",
        reply_markup=get_note_category_keyboard(
            prefix="notes_filter",
            selected=current,
            include_all=True,
            back_callback="notes_list",
        ),
    )
    return ConversationHandler.END


async def notes_filter_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Apply note category filter."""
    query = update.callback_query
    await query.answer()
    value = query.data.split(":", 1)[1]
    if value == "all":
        context.user_data.pop("notes_category_filter", None)
    elif value in NOTE_CATEGORIES:
        context.user_data["notes_category_filter"] = value
    else:
        await query.answer("Неизвестная категория", show_alert=True)
        return ConversationHandler.END

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    search_query = context.user_data.get("notes_search_query")
    category = _notes_category_filter(context)
    pinned_only = _notes_pinned_filter(context)
    text, keyboard = await _render_notes_page(
        user_id,
        page=0,
        search_query=search_query,
        category=category,
        pinned_only=pinned_only,
    )
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def notes_pinned_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle the pinned-only notes filter."""
    query = update.callback_query
    next_value = not _notes_pinned_filter(context)
    context.user_data["notes_pinned_only"] = next_value
    await query.answer("Показаны закрепленные" if next_value else "Показаны все заметки")

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_notes_page(
        user_id,
        page=0,
        search_query=context.user_data.get("notes_search_query"),
        category=_notes_category_filter(context),
        pinned_only=next_value,
    )
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show one note."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)

    text, keyboard = await _render_note_view(note_id, user_id)
    if not text:
        await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_pin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle pinned state for a user-owned note."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = NoteService(session)
        note = await service.get_note(note_id, user_id)
        if not note:
            await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
            return ConversationHandler.END
        await service.update_note(note_id, user_id, is_pinned=not note.is_pinned)
        await session.commit()

    text, keyboard = await _render_note_view(note_id, user_id)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for note title."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    _store_prompt_message(update, context)
    await query.edit_message_text(
        "📝 Новая заметка\n\nВведите название заметки.",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_TITLE


async def note_save_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save note title and ask for category."""
    title = update.message.text.strip()
    await _delete_user_message(update)
    if not title:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Название не может быть пустым. Введите название заметки.",
            get_cancel_inline_keyboard(),
        )
        return NoteStates.WAIT_TITLE
    context.user_data["note_title"] = title
    await _edit_prompt_or_reply(
        update,
        context,
        f"📝 {title}\n\nВыберите категорию заметки.",
        get_note_category_keyboard(back_callback="notes_list"),
    )
    return NoteStates.WAIT_CATEGORY


async def note_save_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save note category and ask for text."""
    query = update.callback_query
    await query.answer()
    category = query.data.split(":", 1)[1]
    if category not in NOTE_CATEGORIES:
        await query.answer("Неизвестная категория", show_alert=True)
        return NoteStates.WAIT_CATEGORY

    context.user_data["note_category"] = category
    title = context.user_data.get("note_title", "Новая заметка")
    await query.edit_message_text(
        f"📝 {title}\n🏷 Категория: {note_category_label(category)}\n\nТеперь отправьте текст заметки. Можно несколькими строками.",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_TEXT


async def note_save_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Create note from collected title and text."""
    title = context.user_data.get("note_title")
    category = context.user_data.get("note_category", DEFAULT_NOTE_CATEGORY)
    text_value = update.message.text or ""
    await _delete_user_message(update)
    if not title:
        await _edit_prompt_or_reply(
            update,
            context,
            "❌ Сценарий создания устарел. Откройте заметки заново.",
            get_back_home_inline_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    try:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            note = await NoteService(session).create_note(user_id, title, text_value, category=category)
            await session.commit()
            note_id = note.id
        rendered_text, keyboard = await _render_note_view(note_id, user_id)
    except ValueError as exc:
        await _edit_prompt_or_reply(update, context, f"❌ {exc}", get_cancel_inline_keyboard())
        return NoteStates.WAIT_TEXT

    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)
    context.user_data.clear()
    return ConversationHandler.END


async def note_edit_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new note title."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note = await NoteService(session).get_note(note_id, user_id)

    if not note:
        await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    context.user_data["editing_note_id"] = note_id
    _store_prompt_message(update, context)
    await query.edit_message_text(
        f"✏️ Новое название заметки:\n\n{note.title}",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_EDIT_TITLE


async def note_edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for a new note text."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note = await NoteService(session).get_note(note_id, user_id)

    if not note:
        await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    context.user_data["editing_note_id"] = note_id
    _store_prompt_message(update, context)
    await query.edit_message_text(
        f"📝 Новый текст заметки:\n\n{truncate(note.text or 'Текст заметки пока пуст.', 700)}",
        reply_markup=get_cancel_inline_keyboard(),
    )
    return NoteStates.WAIT_EDIT_TEXT


async def note_edit_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show category choices for an existing note."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        note = await NoteService(session).get_note(note_id, user_id)

    if not note:
        await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    await query.edit_message_text(
        f"🏷 Категория заметки\n\n{note.title}",
        reply_markup=get_note_category_keyboard(
            prefix="note_category_set",
            note_id=note_id,
            selected=getattr(note, "category", DEFAULT_NOTE_CATEGORY),
            back_callback=f"note_view:{note_id}",
        ),
    )
    return ConversationHandler.END


async def note_category_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Update category for an existing note."""
    query = update.callback_query
    await query.answer()
    _, note_id_raw, category = query.data.split(":", 2)
    note_id = int(note_id_raw)

    try:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            note = await NoteService(session).update_note(note_id, user_id, category=category)
            await session.commit()
        if not note:
            raise ValueError("Заметка не найдена")
    except ValueError as exc:
        await query.edit_message_text(f"❌ {exc}", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    rendered_text, keyboard = await _render_note_view(note_id, user_id)
    await query.edit_message_text(rendered_text, reply_markup=keyboard)
    return ConversationHandler.END


async def note_save_title_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save edited title."""
    note_id = context.user_data.get("editing_note_id")
    value = update.message.text.strip()
    await _delete_user_message(update)
    if not note_id:
        await _edit_prompt_or_reply(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    try:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            note = await NoteService(session).update_note(note_id, user_id, title=value)
            await session.commit()
        if not note:
            raise ValueError("Заметка не найдена")
    except ValueError as exc:
        await _edit_prompt_or_reply(update, context, f"❌ {exc}", get_cancel_inline_keyboard())
        return NoteStates.WAIT_EDIT_TITLE

    rendered_text, keyboard = await _render_note_view(note_id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)
    context.user_data.clear()
    return ConversationHandler.END


async def note_save_text_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save edited text."""
    note_id = context.user_data.get("editing_note_id")
    value = update.message.text or ""
    await _delete_user_message(update)
    if not note_id:
        await _edit_prompt_or_reply(update, context, "❌ Сценарий редактирования устарел.", get_back_home_inline_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    try:
        async with async_session_maker() as session:
            user_id = await _get_app_user_id(update, session)
            note = await NoteService(session).update_note(note_id, user_id, text=value)
            await session.commit()
        if not note:
            raise ValueError("Заметка не найдена")
    except ValueError as exc:
        await _edit_prompt_or_reply(update, context, f"❌ {exc}", get_cancel_inline_keyboard())
        return NoteStates.WAIT_EDIT_TEXT

    rendered_text, keyboard = await _render_note_view(note_id, user_id)
    await _edit_prompt_or_reply(update, context, rendered_text, keyboard)
    context.user_data.clear()
    return ConversationHandler.END


async def note_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask for note deletion confirmation."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)
    await query.edit_message_text(
        "Удалить заметку? Она пропадет из списка заметок.",
        reply_markup=get_note_delete_confirm_keyboard(note_id),
    )
    return ConversationHandler.END


async def note_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Archive note and return to notes list."""
    query = update.callback_query
    await query.answer()
    note_id = _parse_id(query.data)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        deleted = await NoteService(session).archive_note(note_id, user_id)
        await session.commit()

    if not deleted:
        await query.edit_message_text("❌ Заметка не найдена.", reply_markup=get_back_home_inline_keyboard())
        return ConversationHandler.END

    text, keyboard = await _render_notes_page(user_id, page=0)
    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current note operation."""
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


note_create_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(note_create_start, pattern="^note_create$")],
    states={
        NoteStates.WAIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_title),
        ],
        NoteStates.WAIT_CATEGORY: [
            CallbackQueryHandler(note_save_category, pattern="^note_category:"),
            CallbackQueryHandler(notes_list_callback, pattern="^notes_list$"),
        ],
        NoteStates.WAIT_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_text),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)


notes_search_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(notes_search_start, pattern="^notes_search$")],
    states={
        NoteStates.WAIT_SEARCH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, notes_search_save),
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
        CallbackQueryHandler(note_edit_text_start, pattern="^note_edit_text:"),
    ],
    states={
        NoteStates.WAIT_EDIT_TITLE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_title_edit),
        ],
        NoteStates.WAIT_EDIT_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, note_save_text_edit),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
        CallbackQueryHandler(cancel_handler, pattern="^cancel$"),
    ],
)
