"""Settings → 🌅 План на день: morning message with today's reminders and medications."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.config import settings
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.digest_service import DIGEST_HOUR, build_daily_plan
from src.utils.timezones import safe_timezone_name


async def _user(update: Update, session):
    tg = update.effective_user
    return await UserRepository(session).get_or_create(
        telegram_id=tg.id, username=tg.username, first_name=tg.first_name, last_name=tg.last_name
    )


def _screen(enabled: bool) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "🌅 План на день\n\n"
        f"Каждое утро в {DIGEST_HOUR:02d}:00 (по вашему времени) бот присылает одно сообщение: "
        "напоминания на сегодня и время приёма лекарств. Если на день ничего нет, сообщения не будет.\n\n"
        + ("Сейчас: ✅ включено" if enabled else "Сейчас: выключено")
    )
    toggle = (
        InlineKeyboardButton("🔕 Выключить", callback_data="digest_off")
        if enabled else InlineKeyboardButton("🔔 Включить", callback_data="digest_on")
    )
    keyboard = InlineKeyboardMarkup([
        [toggle],
        [InlineKeyboardButton("👀 Показать план на сегодня", callback_data="digest_preview")],
        [
            InlineKeyboardButton("⬅️ Настройки", callback_data="settings_menu"),
            InlineKeyboardButton("🏠 В меню", callback_data="home"),
        ],
    ])
    return text, keyboard


async def digest_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    async with async_session_maker() as session:
        user = await _user(update, session)
        await session.commit()
        enabled = bool(user.daily_digest)
    text, keyboard = _screen(enabled)
    await query.edit_message_text(text, reply_markup=keyboard)


async def digest_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Works both on the settings screen and under a morning message."""
    query = update.callback_query
    enable = query.data == "digest_on"
    async with async_session_maker() as session:
        user = await _user(update, session)
        user.daily_digest = enable
        await session.commit()
    await query.answer("План на день включён" if enable else "План на день выключен")
    message_text = getattr(query.message, "text", "") or ""
    if message_text.startswith("🌅 План на сегодня"):
        try:
            await query.edit_message_reply_markup(
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔔 Включить снова", callback_data="digest_on")
                    if not enable else InlineKeyboardButton("🔕 Не присылать план", callback_data="digest_off")
                ]])
            )
        except Exception:
            pass
        return
    text, keyboard = _screen(enable)
    await query.edit_message_text(text, reply_markup=keyboard)


async def digest_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    async with async_session_maker() as session:
        user = await _user(update, session)
        await session.commit()
        tz_name = safe_timezone_name(user.timezone, settings.TIMEZONE_DEFAULT)
        text = await build_daily_plan(session, user, tz_name)
        enabled = bool(user.daily_digest)
    _, keyboard = _screen(enabled)
    await query.edit_message_text(text or "🌅 На сегодня ни напоминаний, ни приёмов лекарств нет.", reply_markup=keyboard)


def digest_handlers() -> list[CallbackQueryHandler]:
    return [
        CallbackQueryHandler(digest_settings_callback, pattern="^settings_digest$"),
        CallbackQueryHandler(digest_toggle_callback, pattern="^digest_(on|off)$"),
        CallbackQueryHandler(digest_preview_callback, pattern="^digest_preview$"),
    ]
