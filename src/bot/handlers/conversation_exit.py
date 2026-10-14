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


_application = None
_checking = False


def bind_application(application) -> None:
    """Remember the application so wizards can hand buttons to regular screens."""
    global _application
    _application = application


class LeaveWizardHandler(CallbackQueryHandler):
    """Fallback for a button that belongs to another screen or wizard.

    Wizard screens show navigation buttons («К лекарству», «К спискам», …).
    Pressing one opened that screen but left the wizard waiting for text, so
    the next message was swallowed by it. Now the wizard ends and the button
    is handed to its normal handler.
    """

    def __init__(self):
        super().__init__(self._unused)

    @staticmethod
    async def _unused(update, context):  # pragma: no cover - handle_update is overridden
        return ConversationHandler.END

    def check_update(self, update):
        global _checking
        if _checking or _application is None:
            return None
        if not isinstance(update, Update) or update.callback_query is None:
            return None
        _checking = True
        try:
            for handler in _application.handlers.get(0, []):
                if isinstance(handler, LeaveWizardHandler):
                    continue
                if getattr(handler, "callback", None) in (stale_button_callback, noop_callback):
                    continue
                if isinstance(handler, (CallbackQueryHandler, ConversationHandler)):
                    result = handler.check_update(update)
                    if result is not None and result is not False:
                        return handler, result
        finally:
            _checking = False
        return None

    async def handle_update(self, update, application, check_result, context):
        handler, result = check_result
        await handler.handle_update(update, application, result, context)
        return ConversationHandler.END


async def stale_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Answer a button nobody handles any more instead of an endless spinner.

    Wizard state lives in memory: after a restart/deploy or the 15-minute
    timeout, wizard buttons («Сегодня», «09:00», «Полный бак», «Отмена»…)
    had no handler and just kept loading.
    """
    query = update.callback_query
    if query is None:
        return
    context.user_data.clear()
    from src.bot.keyboards import get_home_inline_keyboard

    if (query.data or "") in {"cancel", "rem_cancel_create", "list_voice_cancel"}:
        await query.answer("Отменено")
        try:
            await query.edit_message_text("❌ Отменено", reply_markup=get_home_inline_keyboard())
        except Exception:
            pass
        return
    await query.answer(
        "Эта кнопка устарела — сценарий уже закрыт. Откройте раздел заново.",
        show_alert=True,
    )
    try:
        await query.edit_message_reply_markup(reply_markup=get_home_inline_keyboard())
    except Exception:
        pass


async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Informational buttons: just stop the spinner."""
    if update.callback_query is not None:
        await update.callback_query.answer()


def exit_fallbacks() -> list:
    """Fallbacks that close a wizard when the user navigates away."""
    return [
        CommandHandler("start", _exit_via_start),
        MessageHandler(MAIN_MENU_FILTER, _exit_via_menu),
        CallbackQueryHandler(_exit_via_home, pattern="^home$"),
    ]


def leave_wizard_fallbacks() -> list:
    """Must be the last fallbacks: any other screen's button ends the wizard."""
    return [LeaveWizardHandler()]
