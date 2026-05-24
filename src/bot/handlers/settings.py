"""
Settings handlers.

Timezone selection, statistics, user preferences.
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
    get_settings_keyboard,
    get_timezone_keyboard,
    get_back_home_inline_keyboard,
    get_cancel_keyboard,
    get_cancel_inline_keyboard,
)
from src.bot.states import SettingsStates
from src.db.session import async_session_maker
from src.services.settings_service import SettingsService
from src.services.subscription_service import SubscriptionService
from src.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


async def settings_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show settings menu."""
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()
    
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
    
    timezone_str = user.timezone if user else "UTC"
    
    text = (
        "⚙️ Настройки\n\n"
        f"🌍 Часовой пояс: {timezone_str}\n\n"
        "Выберите раздел:"
    )
    
    if query:
        await query.edit_message_text(text, reply_markup=get_settings_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=get_settings_keyboard())
    
    return ConversationHandler.END


async def settings_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show timezone selection."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🌍 Часовой пояс\n\nВыберите из списка или введите вручную:",
        reply_markup=get_timezone_keyboard(),
    )
    
    return SettingsStates.WAIT_TIMEZONE


async def settings_set_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set timezone from preset."""
    query = update.callback_query
    await query.answer()
    
    tz_map = {
        "tz_europe_moscow": "Europe/Moscow",
        "tz_america_new_york": "America/New_York",
        "tz_america_los_angeles": "America/Los_Angeles",
        "tz_europe_london": "Europe/London",
        "tz_europe_berlin": "Europe/Berlin",
    }
    
    selected = query.data
    timezone_str = tz_map.get(selected, "UTC")
    
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        if user:
            user.timezone = timezone_str
            await session.commit()
    
    await query.edit_message_text(
        f"✅ Часовой пояс установлен: {timezone_str}",
        reply_markup=get_back_home_inline_keyboard(),
    )
    
    return ConversationHandler.END


async def settings_timezone_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Custom timezone input."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ Введите часовой пояс\n\n"
        "Примеры: Europe/Moscow, America/New_York, Asia/Tokyo",
        reply_markup=get_cancel_inline_keyboard(),
    )
    
    return SettingsStates.WAIT_TIMEZONE_CUSTOM


async def settings_save_custom_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save custom timezone."""
    import pytz
    
    timezone_str = update.message.text.strip()
    user_id = update.effective_user.id
    
    try:
        # Validate timezone
        pytz.timezone(timezone_str)
        
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(user_id)
            
            if user:
                user.timezone = timezone_str
                await session.commit()
        
        await update.message.reply_text(
            f"✅ Часовой пояс установлен: {timezone_str}",
            reply_markup=get_back_home_inline_keyboard(),
        )
    except pytz.exceptions.UnknownTimeZoneError:
        await update.message.reply_text(
            f"❌ Неверный часовой пояс: {timezone_str}\n\n"
            f"Попробуйте ещё раз или нажмите Отмена:",
            reply_markup=get_cancel_keyboard(),
        )
        return SettingsStates.WAIT_TIMEZONE_CUSTOM
    
    context.user_data.clear()
    return ConversationHandler.END


async def settings_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show user statistics."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(user_id)
        
        settings_service = SettingsService(session)
        stats = await settings_service.get_stats(user.id if user else user_id)
    
    text = (
        "📊 Статистика\n\n"
        f"📋 Списки: {stats['lists']['owned']}\n"
        f"👥 Общие списки: {stats['lists']['shared']}\n"
        f"💊 Лекарства: {stats['medications']['active']} активных, "
        f"{stats['medications']['archived']} в архиве\n"
        f"🚗 Авто: {stats['driver']['vehicles_count']}, "
        f"заправок: {stats['driver']['fuel_entries_count']}, "
        f"топливо: {stats['driver']['fuel_total_cost']:.0f} ₽\n"
        f"⏰ Напоминаний:\n"
        f"  • Активных: {stats['reminders']['active']}\n"
        f"  • Выполненных: {stats['reminders']['done']}\n"
        f"  • Отменённых: {stats['reminders']['canceled']}\n"
        f"  • Пропущенных: {stats['reminders']['missed']}\n"
        f"📝 Заметки (скрытый модуль): {stats['notes']['active']} активных, "
        f"{stats['notes']['archived']} в архиве\n"
    )
    
    await query.edit_message_text(
        text,
        reply_markup=get_back_home_inline_keyboard(),
    )
    
    return ConversationHandler.END


async def settings_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show current subscription and planned paid features."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(
            telegram_id=telegram_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        subscription_service = SubscriptionService(session)
        access = await subscription_service.get_access_context(user.id)
        await session.commit()

    feature_labels = {
        "lists": "списки",
        "shared_lists": "общие списки",
        "reminders": "напоминания",
        "medications": "лекарства",
        "advanced_history": "расширенная история",
        "priority_support": "приоритетная поддержка",
        "exports": "экспорт данных",
        "family_access": "семейный доступ",
    }
    features = ", ".join(
        feature_labels.get(feature, feature)
        for feature in access["features"]
    )
    admin_note = "\n\n🔐 У вас админский доступ для отладки." if access["is_admin"] else ""

    text = (
        "💳 Подписка\n\n"
        f"Текущий тариф: {access['plan_title']} ({access['plan']})\n"
        f"Статус: {access['subscription_status']}\n\n"
        f"Доступно сейчас: {features}.\n\n"
        "На этапе отладки базовые функции доступны всем пользователям. "
        "Оплата пока не подключена, но бот уже хранит тариф пользователя и готов к будущим ограничениям функций."
        f"{admin_note}"
    )

    await query.edit_message_text(
        text,
        reply_markup=get_back_home_inline_keyboard(),
    )

    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current operation."""
    await update.message.reply_text(
        "❌ Отменено",
        reply_markup=get_back_home_inline_keyboard(),
    )
    context.user_data.clear()
    return ConversationHandler.END


# Conversation handlers
settings_timezone_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(settings_timezone_callback, pattern="^settings_timezone$"),
    ],
    states={
        SettingsStates.WAIT_TIMEZONE: [
            CallbackQueryHandler(settings_timezone_custom, pattern="^tz_custom$"),
            CallbackQueryHandler(settings_set_timezone, pattern="^tz_"),
        ],
        SettingsStates.WAIT_TIMEZONE_CUSTOM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, settings_save_custom_timezone),
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_handler),
    ],
)
