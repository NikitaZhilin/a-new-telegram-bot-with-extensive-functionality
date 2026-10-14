"""Text sent outside any section.

Before, the bot stayed silent on such messages, so people who just typed
"купить молоко" or "завтра в 10 врач" thought the bot was broken. Now it
answers and offers to turn the text into a reminder or a note.
"""

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.db.session import async_session_maker

TOKEN_LIKE = re.compile(r"^[A-Za-z0-9_\-]{24,}$")


def free_text_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏰ Напоминание", callback_data="free_reminder"),
            InlineKeyboardButton("📝 Заметка", callback_data="free_note"),
        ],
        [InlineKeyboardButton("🏠 В меню", callback_data="home")],
    ])


async def free_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    text = (message.text or "").strip() if message else ""
    if not text:
        return
    if TOKEN_LIKE.match(text):
        await message.reply_text(
            "Похоже, это ключ для входа в web-версию. Его не нужно отправлять боту — "
            "откройте ссылку из сообщения с ключом в браузере.",
        )
        return
    context.user_data["free_text"] = text[:1000]
    await message.reply_text(
        "Что сделать с этим текстом?\n\n"
        "💡 Напоминание можно написать сразу с временем: «завтра в 10 позвонить маме».",
        reply_markup=free_text_keyboard(),
    )


async def free_note_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save the free text as a note."""
    from src.bot.keyboards import get_back_home_inline_keyboard
    from src.repositories.user_repo import UserRepository
    from src.services.note_service import NoteService

    query = update.callback_query
    text = (context.user_data.pop("free_text", None) or "").strip()
    if not text:
        await query.answer("Текст не найден — напишите его ещё раз.", show_alert=True)
        return
    await query.answer()
    first_line = text.splitlines()[0]
    title = first_line if len(first_line) <= 60 else first_line[:57] + "…"
    body = text if (len(text.splitlines()) > 1 or len(first_line) > 60) else None
    async with async_session_maker() as session:
        tg = update.effective_user
        user = await UserRepository(session).get_or_create(
            telegram_id=tg.id, username=tg.username, first_name=tg.first_name, last_name=tg.last_name
        )
        note = await NoteService(session).create_note(user.id, title, body)
        await session.commit()
        note_id = note.id
    await query.edit_message_text(
        f"📝 Заметка сохранена: {title}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Открыть заметку", callback_data=f"note_view:{note_id}")],
            *get_back_home_inline_keyboard("notes_list").inline_keyboard,
        ]),
    )
