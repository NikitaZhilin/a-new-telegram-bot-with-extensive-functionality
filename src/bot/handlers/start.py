"""Start handler."""

import logging
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот-напоминалка. Я помогу тебе:\n"
        f"📝 Записывать заметки\n"
        f"⏰ Создавать напоминания\n"
        f"✅ Вести списки дел\n\n"
        f"Нажми /help для подробной информации."
    )


# Handler instance
start_handler = CommandHandler("start", start)
