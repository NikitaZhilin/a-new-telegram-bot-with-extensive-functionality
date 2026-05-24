"""
Main menu and navigation handlers.

Handles /start, /help, and main menu button clicks.
"""

import logging
from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from src.bot.keyboards import (
    get_home_inline_keyboard,
    get_main_menu_inline_keyboard,
    get_main_menu_keyboard,
)
from src.config import settings
from src.repositories.user_repo import UserRepository
from src.db.session import async_session_maker

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    
    # Register or update user in database
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        await session.commit()

    if context.args and context.args[0].startswith("import_list_"):
        from src.bot.handlers.lists import import_list_token

        await import_list_token(
            update,
            context,
            context.args[0].removeprefix("import_list_"),
        )
        return

    if context.args and context.args[0].startswith("join_list_"):
        from src.bot.handlers.lists import join_list_token

        await join_list_token(
            update,
            context,
            context.args[0].removeprefix("join_list_"),
        )
        return
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я бот-напоминалка. Я помогу тебе:\n"
        f"📋 Вести списки дел\n"
        f"💊 Следить за приемом лекарств\n"
        f"⏰ Создавать напоминания\n"
        f"🚗 Вести автомобильный журнал\n\n"
        f"Выбери раздел в меню ниже 👇",
        reply_markup=get_main_menu_keyboard(),
    )
    
    logger.info(f"User {user.id} started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "📖 *Помощь*\n\n"
        "📋 *Списки*\n"
        "Создавай списки дел или покупок. "
        "Добавляй элементы по одному или пачкой. "
        "Отмечай выполненные и делись копией списка с другим пользователем.\n\n"
        "💊 *Прием лекарств*\n"
        "Добавляй препараты, важность, дозировку, инструкции и напоминания 1-3 раза в день.\n\n"
        "⏰ *Напоминания*\n"
        "Создавай напоминания на конкретное время. "
        "Поддерживаются повторы: ежедневно, еженедельно, ежемесячно.\n\n"
        "🚗 *Для водителя*\n"
        "Автомобильный журнал: пробег, топливо, ТО, жидкости, запчасти, мойка, "
        "шины, документы и расходы.\n\n"
        "⚙️ *Настройки*\n"
        "Установи часовой пояс для корректного времени напоминаний.\n\n"
        "Используй кнопки меню для навигации."
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_home_inline_keyboard(),
    )


async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu button clicks."""
    text = update.message.text

    if text == "📝 Заметки":
        await update.message.reply_text(
            "📝 Раздел заметок убран из бота.\n\n"
            "Я обновил нижнее меню, используйте актуальные разделы.",
            reply_markup=get_main_menu_keyboard(),
        )
        return
    if text == "📋 Списки":
        await show_lists_menu(update, context)
        return
    if text == "💊 Лекарства":
        await show_medications_menu(update, context)
        return
    if text == "⏰ Напоминания":
        await show_reminders_menu(update, context)
        return
    if text == "🚗 Для водителя":
        await show_driver_menu(update, context)
        return
    if text == "⚙️ Настройки":
        await show_settings_menu(update, context)
        return
    if text == "❓ Помощь":
        await help_command(update, context)
        return
    if text == "👥 Поделиться ботом":
        await share_bot_message(update, context)
        return

    if text == "📋 Списки":
        await show_lists_menu(update, context)
    elif text == "💊 Лекарства":
        await show_medications_menu(update, context)
    elif text == "⏰ Напоминания":
        await show_reminders_menu(update, context)
    elif text == "🚗 Для водителя":
        await show_driver_menu(update, context)
    elif text == "⚙️ Настройки":
        await show_settings_menu(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    elif text == "👥 Поделиться ботом":
        await share_bot_message(update, context)


async def show_lists_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show lists section menu."""
    from src.bot.handlers.lists import lists_list_callback
    await lists_list_callback(update, context)


async def show_medications_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show medications section menu."""
    from src.bot.handlers.medications import medications_list_callback
    await medications_list_callback(update, context)


async def show_reminders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show reminders section menu."""
    from src.bot.handlers.reminders import reminders_list_callback
    await reminders_list_callback(update, context)


async def show_driver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show driver assistant menu."""
    from src.bot.handlers.driver import driver_menu_callback

    await driver_menu_callback(update, context)


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    from src.bot.handlers.settings import settings_menu_callback
    await settings_menu_callback(update, context)


def _share_bot_text() -> str:
    """Build bot sharing text."""
    if settings.BOT_USERNAME:
        return (
            "👥 Поделиться ботом\n\n"
            "Отправьте человеку эту ссылку:\n"
            f"https://t.me/{settings.BOT_USERNAME}\n\n"
            "После `/start` у него будут свои личные списки, лекарства и напоминания. "
            "Списком можно поделиться отдельно через кнопку `📤 Поделиться` внутри списка."
        )

    return (
        "👥 Поделиться ботом\n\n"
        "Укажите `BOT_USERNAME` в `.env`, чтобы бот мог показывать готовую ссылку. "
        "Пока можно переслать человеку имя бота вручную."
    )


async def share_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send bot sharing instructions from reply keyboard."""
    await update.message.reply_text(
        _share_bot_text(),
        reply_markup=get_home_inline_keyboard(),
    )


async def share_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot sharing instructions from inline keyboard."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _share_bot_text(),
        reply_markup=get_home_inline_keyboard(),
    )


async def removed_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle stale notes buttons from older bot messages."""
    query = update.callback_query
    await query.answer("Раздел заметок убран")
    await query.edit_message_text(
        "📝 Раздел заметок убран из бота.\n\n"
        "Сейчас доступны списки, лекарства, напоминания и настройки.",
        reply_markup=get_main_menu_inline_keyboard(),
    )


async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'back' callback."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text="Выберите раздел:",
        reply_markup=get_main_menu_inline_keyboard(),
    )
    return
    
    await query.edit_message_text(
        text="Навигация назад...",
        reply_markup=get_home_inline_keyboard(),
    )


async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'home' callback - return to main menu."""
    query = update.callback_query
    await query.answer("В главное меню")
    
    # Clear conversation state
    context.user_data.clear()

    await query.edit_message_text(
        text="🏠 Главное меню\n\nВыберите раздел:",
        reply_markup=get_main_menu_inline_keyboard(),
    )
    return
    
    await query.edit_message_text(
        text="🏠 Главное меню\n\nВыбери раздел:",
        reply_markup=get_main_menu_keyboard(),
    )


# Handlers instances

start_handler = CommandHandler("start", start_command)
help_handler = CommandHandler("help", help_command)

menu_button_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    menu_button_handler,
)

back_handler = CallbackQueryHandler(back_callback, pattern="^back$")
home_handler = CallbackQueryHandler(home_callback, pattern="^home$")
