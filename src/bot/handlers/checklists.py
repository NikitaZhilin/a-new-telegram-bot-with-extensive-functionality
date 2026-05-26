"""Interactive checklist run handlers."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.keyboards import (
    get_back_home_inline_keyboard,
    get_checklist_finished_keyboard,
    get_checklist_run_keyboard,
)
from src.db.session import async_session_maker
from src.repositories.user_repo import UserRepository
from src.services.checklist_service import ChecklistService
from src.utils.text import truncate

logger = logging.getLogger(__name__)


async def _get_app_user_id(update: Update, session) -> int:
    """Return internal user ID, creating the user for direct callback flows."""
    user_repo = UserRepository(session)
    telegram_user = update.effective_user
    user = await user_repo.get_or_create(
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
        last_name=telegram_user.last_name,
    )
    await session.commit()
    return user.id


def _source_list_id(run) -> int | None:
    """Return source list id if it is still available."""
    return run.source_list_id if getattr(run, "source_list_id", None) else None


async def _render_run(service: ChecklistService, run) -> tuple[str, object]:
    """Build active checklist text and keyboard."""
    checked, total = service.progress(run)
    source_changed = await service.source_changed(run)

    lines = [
        f"▶️ Чек-лист: {truncate(run.title_snapshot, 80)}",
        "",
        f"Готово: {checked}/{total}",
    ]
    if source_changed:
        lines.extend([
            "",
            "⚠️ Исходный список изменился после запуска. Этот чек-лист идет по сохраненной копии.",
        ])

    lines.extend([
        "",
        "Отмечайте пункты, которые уже выполнены:",
        "",
    ])
    for item in run.items:
        status = "✅" if item.checked else "⬜"
        lines.append(f"{status} {truncate(item.text_snapshot, 90)}")

    return "\n".join(lines), get_checklist_run_keyboard(run, _source_list_id(run))


def _stale_text() -> str:
    """Text for stale checklist callbacks."""
    return (
        "❌ Этот чек-лист уже не активен.\n\n"
        "Откройте список и запустите прохождение заново."
    )


async def _show_stale(update: Update) -> None:
    """Show a safe stale-callback message."""
    query = update.callback_query
    await query.edit_message_text(_stale_text(), reply_markup=get_back_home_inline_keyboard())


async def checklist_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start a personal checklist run from an accessible list."""
    query = update.callback_query
    await query.answer()

    list_id = int(query.data.split(":", 1)[1])

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        run = await service.create_run_from_list(list_id, user_id, source_module=None)
        await session.commit()
        if run:
            run = await service.get_run(run.id, user_id)
            text, keyboard = await _render_run(service, run)
        else:
            text = (
                "❌ Не удалось запустить чек-лист.\n\n"
                "Проверьте, что список существует, доступен вам и в нем есть пункты."
            )
            keyboard = get_back_home_inline_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def checklist_start_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start a checklist run from a list item and mark that item in the run."""
    query = update.callback_query
    await query.answer()

    _, list_id_str, item_id_str = query.data.split(":", 2)
    list_id = int(list_id_str)
    item_id = int(item_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        run = await service.create_run_from_list(
            list_id,
            user_id,
            source_module=None,
            initial_source_item_id=item_id,
        )
        await session.commit()
        if run:
            run = await service.get_run(run.id, user_id)
            text, keyboard = await _render_run(service, run)
        else:
            text = (
                "❌ Не удалось запустить чек-лист.\n\n"
                "Проверьте, что список существует, доступен вам и в нем есть пункты."
            )
            keyboard = get_back_home_inline_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def checklist_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle a checklist run item and refresh the same message."""
    query = update.callback_query
    await query.answer()

    _, run_id_str, item_id_str = query.data.split(":", 2)
    run_id = int(run_id_str)
    item_id = int(item_id_str)

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        run = await service.toggle_item(run_id, item_id, user_id)
        await session.commit()
        if run:
            text, keyboard = await _render_run(service, run)
        else:
            text, keyboard = _stale_text(), get_back_home_inline_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def checklist_check_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mark every item checked in an active checklist run."""
    query = update.callback_query
    await query.answer()

    run_id = int(query.data.split(":", 1)[1])

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        run = await service.check_all(run_id, user_id)
        await session.commit()
        if run:
            text, keyboard = await _render_run(service, run)
        else:
            text, keyboard = _stale_text(), get_back_home_inline_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard)
    return ConversationHandler.END


async def checklist_finish_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish a checklist run after all snapshot items are checked."""
    query = update.callback_query

    run_id = int(query.data.split(":", 1)[1])

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        before = await service.get_run(run_id, user_id)
        if before and before.status == "active" and not service.all_checked(before):
            await query.answer("Сначала отметьте все пункты чек-листа", show_alert=True)
            text, keyboard = await _render_run(service, before)
            await query.edit_message_text(text, reply_markup=keyboard)
            return ConversationHandler.END

        await query.answer()
        run = await service.finish_run(run_id, user_id)
        await session.commit()

    if not run:
        await _show_stale(update)
        return ConversationHandler.END

    checked, total = ChecklistService.progress(run)
    text = (
        "✅ Чек-лист завершен.\n\n"
        f"Список: {run.title_snapshot}\n"
        f"Пунктов выполнено: {checked}/{total}\n\n"
        "Исходный список не изменен."
    )
    await query.edit_message_text(
        text,
        reply_markup=get_checklist_finished_keyboard(_source_list_id(run)),
    )
    return ConversationHandler.END


async def checklist_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel an active checklist run."""
    query = update.callback_query
    await query.answer("Чек-лист отменен")

    run_id = int(query.data.split(":", 1)[1])

    async with async_session_maker() as session:
        user_id = await _get_app_user_id(update, session)
        service = ChecklistService(session)
        run = await service.cancel_run(run_id, user_id)
        await session.commit()

    if not run:
        await _show_stale(update)
        return ConversationHandler.END

    text = (
        "❌ Прохождение чек-листа отменено.\n\n"
        f"Список: {run.title_snapshot}\n"
        "Исходный список не изменен."
    )
    await query.edit_message_text(
        text,
        reply_markup=get_checklist_finished_keyboard(_source_list_id(run)),
    )
    return ConversationHandler.END
