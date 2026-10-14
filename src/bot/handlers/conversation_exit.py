"""Leaving a half-finished wizard through the main menu, /start or «В меню».

Conversations used to stay open until /cancel. While one was waiting for text,
pressing a main menu button sent that label into the wizard (a reminder titled
"📋 Списки"), and every later text message went to the stale wizard instead of
the section the user had opened. Text inputs now ignore main menu labels, and
the menu, /start and «В меню» close any open wizard before doing their job.
"""

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

MAIN_MENU_LABELS = [
    "📋 Списки",
    "📝 Заметки",
    "💊 Лекарства",
    "⏰ Напоминания",
    "🚗 Водитель",
    "🚗 Для водителя",
    "🌐 Web / приложение",
    "🌐 Web-версия",
    "⚙️ Настройки",
    "👥 Поделиться ботом",
    "⌨️ Скрыть меню",
    "⌨️ Скрыть",
    "❓ Помощь",
]

MAIN_MENU_FILTER = filters.Text(MAIN_MENU_LABELS)

# A wizard nobody touched for this long is closed, so it cannot swallow text
# typed much later for another section.
WIZARD_TIMEOUT_SECONDS = 15 * 60

# Use for every wizard text input instead of `filters.TEXT & ~filters.COMMAND`.
TEXT_INPUT = filters.TEXT & ~filters.COMMAND & ~MAIN_MENU_FILTER


async def _exit_via_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.bot.handlers.navigation import menu_button_handler

    context.user_data.clear()
    await menu_button_handler(update, context)
    return ConversationHandler.END


async def _exit_via_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.bot.handlers.navigation import start_command

    context.user_data.clear()
    await start_command(update, context)
    return ConversationHandler.END


async def _exit_via_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.bot.handlers.navigation import home_callback

    context.user_data.clear()
    await home_callback(update, context)
    return ConversationHandler.END


def exit_fallbacks() -> list:
    """Fallbacks that close a wizard when the user navigates away."""
    return [
        CommandHandler("start", _exit_via_start),
        MessageHandler(MAIN_MENU_FILTER, _exit_via_menu),
        CallbackQueryHandler(_exit_via_home, pattern="^home$"),
    ]
