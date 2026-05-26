"""
Settings handlers.

Timezone selection, statistics, user preferences.
"""

import logging
from html import escape
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from sqlalchemy import text

from src.config import settings
from src.bot.keyboards import (
    get_about_keyboard,
    get_settings_keyboard,
    get_timezone_keyboard,
    get_back_home_inline_keyboard,
    get_settings_back_home_keyboard,
    get_cancel_keyboard,
    get_cancel_inline_keyboard,
)
from src.bot.states import SettingsStates
from src.db.session import async_session_maker
from src.services.settings_service import SettingsService
from src.services.subscription_service import SubscriptionService
from src.services.web_auth_service import WebAuthService
from src.services.release_info import app_info
from src.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


def _is_admin_user(user, telegram_id: int) -> bool:
    """Return whether Telegram user can see admin-only settings screens."""
    return bool(user and user.is_admin) or telegram_id in settings.admin_telegram_id_set


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
        reply_markup=get_settings_back_home_keyboard(),
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
            reply_markup=get_settings_back_home_keyboard(),
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


def _plural_ru(count: int, one: str, few: str, many: str) -> str:
    """Return a Russian plural form for count."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _people(count: int) -> str:
    return f"{count} {_plural_ru(count, 'человек', 'человека', 'человек')}"


def _records(count: int) -> str:
    return f"{count} {_plural_ru(count, 'запись', 'записи', 'записей')}"


def _rubles(value: float) -> str:
    return f"{value:.0f} ₽"


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
        admin_activity = None
        if user and user.is_admin:
            admin_activity = await settings_service.get_admin_activity_stats(user.id)
    
    text = (
        "📊 Статистика\n\n"
        "Ваши данные\n"
        f"• Личные списки: {_records(stats['lists']['owned'])}\n"
        f"• Общие списки, где есть доступ: {_records(stats['lists']['shared'])}\n"
        f"• Лекарства: активных {stats['medications']['active']}, "
        f"в архиве {stats['medications']['archived']}\n"
        f"• Чек-листы: активных {stats['checklists']['active']}, "
        f"завершенных {stats['checklists']['completed']}, "
        f"отмененных {stats['checklists']['canceled']}\n"
        f"• Автомобили: {stats['driver']['vehicles_count']}; "
        f"заправок: {stats['driver']['fuel_entries_count']}; "
        f"топливо: {_rubles(stats['driver']['fuel_total_cost'])}; "
        f"прочие расходы: {_rubles(stats['driver'].get('expense_total_cost', 0))}; "
        f"документов: {stats['driver'].get('documents_active_count', 0)}\n\n"
        "Напоминания\n"
        f"• Активные: {stats['reminders']['active']}\n"
        f"• Выполненные: {stats['reminders']['done']}\n"
        f"• Отмененные: {stats['reminders']['canceled']}\n"
        f"• Пропущенные: {stats['reminders']['missed']}\n"
    )

    if admin_activity:
        activity = admin_activity["activity"]
        top_domains = "\n".join(
            f"  • {item['label']}: {item['count']}"
            for item in activity["top_domains"][:5]
        ) or "  • пока нет событий"
        top_actions = "\n".join(
            f"  • {item['label']}: {item['count']}"
            for item in activity["top_actions"][:5]
        ) or "  • пока нет событий"
        funnel_lines = []
        for funnel in admin_activity["funnels"]["funnels"][:4]:
            stages = funnel["stages"]
            if not stages:
                continue
            first = stages[0]
            last = stages[-1]
            conversion = round((last["count"] / first["count"]) * 100, 1) if first["count"] else 0.0
            funnel_lines.append(
                f"  • {funnel['label']}: {first['count']} → {last['count']} ({conversion}%)"
            )
        funnel_text = "\n".join(funnel_lines) or "  • пока нет данных"
        text += (
            "\n👥 Пользователи и активность\n"
            f"• Всего пользователей: {_people(admin_activity['users']['total'])}\n"
            f"• Других пользователей, кроме вас: {_people(admin_activity['users']['other'])}\n"
            f"• Списки создали: {_people(admin_activity['lists']['other_users'])}; "
            f"всего личных списков: {_records(admin_activity['lists']['records'])}\n"
            f"• Доступов к общим спискам: {_records(admin_activity['shared_lists']['records'])}; "
            f"участников: {_people(admin_activity['shared_lists']['other_users'])}\n"
            f"• Напоминания используют: {_people(admin_activity['reminders']['other_users'])}; "
            f"создано: {_records(admin_activity['reminders']['records'])}\n"
            f"• Чек-листы проходили: {_people(admin_activity['checklists']['other_users'])}; "
            f"запусков: {_records(admin_activity['checklists']['records'])}\n"
            f"• Лекарства ведут: {_people(admin_activity['medications']['other_users'])}; "
            f"препаратов: {admin_activity['medications']['records']}\n"
            f"• Авто ведут: {_people(admin_activity['driver']['vehicle_users'])}; "
            f"автомобилей: {admin_activity['driver']['vehicles']}; "
            f"заправок: {admin_activity['driver']['fuel_entries']}; "
            f"расходов: {admin_activity['driver'].get('expenses', 0)}; "
            f"документов: {admin_activity['driver'].get('documents', 0)}\n"
            "\n📈 Поведение в боте\n"
            f"• Событий за последние 24 часа: {activity['events_24h']}\n"
            f"• Событий за последние {activity['period_days']} дней: {activity['events_period']}\n"
            f"• Активных других пользователей за 24 часа: {activity['active_other_users_24h']}\n"
            f"• Активных других пользователей за {activity['period_days']} дней: "
            f"{activity['active_other_users_period']}\n"
            "Самые используемые разделы:\n"
            f"{top_domains}\n"
            "Самые частые действия:\n"
            f"{top_actions}\n"
            "Прохождение сценариев:\n"
            f"{funnel_text}\n"
        )
    
    await query.edit_message_text(
        text,
        reply_markup=get_settings_back_home_keyboard(),
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
        reply_markup=get_settings_back_home_keyboard(),
    )

    return ConversationHandler.END


async def settings_about_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show app version, release links, and current changelog."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)

    info = app_info(settings)
    changes = "\n".join(f"• {item}" for item in info["user_changes"]) or "• Изменений не указано."
    testing_notice = (
        f"\n\n{info['testing_notice_text']}"
        if info["testing_notice_enabled"] and info["testing_notice_text"]
        else ""
    )
    github_line = info["github_url"] or "не настроено"
    changelog_line = info["changelog_url"] or "не настроено"
    text = (
        "ℹ️ О боте\n\n"
        f"Версия: {info['version']}\n"
        f"Канал: {info['release_channel']}\n"
        f"Статус: {'тестирование' if info['testing_notice_enabled'] else 'стабильный режим'}\n"
        f"Последний запуск: {info['started_at_display']} ({info['started_timezone']})\n\n"
        "Проект:\n"
        f"GitHub: {github_line}\n"
        f"История изменений: {changelog_line}\n\n"
        "Что нового:\n"
        f"{changes}"
        f"{testing_notice}"
    )

    await query.edit_message_text(
        text,
        reply_markup=get_about_keyboard(
            info["github_url"],
            info["changelog_url"],
            is_admin=_is_admin_user(user, telegram_id),
        ),
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


async def settings_release_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show recent release history from bundled changelog."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)

    info = app_info(settings)
    entries = info.get("release_history", [])
    if entries:
        blocks = []
        for entry in entries[:5]:
            items = entry.get("items", [])[:5]
            items_text = "\n".join(f"• {item}" for item in items) or "• Изменения не указаны."
            blocks.append(f"{entry.get('version', 'версия')}\n{items_text}")
        history_text = "\n\n".join(blocks)
    else:
        history_text = "История версий пока не найдена в CHANGELOG.md."

    await query.edit_message_text(
        "📜 История версий\n\n"
        f"{history_text}",
        reply_markup=get_about_keyboard(
            info["github_url"],
            info["changelog_url"],
            is_admin=_is_admin_user(user, telegram_id),
        ),
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


async def settings_technical_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show admin-only technical release and runtime status."""
    query = update.callback_query
    await query.answer()

    telegram_id = update.effective_user.id
    db_status = "недоступна"
    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(telegram_id)
        if not _is_admin_user(user, telegram_id):
            await query.edit_message_text(
                "🔒 Технический статус доступен только администратору.",
                reply_markup=get_settings_back_home_keyboard(),
            )
            return ConversationHandler.END
        try:
            await session.execute(text("SELECT 1"))
            db_status = "доступна"
        except Exception:
            logger.exception("Technical status DB check failed")

    info = app_info(settings)
    technical_changes = "\n".join(
        f"• {item}" for item in info.get("technical_changes", [])
    ) or "• Технические изменения для этой версии не указаны."
    api_url = settings.WEB_PUBLIC_URL or settings.APP_BASE_URL or "не настроен"
    text_body = (
        "🔧 Технический статус\n\n"
        f"Bot-процесс: работает\n"
        f"База данных: {db_status}\n"
        f"Версия: {info['version']}\n"
        f"Канал: {info['release_channel']}\n"
        f"Важность релиза: {info['release_importance']}\n"
        f"Запуск bot-процесса: {info['started_at_display']} ({info['started_timezone']})\n"
        f"Worker interval: {settings.WORKER_INTERVAL} сек.\n"
        f"Публичный web/API URL: {api_url}\n\n"
        "Режимы уведомлений:\n"
        f"• пользователям: {info['startup_announce_mode']}\n"
        f"• админам: {info['startup_admin_announce_mode']}\n\n"
        "Технические изменения:\n"
        f"{technical_changes}"
    )

    await query.edit_message_text(
        text_body,
        reply_markup=get_about_keyboard(
            info["github_url"],
            info["changelog_url"],
            is_admin=True,
        ),
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


async def settings_web_login_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Issue a personal key for the standalone web client."""
    query = update.callback_query if update.callback_query else None
    if query:
        await query.answer()

    telegram_user = update.effective_user

    async with async_session_maker() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_or_create(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )
        login_key = await WebAuthService(session).create_login_key(user.id)
        await session.commit()

    expires_at = login_key.expires_at_utc.strftime("%d.%m.%Y %H:%M UTC")
    token_text = escape(login_key.token)
    link_block = (
        f'\n\n<a href="{escape(login_key.url, quote=True)}">Открыть web-версию</a>'
        if login_key.url
        else (
            "\n\nПубличный адрес web-версии еще не настроен. "
            "Откройте web-страницу проекта и вставьте ключ вручную."
        )
    )
    text = (
        "🌐 Web-версия\n\n"
        "Я выпустил персональный ключ для входа в web-приложение. "
        "Он привязан только к вашему Telegram-пользователю.\n\n"
        f"Ключ:\n<code>{token_text}</code>\n\n"
        f"Действует до: {expires_at}"
        f"{link_block}\n\n"
        "Если создать новый ключ, предыдущий ключ перестанет работать."
    )

    if query:
        await query.edit_message_text(
            text,
            reply_markup=get_settings_back_home_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=get_settings_back_home_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True,
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
