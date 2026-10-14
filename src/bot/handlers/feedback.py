"""Feedback from users and admin-only screens: error journal and inbox.

Users: Настройки → «💬 Обратная связь» (or /feedback) → kind → one message
(text or a screenshot with a caption). The message is stored and sent to the
admins (ADMIN_TELEGRAM_IDS) only, with «Ответить» / «Прочитано» buttons.

Admins: Настройки → О боте → «🧯 Журнал ошибок» and «📬 Обращения».
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.handlers.conversation_exit import (
    TEXT_INPUT,
    WIZARD_TIMEOUT_SECONDS,
    exit_fallbacks,
    leave_wizard_fallbacks,
)
from src.config import settings
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.error_journal import SECTION_LABELS, SERVICE_LABELS, ErrorJournalService
from src.services.feedback_service import (
    KIND_LABELS,
    STATUS_LABELS,
    FeedbackLimitError,
    FeedbackService,
)
from src.utils.timezones import safe_zoneinfo

logger = logging.getLogger(__name__)

WAIT_KIND = "FEEDBACK_WAIT_KIND"
WAIT_TEXT = "FEEDBACK_WAIT_TEXT"
WAIT_REPLY = "FEEDBACK_WAIT_REPLY"

MESSAGE_LIMIT = 3900

KIND_PROMPTS = {
    "bug": (
        "🐞 Опишите, что случилось: в каком разделе, что вы нажимали и что ожидали увидеть.\n\n"
        "Можно приложить скриншот — отправьте фото с подписью."
    ),
    "idea": "💡 Опишите идею или доработку одним сообщением.",
    "other": "✉️ Напишите сообщение одним сообщением.",
}


def _cut(text: str, limit: int = MESSAGE_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_time(value: Optional[datetime], tz_name: Optional[str]) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(safe_zoneinfo(tz_name, settings.TIMEZONE_DEFAULT)).strftime("%d.%m %H:%M")


async def _is_admin(telegram_id: int) -> bool:
    if telegram_id in settings.admin_telegram_id_set:
        return True
    async with async_session_maker() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        return bool(user and user.is_admin)


async def _admin_timezone(telegram_id: int) -> Optional[str]:
    async with async_session_maker() as session:
        user = await UserRepository(session).get_by_telegram_id(telegram_id)
        return user.timezone if user else None


# =============================================================================
# Users: send feedback
# =============================================================================

def feedback_kind_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(KIND_LABELS["bug"], callback_data="fb_kind:bug")],
            [InlineKeyboardButton(KIND_LABELS["idea"], callback_data="fb_kind:idea")],
            [InlineKeyboardButton(KIND_LABELS["other"], callback_data="fb_kind:other")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
    )


FEEDBACK_INTRO = (
    "💬 Обратная связь\n\n"
    "Нашли ошибку или не хватает функции? Напишите — сообщение получит разработчик.\n\n"
    "Что хотите передать?"
)


async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    context.user_data.pop("feedback_kind", None)
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.edit_message_text(FEEDBACK_INTRO, reply_markup=feedback_kind_keyboard())
        except Exception:
            await query.message.reply_text(FEEDBACK_INTRO, reply_markup=feedback_kind_keyboard())
    else:
        await update.message.reply_text(FEEDBACK_INTRO, reply_markup=feedback_kind_keyboard())
    return WAIT_KIND


async def feedback_kind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    kind = query.data.split(":", 1)[1]
    if kind not in KIND_LABELS:
        kind = "other"
    context.user_data["feedback_kind"] = kind
    await query.edit_message_text(
        KIND_PROMPTS[kind],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]),
    )
    return WAIT_TEXT


def _admin_feedback_keyboard(feedback_id: int, status: str = "new") -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton("↩️ Ответить", callback_data=f"fb_reply:{feedback_id}")]
    if status == "new":
        row.append(InlineKeyboardButton("✅ Прочитано", callback_data=f"fb_read:{feedback_id}"))
    return InlineKeyboardMarkup([row])


def format_feedback_for_admin(item, recent_errors=(), tz_name: Optional[str] = None) -> str:
    who = item.first_name or "без имени"
    if item.username:
        who += f" (@{item.username})"
    lines = [
        f"💬 Обращение №{item.id} · {KIND_LABELS.get(item.kind, item.kind)}",
        f"От: {who} · ID {item.telegram_id}",
        f"Когда: {_fmt_time(item.created_at, tz_name)} · версия {item.app_version or '—'}",
        f"Статус: {STATUS_LABELS.get(item.status, item.status)}",
        "",
        item.text or "(без текста, только скриншот)",
    ]
    if item.admin_reply:
        lines += ["", f"↩️ Ваш ответ: {item.admin_reply}"]
    if recent_errors:
        lines += ["", "Ошибки этого пользователя за сутки:"]
        for event in recent_errors:
            lines.append(
                f"• №{event.id} {SECTION_LABELS.get(event.section, event.section)} — "
                f"{event.error_type} ({event.count}×)"
            )
    return _cut("\n".join(lines))


async def _notify_admins(context: ContextTypes.DEFAULT_TYPE, item, recent_errors) -> None:
    for admin_id in settings.admin_telegram_id_set:
        try:
            if item.photo_file_id:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=item.photo_file_id,
                    caption=f"📎 Скриншот к обращению №{item.id}",
                )
            await context.bot.send_message(
                chat_id=admin_id,
                text=format_feedback_for_admin(item, recent_errors),
                reply_markup=_admin_feedback_keyboard(item.id),
            )
        except Exception:
            logger.warning("Could not deliver feedback to admin", exc_info=True)


async def feedback_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = (message.text or message.caption or "").strip()
    photo_id = message.photo[-1].file_id if message.photo else None
    if not text and not photo_id:
        await message.reply_text("Напишите сообщение текстом или пришлите скриншот с подписью.")
        return WAIT_TEXT

    kind = context.user_data.pop("feedback_kind", "other")
    tg_user = update.effective_user
    try:
        async with async_session_maker() as session:
            user = await UserRepository(session).get_or_create(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            service = FeedbackService(session)
            item = await service.create(
                telegram_id=tg_user.id,
                user_id=user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                kind=kind,
                text=text,
                photo_file_id=photo_id,
                app_version=settings.APP_VERSION,
            )
            recent_errors = await service.recent_errors_for(tg_user.id) if kind == "bug" else []
            await session.commit()
    except FeedbackLimitError:
        await message.reply_text(
            "⏳ Вы уже отправили много сообщений за последний час. Попробуйте чуть позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="home")]]),
        )
        return ConversationHandler.END

    await message.reply_text(
        f"✅ Спасибо! Обращение №{item.id} передано разработчику.\n"
        "Если понадобится уточнение, ответ придёт сюда, в этот чат.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="home")]]),
    )
    await _notify_admins(context, item, recent_errors)
    return ConversationHandler.END


async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("feedback_kind", None)
    context.user_data.pop("feedback_reply_id", None)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В меню", callback_data="home")]])
    if update.callback_query:
        await update.callback_query.answer("Отменено")
        await update.callback_query.edit_message_text("❌ Отменено", reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text("❌ Отменено", reply_markup=keyboard)
    return ConversationHandler.END


# =============================================================================
# Admins: answer feedback
# =============================================================================

async def feedback_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _is_admin(update.effective_user.id):
        await query.answer("Только для администратора", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    feedback_id = int(query.data.split(":", 1)[1])
    context.user_data["feedback_reply_id"] = feedback_id
    await query.message.reply_text(
        f"↩️ Напишите ответ на обращение №{feedback_id}. Пользователь получит его от бота.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="cancel")]]),
    )
    return WAIT_REPLY


async def feedback_reply_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    feedback_id = context.user_data.pop("feedback_reply_id", None)
    reply = (update.message.text or "").strip()
    if feedback_id is None or not reply:
        await update.message.reply_text("Ответ не отправлен.")
        return ConversationHandler.END
    async with async_session_maker() as session:
        service = FeedbackService(session)
        item = await service.get(feedback_id)
        if item is None:
            await update.message.reply_text("Обращение не найдено.")
            return ConversationHandler.END
        target = item.telegram_id
    try:
        await context.bot.send_message(
            chat_id=target,
            text=_cut(f"💬 Ответ разработчика на ваше обращение №{feedback_id}:\n\n{reply}"),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("💬 Написать ещё", callback_data="feedback_start")]]
            ),
        )
    except Exception as exc:
        await update.message.reply_text(
            f"⚠️ Не удалось доставить ответ: {type(exc).__name__}. Возможно, пользователь остановил бота."
        )
        return ConversationHandler.END
    async with async_session_maker() as session:
        await FeedbackService(session).save_reply(feedback_id, reply)
        await session.commit()
    await update.message.reply_text(f"✅ Ответ на обращение №{feedback_id} отправлен.")
    return ConversationHandler.END


async def feedback_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await _is_admin(update.effective_user.id):
        await query.answer("Только для администратора", show_alert=True)
        return
    feedback_id = int(query.data.split(":", 1)[1])
    async with async_session_maker() as session:
        item = await FeedbackService(session).get(feedback_id)
        if item is not None and item.status == "new":
            item.status = "read"
        await session.commit()
    await query.answer("Отмечено как прочитанное")
    try:
        await query.edit_message_reply_markup(reply_markup=_admin_feedback_keyboard(feedback_id, "read"))
    except Exception:
        pass


feedback_conv = ConversationHandler(
    conversation_timeout=WIZARD_TIMEOUT_SECONDS,
    allow_reentry=True,
    entry_points=[
        CommandHandler("feedback", feedback_start),
        CallbackQueryHandler(feedback_start, pattern="^feedback_start$"),
        CallbackQueryHandler(feedback_reply_start, pattern=r"^fb_reply:\d+$"),
    ],
    states={
        WAIT_KIND: [CallbackQueryHandler(feedback_kind_callback, pattern="^fb_kind:")],
        WAIT_TEXT: [MessageHandler(TEXT_INPUT | filters.PHOTO, feedback_receive)],
        WAIT_REPLY: [MessageHandler(TEXT_INPUT, feedback_reply_receive)],
    },
    fallbacks=[
        *exit_fallbacks(),
        CommandHandler("cancel", feedback_cancel),
        CallbackQueryHandler(feedback_cancel, pattern="^cancel$"),
        *leave_wizard_fallbacks(),
    ],
)


# =============================================================================
# Admins: error journal and inbox screens
# =============================================================================

def _admin_back_row() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton("⬅️ О боте", callback_data="settings_about"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ]


async def _deny(query) -> None:
    await query.edit_message_text(
        "🔒 Раздел доступен только администратору.",
        reply_markup=InlineKeyboardMarkup([_admin_back_row()]),
    )


async def admin_errors_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    tz_name = await _admin_timezone(update.effective_user.id)
    async with async_session_maker() as session:
        service = ErrorJournalService(session)
        summary = await service.summary()
        events = await service.list_events(days=30, limit=10)

    lines = [
        "🧯 Журнал ошибок",
        "",
        f"Открытых видов ошибок: {summary['open_kinds']} · новых или повторившихся за 24 ч: {summary['kinds_seen_24h']}",
    ]
    if summary["by_section"]:
        lines.append("По разделам: " + ", ".join(
            f"{item['label']} {item['occurrences']}" for item in summary["by_section"][:6]
        ))
    lines.append("")
    if not events:
        lines.append("Открытых ошибок нет 🎉")
    for event in events:
        lines.append(
            f"№{event.id} · {SECTION_LABELS.get(event.section, event.section)} · "
            f"{event.count}× · {_fmt_time(event.last_seen_at, tz_name)}\n"
            f"   {event.error_type}: {(event.message or '')[:120]}"
        )
    keyboard: list[list[InlineKeyboardButton]] = []
    buttons = [InlineKeyboardButton(f"№{event.id}", callback_data=f"settings_error:{event.id}") for event in events]
    for start in range(0, len(buttons), 5):
        keyboard.append(buttons[start:start + 5])
    if events:
        keyboard.append([InlineKeyboardButton("✅ Отметить все решёнными", callback_data="settings_errors_resolve_all")])
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="settings_errors")])
    keyboard.append(_admin_back_row())
    await query.edit_message_text(_cut("\n".join(lines)), reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_error_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    event_id = int(query.data.split(":", 1)[1])
    tz_name = await _admin_timezone(update.effective_user.id)
    async with async_session_maker() as session:
        event = await ErrorJournalService(session).get(event_id)
    if event is None:
        await query.edit_message_text(
            "Запись не найдена (возможно, удалена как старая).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Журнал", callback_data="settings_errors")]]),
        )
        return
    head = [
        f"🧯 Ошибка №{event.id}" + (" · решена" if event.resolved_at else ""),
        f"Раздел: {SECTION_LABELS.get(event.section, event.section)} · процесс: {SERVICE_LABELS.get(event.service, event.service)}",
        f"Повторов: {event.count} · первая {_fmt_time(event.first_seen_at, tz_name)} · последняя {_fmt_time(event.last_seen_at, tz_name)}",
        f"Где: {event.location or '—'}",
    ]
    if event.context:
        head.append(f"Что делали: {event.context}")
    if event.telegram_id:
        head.append(f"Пользователь: ID {event.telegram_id}")
    head += ["", f"{event.error_type}: {event.message}"]
    body = "\n".join(head)
    if event.traceback:
        room = MESSAGE_LIMIT - len(body) - 10
        if room > 200:
            body += "\n\n" + event.traceback[-room:]
    keyboard = []
    if not event.resolved_at:
        keyboard.append([InlineKeyboardButton("✅ Решено", callback_data=f"settings_error_resolve:{event.id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Журнал", callback_data="settings_errors")])
    await query.edit_message_text(_cut(body), reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_error_resolve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await _is_admin(update.effective_user.id):
        await query.answer()
        await _deny(query)
        return
    event_id = int(query.data.split(":", 1)[1])
    async with async_session_maker() as session:
        await ErrorJournalService(session).resolve(event_id)
        await session.commit()
    await admin_errors_callback(update, context)


async def admin_errors_resolve_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await _is_admin(update.effective_user.id):
        await query.answer()
        await _deny(query)
        return
    async with async_session_maker() as session:
        await ErrorJournalService(session).resolve_all()
        await session.commit()
    await admin_errors_callback(update, context)


async def admin_feedback_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    tz_name = await _admin_timezone(update.effective_user.id)
    async with async_session_maker() as session:
        service = FeedbackService(session)
        items = await service.list(limit=10)
        new_count = await service.count_new()
    lines = ["📬 Обращения пользователей", "", f"Новых: {new_count}", ""]
    if not items:
        lines.append("Пока никто ничего не писал.")
    for item in items:
        mark = "🆕 " if item.status == "new" else ""
        lines.append(
            f"{mark}№{item.id} · {KIND_LABELS.get(item.kind, item.kind)} · {_fmt_time(item.created_at, tz_name)} · "
            f"{item.first_name or item.telegram_id}\n   {(item.text or '(скриншот)')[:100]}"
        )
    keyboard: list[list[InlineKeyboardButton]] = []
    buttons = [InlineKeyboardButton(f"№{item.id}", callback_data=f"settings_feedback:{item.id}") for item in items]
    for start in range(0, len(buttons), 5):
        keyboard.append(buttons[start:start + 5])
    keyboard.append(_admin_back_row())
    await query.edit_message_text(_cut("\n".join(lines)), reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_feedback_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    feedback_id = int(query.data.split(":", 1)[1])
    tz_name = await _admin_timezone(update.effective_user.id)
    async with async_session_maker() as session:
        service = FeedbackService(session)
        item = await service.get(feedback_id)
        if item is None:
            await query.edit_message_text(
                "Обращение не найдено.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Обращения", callback_data="settings_feedback_list")]]),
            )
            return
        recent_errors = await service.recent_errors_for(item.telegram_id, hours=24 * 7)
        if item.status == "new":
            item.status = "read"
        await session.commit()
    keyboard = _admin_feedback_keyboard(item.id, item.status).inline_keyboard
    rows = [list(row) for row in keyboard]
    rows.append([InlineKeyboardButton("⬅️ Обращения", callback_data="settings_feedback_list")])
    text = format_feedback_for_admin(item, recent_errors, tz_name)
    if item.photo_file_id:
        text += "\n\n📎 К обращению приложен скриншот (пришёл вам отдельным сообщением)."
    await query.edit_message_text(_cut(text), reply_markup=InlineKeyboardMarkup(rows))


def admin_callback_handlers() -> list[CallbackQueryHandler]:
    return [
        CallbackQueryHandler(admin_errors_callback, pattern="^settings_errors$"),
        CallbackQueryHandler(admin_errors_resolve_all_callback, pattern="^settings_errors_resolve_all$"),
        CallbackQueryHandler(admin_error_view_callback, pattern=r"^settings_error:\d+$"),
        CallbackQueryHandler(admin_error_resolve_callback, pattern=r"^settings_error_resolve:\d+$"),
        CallbackQueryHandler(admin_feedback_list_callback, pattern="^settings_feedback_list$"),
        CallbackQueryHandler(admin_feedback_view_callback, pattern=r"^settings_feedback:\d+$"),
        CallbackQueryHandler(feedback_read_callback, pattern=r"^fb_read:\d+$"),
    ]
