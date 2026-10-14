"""Admin-only announcement sender: О боте → 📣 Оповещение.

Flow: preview → «Только мне» (test, not marked as delivered) /
«Выбрать получателей» (checkbox list) / «Всем, кто ещё не получал» →
confirmation → sending → result. Nothing is sent without the confirmation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from src.bot.handlers.feedback import _deny, _is_admin
from src.config import settings
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.announcements import (
    ANNOUNCEMENT_ID,
    announcement_text,
    delivered_telegram_ids,
    send_announcement,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 8
SELECTED_KEY = "broadcast_selected"


def _feedback_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("💬 Обратная связь", callback_data="feedback_start")]])


def _selected(context) -> set[int]:
    selected = context.user_data.get(SELECTED_KEY)
    if not isinstance(selected, set):
        selected = set(selected or [])
        context.user_data[SELECTED_KEY] = selected
    return selected


async def _load_users():
    async with async_session_maker() as session:
        users = list(await UserRepository(session).get_all_with_telegram_id())
        delivered = await delivered_telegram_ids(session)
    return users, delivered


def _user_label(user) -> str:
    name = user.first_name or user.username or str(user.telegram_id)
    if user.username and user.first_name:
        name += f" @{user.username}"
    return name[:40]


async def broadcast_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    users, delivered = await _load_users()
    pending = [user for user in users if user.telegram_id not in delivered]
    selected = _selected(context)
    text = (
        "📣 Оповещение пользователям\n\n"
        f"Всего пользователей: {len(users)} · уже получили: {len(delivered & {u.telegram_id for u in users})} · "
        f"ещё не получали: {len(pending)}\n"
        "Сначала можно отправить себе и посмотреть, как выглядит.\n\n"
        "──── Текст ────\n"
        f"{announcement_text(settings.APP_VERSION)}"
    )
    keyboard = [
        [InlineKeyboardButton("🧪 Отправить только мне", callback_data="bc_confirm:me")],
        [InlineKeyboardButton(f"👥 Выбрать получателей ({len(selected)})", callback_data="bc_pick:0")],
    ]
    if pending:
        keyboard.append([InlineKeyboardButton(f"📣 Всем, кто ещё не получал ({len(pending)})", callback_data="bc_confirm:new")])
    keyboard.append([
        InlineKeyboardButton("⬅️ О боте", callback_data="settings_about"),
        InlineKeyboardButton("🏠 В меню", callback_data="home"),
    ])
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))


async def _show_pick(query, context, page: int) -> None:
    users, delivered = await _load_users()
    selected = _selected(context)
    pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), pages - 1)
    chunk = users[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    keyboard = []
    for user in chunk:
        box = "☑️" if user.telegram_id in selected else "⬜"
        got = " ✅" if user.telegram_id in delivered else ""
        keyboard.append([InlineKeyboardButton(f"{box} {_user_label(user)}{got}", callback_data=f"bc_toggle:{user.telegram_id}:{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"bc_pick:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"bc_pick:{page + 1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([
        InlineKeyboardButton("Отметить не получавших", callback_data=f"bc_select_new:{page}"),
        InlineKeyboardButton("Снять всё", callback_data=f"bc_clear:{page}"),
    ])
    if selected:
        keyboard.append([InlineKeyboardButton(f"📨 Отправить выбранным ({len(selected)})", callback_data="bc_confirm:sel")])
    keyboard.append([InlineKeyboardButton("⬅️ К оповещению", callback_data="settings_broadcast")])
    await query.edit_message_text(
        "👥 Кому отправить?\n\nНажмите на человека, чтобы отметить. ✅ — уже получал это оповещение.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def broadcast_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    await _show_pick(query, context, int(query.data.split(":", 1)[1]))


async def broadcast_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    _, telegram_id, page = query.data.split(":")
    selected = _selected(context)
    selected.symmetric_difference_update({int(telegram_id)})
    await _show_pick(query, context, int(page))


async def broadcast_bulk_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    action, page = query.data.split(":")
    selected = _selected(context)
    if action == "bc_clear":
        selected.clear()
    else:
        users, delivered = await _load_users()
        selected.update(user.telegram_id for user in users if user.telegram_id not in delivered)
    await _show_pick(query, context, int(page))


async def _recipients(mode: str, context, admin_id: int) -> list[tuple[int, int | None]]:
    users, delivered = await _load_users()
    by_tg = {user.telegram_id: user.id for user in users}
    if mode == "me":
        return [(admin_id, by_tg.get(admin_id))]
    if mode == "new":
        return [(user.telegram_id, user.id) for user in users if user.telegram_id not in delivered]
    selected = _selected(context)
    return [(telegram_id, by_tg.get(telegram_id)) for telegram_id in sorted(selected) if telegram_id in by_tg]


async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    mode = query.data.split(":", 1)[1]
    recipients = await _recipients(mode, context, update.effective_user.id)
    if not recipients:
        await query.edit_message_text(
            "Некому отправлять: никто не выбран или все уже получили.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К оповещению", callback_data="settings_broadcast")]]),
        )
        return
    who = "только вам (тест, не считается доставкой)" if mode == "me" else f"{len(recipients)} польз."
    await query.edit_message_text(
        f"Отправить оповещение: {who}?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, отправить", callback_data=f"bc_send:{mode}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="settings_broadcast")],
        ]),
    )


async def broadcast_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not await _is_admin(update.effective_user.id):
        await _deny(query)
        return
    mode = query.data.split(":", 1)[1]
    recipients = await _recipients(mode, context, update.effective_user.id)
    if mode != "me":
        # A second press of the same button must not message people twice.
        async with async_session_maker() as session:
            delivered = await delivered_telegram_ids(session)
        recipients = [item for item in recipients if item[0] not in delivered]
    await query.edit_message_text(f"⏳ Отправляю ({len(recipients)})…")
    result = await send_announcement(
        context.bot,
        recipients,
        async_session_maker,
        text=announcement_text(settings.APP_VERSION),
        reply_markup=_feedback_markup(),
        record=mode != "me",
    )
    if mode == "sel":
        _selected(context).clear()
    logger.info(
        "Announcement %s sent by admin: mode=%s sent=%s blocked=%s failed=%s",
        ANNOUNCEMENT_ID, mode, result.sent, result.blocked, result.failed,
    )
    lines = [
        "📣 Готово",
        "",
        f"Доставлено: {result.sent}",
        f"Остановили бота: {result.blocked}",
        f"Не удалось: {result.failed}" + (f" (ID: {', '.join(map(str, result.failed_ids[:10]))})" if result.failed_ids else ""),
        f"Время: {datetime.now(timezone.utc).strftime('%H:%M')} UTC",
    ]
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К оповещению", callback_data="settings_broadcast")]]),
    )


def broadcast_callback_handlers() -> list[CallbackQueryHandler]:
    return [
        CallbackQueryHandler(broadcast_menu_callback, pattern="^settings_broadcast$"),
        CallbackQueryHandler(broadcast_pick_callback, pattern=r"^bc_pick:\d+$"),
        CallbackQueryHandler(broadcast_toggle_callback, pattern=r"^bc_toggle:\d+:\d+$"),
        CallbackQueryHandler(broadcast_bulk_select_callback, pattern=r"^bc_(select_new|clear):\d+$"),
        CallbackQueryHandler(broadcast_confirm_callback, pattern=r"^bc_confirm:(me|new|sel)$"),
        CallbackQueryHandler(broadcast_send_callback, pattern=r"^bc_send:(me|new|sel)$"),
    ]
