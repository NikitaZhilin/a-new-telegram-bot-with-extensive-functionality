"""Tests for bot callback registration."""

import re
from types import SimpleNamespace

import pytest
from telegram.ext import ConversationHandler

from src.bot.app import create_application
from src.bot.handlers import medications as medication_handlers
from src.bot.keyboards import (
    get_driver_fuel_delete_confirm_keyboard,
    get_driver_fuel_entry_keyboard,
    get_driver_fuel_history_keyboard,
    get_driver_menu_keyboard,
    get_driver_section_keyboard,
    get_driver_service_keyboard,
    get_driver_step_keyboard,
    get_driver_templates_keyboard,
    get_driver_vehicle_delete_confirm_keyboard,
    get_driver_vehicles_keyboard,
    get_driver_vehicle_view_keyboard,
    get_driver_fuel_keyboard,
    get_driver_full_tank_keyboard,
    get_main_menu_inline_keyboard,
    get_main_menu_keyboard,
    get_medication_delete_confirm_keyboard,
    get_medication_dosage_keyboard,
    get_medication_edit_dosage_keyboard,
    get_medication_edit_importance_keyboard,
    get_medication_edit_instructions_keyboard,
    get_medication_edit_keyboard,
    get_medication_edit_text_keyboard,
    get_medication_importance_keyboard,
    get_medication_instructions_keyboard,
    get_medication_reminder_keyboard,
    get_medication_view_keyboard,
    get_reminder_edit_repeat_keyboard,
    get_reminder_view_keyboard,
)
from src.db.models import User


def _collect_callback_patterns(handler) -> set[str]:
    """Collect regex patterns from handlers, including ConversationHandler internals."""
    patterns = set()

    pattern = getattr(handler, "pattern", None)
    if pattern is not None:
        patterns.add(pattern.pattern)

    if isinstance(handler, ConversationHandler):
        for nested in handler.entry_points:
            patterns.update(_collect_callback_patterns(nested))
        for state_handlers in handler.states.values():
            for nested in state_handlers:
                patterns.update(_collect_callback_patterns(nested))
        for nested in handler.fallbacks:
            patterns.update(_collect_callback_patterns(nested))

    return patterns


def _collect_application_callback_patterns() -> set[str]:
    app = create_application()
    patterns = set()
    for handlers in app.handlers.values():
        for handler in handlers:
            patterns.update(_collect_callback_patterns(handler))
    return patterns


def _collect_callback_data(markup) -> set[str]:
    payload = markup.to_dict()
    return {
        button["callback_data"]
        for row in payload["inline_keyboard"]
        for button in row
        if "callback_data" in button
    }


def _is_registered(callback_data: str, patterns: set[str]) -> bool:
    return any(re.match(pattern, callback_data) for pattern in patterns)


def test_important_callback_patterns_are_registered():
    """Buttons for implemented flows should have registered handlers."""
    patterns = _collect_application_callback_patterns()

    expected = {
        "^(notes_|note_)",
        "^share_bot$",
        "^lists_page:",
        "^list_item_edit:",
        "^list_members:",
        "^list_member:",
        "^list_member_role:",
        "^list_member_remove:",
        "^list_remind:",
        "^med_create$",
        "^med_dosage:",
        "^med_instr:",
        "^med_importance:",
        "^med_rem_custom:",
        "^medications_list$",
        "^med_view:",
        "^med_edit:",
        "^med_edit_name:",
        "^med_edit_dosage:",
        "^med_edit_dosage_value:",
        "^med_edit_instr:",
        "^med_edit_instr_value:",
        "^med_edit_importance:",
        "^med_edit_importance_value:",
        "^med_taken:",
        "^med_skip:",
        "^med_snooze:",
        "^med_remind:",
        "^med_rem_freq:",
        "^med_rem_time:",
        "^med_rem_skip:",
        "^list_delete_confirm:",
        "^list_item_delete_confirm:",
        "^reminders_page:",
        "^reminder_edit_text:",
        "^reminder_edit_time:",
        "^reminder_edit_repeat:",
        "^reminder_edit_repeat_value:",
        "^rem_date_after_tomorrow$",
        "^rem_date_next_week$",
        "^rem_time_back$",
        "^rem_time_custom$",
        "^rem_confirm_back$",
        "^settings_timezone$",
        "^settings_subscription$",
        "^settings_web_login$",
        "^tz_custom$",
        "^driver_menu$",
        "^driver_section:",
        "^driver_list_template:",
        "^driver_reminder_template:",
        "^driver_vehicle_create$",
        "^driver_vehicle_edit:",
        "^driver_vehicle_view:",
        "^driver_vehicle_delete:",
        "^driver_vehicle_delete_confirm:",
        "^driver_vehicle_mileage:",
        "^driver_fuel_add:",
        "^driver_fuel_edit:",
        "^driver_fuel_full:",
        "^driver_fuel_history:",
        "^driver_fuel_view:",
        "^driver_fuel_delete:",
        "^driver_fuel_delete_confirm:",
        "^driver_service_view:",
        "^driver_service_done:",
    }

    assert expected <= patterns


def test_medication_keyboards_have_registered_callbacks():
    """Medication buttons should not point to dead callback_data."""
    patterns = _collect_application_callback_patterns()
    callbacks = set()

    for keyboard in [
        get_medication_dosage_keyboard(),
        get_medication_instructions_keyboard(),
        get_medication_importance_keyboard(),
        get_medication_reminder_keyboard(10),
        get_medication_view_keyboard(10),
        get_medication_edit_keyboard(10),
        get_medication_edit_text_keyboard(10),
        get_medication_edit_dosage_keyboard(10),
        get_medication_edit_instructions_keyboard(10),
        get_medication_edit_importance_keyboard(10),
        get_medication_delete_confirm_keyboard(10),
        get_reminder_view_keyboard(10),
        get_reminder_edit_repeat_keyboard(10),
    ]:
        callbacks.update(_collect_callback_data(keyboard))

    unregistered = {
        callback_data
        for callback_data in callbacks
        if not _is_registered(callback_data, patterns)
    }

    assert unregistered == set()


@pytest.mark.asyncio
async def test_medication_user_lookup_creates_user_before_domain_writes(db_session):
    """Medication flows must not use Telegram ID as an internal FK fallback."""
    update = SimpleNamespace(
        effective_user=SimpleNamespace(
            id=372690348,
            username="tester",
            first_name="Test",
            last_name=None,
        )
    )

    internal_id = await medication_handlers._get_app_user_id(update, db_session)
    user = await db_session.get(User, internal_id)

    assert user is not None
    assert user.telegram_id == 372690348
    assert internal_id != 372690348


def test_main_menus_expose_active_sections_only():
    """Main menus should not regress to stale incubation/feed buttons."""
    reply_markup = get_main_menu_keyboard().to_dict()
    reply_texts = {
        button["text"]
        for row in reply_markup["keyboard"]
        for button in row
    }

    assert reply_texts == {
        "📋 Списки",
        "💊 Лекарства",
        "⏰ Напоминания",
        "🚗 Для водителя",
        "⚙️ Настройки",
        "🌐 Web-версия",
        "👥 Поделиться ботом",
        "❓ Помощь",
    }

    inline_markup = get_main_menu_inline_keyboard().to_dict()
    inline_texts = {
        button["text"]
        for row in inline_markup["inline_keyboard"]
        for button in row
    }

    assert inline_texts == {
        "📋 Списки",
        "💊 Лекарства",
        "⏰ Напоминания",
        "🚗 Для водителя",
        "⚙️ Настройки",
        "🌐 Web-версия",
        "👥 Поделиться ботом",
    }


def test_driver_keyboards_have_registered_callbacks():
    """Driver menu buttons should route to registered handlers or existing flows."""
    patterns = _collect_application_callback_patterns()
    callbacks = set()

    for keyboard in [
        get_driver_menu_keyboard(),
        get_driver_section_keyboard(),
        get_driver_templates_keyboard(),
        get_driver_vehicles_keyboard([]),
        get_driver_vehicle_view_keyboard(10),
        get_driver_vehicle_delete_confirm_keyboard(10),
        get_driver_fuel_keyboard([]),
        get_driver_fuel_history_keyboard(10, []),
        get_driver_fuel_entry_keyboard(10, 20),
        get_driver_fuel_delete_confirm_keyboard(10, 20),
        get_driver_service_keyboard(10),
        get_driver_step_keyboard(can_skip=True),
        get_driver_full_tank_keyboard(),
    ]:
        callbacks.update(_collect_callback_data(keyboard))

    unregistered = {
        callback_data
        for callback_data in callbacks
        if not _is_registered(callback_data, patterns)
    }

    assert unregistered == set()
