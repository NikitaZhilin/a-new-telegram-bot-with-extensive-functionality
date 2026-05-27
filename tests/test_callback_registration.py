"""Tests for bot callback registration."""

import re
from types import SimpleNamespace

import pytest
from telegram.ext import ConversationHandler

from src.bot.app import create_application
from src.bot.handlers import medications as medication_handlers
from src.bot.keyboards import (
    get_driver_document_delete_confirm_keyboard,
    get_driver_document_remind_keyboard,
    get_driver_document_type_keyboard,
    get_driver_document_view_keyboard,
    get_driver_documents_keyboard,
    get_driver_expense_category_keyboard,
    get_driver_expense_delete_confirm_keyboard,
    get_driver_expense_view_keyboard,
    get_driver_expenses_keyboard,
    get_driver_fuel_delete_confirm_keyboard,
    get_driver_fuel_entry_keyboard,
    get_driver_fuel_history_keyboard,
    get_driver_created_list_keyboard,
    get_driver_journal_delete_confirm_keyboard,
    get_driver_journal_entry_keyboard,
    get_driver_journal_keyboard,
    get_driver_journal_type_keyboard,
    get_driver_menu_keyboard,
    get_driver_reminder_repeat_keyboard,
    get_driver_section_keyboard,
    get_driver_service_keyboard,
    get_driver_step_keyboard,
    get_driver_templates_keyboard,
    get_driver_vehicle_delete_confirm_keyboard,
    get_driver_vehicle_preset_confirm_keyboard,
    get_driver_vehicle_preset_keyboard,
    get_driver_vehicles_keyboard,
    get_driver_vehicle_view_keyboard,
    get_driver_fuel_keyboard,
    get_driver_full_tank_keyboard,
    get_main_menu_inline_keyboard,
    get_main_menu_keyboard,
    get_list_delete_confirm_keyboard,
    get_list_item_delete_confirm_keyboard,
    get_list_item_keyboard,
    get_list_member_manage_keyboard,
    get_list_members_keyboard,
    get_list_share_keyboard,
    get_list_view_keyboard,
    get_voice_list_preview_keyboard,
    get_lists_list_keyboard,
    get_checklist_finished_keyboard,
    get_checklist_run_keyboard,
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
    get_reminder_edit_keyboard,
    get_reminder_edit_repeat_keyboard,
    get_reminder_view_keyboard,
    get_settings_keyboard,
    get_settings_back_home_keyboard,
    get_about_keyboard,
)
from src.db.models import User
from src.services.vehicle_presets import list_vehicle_presets


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
        "^list_manage_items:",
        "^list_remind:",
        "^list_voice_(new|add:)",
        "^list_voice_confirm$",
        "^list_voice_edit_text$",
        "^list_voice_cancel$",
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
        "^checklist_start_item:",
        "^checklist_start:",
        "^checklist_toggle:",
        "^checklist_check_all:",
        "^checklist_finish:",
        "^checklist_cancel:",
        "^reminders_page:",
        "^reminder_edit_menu:",
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
        "^settings_about$",
        "^settings_release_history$",
        "^settings_technical_status$",
        "^settings_subscription$",
        "^settings_web_login$",
        "^tz_custom$",
        "^driver_menu$",
        "^driver_section:",
        "^driver_list_view:",
        "^driver_list_template:",
        "^driver_reminder_template:",
        "^driver_rem_repeat:",
        "^driver_vehicle_create$",
        "^driver_vehicle_manual$",
        "^driver_vehicle_preset:",
        "^driver_vehicle_preset_confirm$",
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
        "^driver_expense_add$",
        "^driver_expense_edit:",
        "^driver_expense_view:",
        "^driver_expense_delete:",
        "^driver_expense_delete_confirm:",
        "^driver_expense_category:",
        "^driver_expense_vehicle:",
        "^driver_document_add$",
        "^driver_document_edit:",
        "^driver_document_view:",
        "^driver_document_delete:",
        "^driver_document_delete_confirm:",
        "^driver_document_type:",
        "^driver_document_vehicle:",
        "^driver_document_remind:",
        "^driver_service_view:",
        "^driver_service_done:",
        "^driver_journal_filter:",
        "^driver_journal_vehicle_filter:",
        "^driver_journal_vehicle_value:",
        "^driver_journal_quick:",
        "^driver_journal_quick_vehicle:",
        "^driver_journal_view:",
        "^driver_journal_delete:",
        "^driver_journal_delete_confirm:",
        "^driver_journal_edit:",
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
        get_reminder_edit_keyboard(10),
        get_reminder_edit_repeat_keyboard(10),
    ]:
        callbacks.update(_collect_callback_data(keyboard))

    unregistered = {
        callback_data
        for callback_data in callbacks
        if not _is_registered(callback_data, patterns)
    }

    assert unregistered == set()


def test_driver_section_keyboard_does_not_start_general_flows():
    """Driver sections must not create general lists or reminders."""
    for section in ["maintenance", "fluids", "parts", "wash", "tires"]:
        callbacks = _collect_callback_data(get_driver_section_keyboard(section))
        assert "list_create" not in callbacks
        assert "reminder_create" not in callbacks

    run_item = SimpleNamespace(id=40, text_snapshot="Driver item", checked=False)
    run = SimpleNamespace(id=50, items=[run_item])
    callbacks = _collect_callback_data(get_checklist_run_keyboard(run, 10, source_module="driver"))
    callbacks |= _collect_callback_data(get_checklist_finished_keyboard(10, source_module="driver"))
    assert "driver_menu" in callbacks
    assert "driver_list_view:10" not in callbacks
    assert "list_view:10" not in callbacks


def test_list_keyboards_have_registered_callbacks():
    """List buttons should not point to dead callback_data."""
    patterns = _collect_application_callback_patterns()
    callbacks = set()
    item = SimpleNamespace(id=20, text="Пункт списка", is_completed=False)
    list_obj = SimpleNamespace(id=10, title="Дела", items=[item], _access_role="owner")
    run_item = SimpleNamespace(id=40, text_snapshot="Пункт чек-листа", checked=False)
    run = SimpleNamespace(id=50, items=[run_item])
    members = [
        {"member_id": None, "role": "owner", "display_name": "Владелец"},
        {"member_id": 30, "role": "viewer", "display_name": "Участник"},
    ]

    for keyboard in [
        get_lists_list_keyboard([list_obj], page=1, has_next=True),
        get_list_view_keyboard(10, [item]),
        get_list_share_keyboard(10),
        get_list_members_keyboard(10, members),
        get_list_member_manage_keyboard(10, 30, "viewer"),
        get_list_item_keyboard(10, 20),
        get_list_delete_confirm_keyboard(10),
        get_list_item_delete_confirm_keyboard(10, 20),
        get_checklist_run_keyboard(run, 10),
        get_checklist_finished_keyboard(10),
        get_voice_list_preview_keyboard("new"),
        get_voice_list_preview_keyboard("add", 10),
    ]:
        callbacks.update(_collect_callback_data(keyboard))

    unregistered = {
        callback_data
        for callback_data in callbacks
        if not _is_registered(callback_data, patterns)
    }

    assert unregistered == set()


def test_settings_keyboards_have_registered_callbacks():
    """Settings buttons should route to registered handlers or URL links."""
    patterns = _collect_application_callback_patterns()
    callbacks = set()
    for keyboard in [
        get_settings_keyboard(),
        get_settings_back_home_keyboard(),
        get_about_keyboard("https://example.com/repo", "https://example.com/changelog"),
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
        "🚗 Водитель",
        "⚙️ Настройки",
        "🌐 Web-версия",
        "👥 Поделиться ботом",
        "⌨️ Скрыть меню",
        "❓ Помощь",
    }
    assert all(len(row) <= 2 for row in reply_markup["keyboard"])

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
        "🚗 Водитель",
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
        get_driver_reminder_repeat_keyboard(),
        get_driver_section_keyboard(),
        get_driver_section_keyboard("wash"),
        get_driver_section_keyboard("tires"),
        get_driver_templates_keyboard(),
        get_driver_created_list_keyboard(10),
        get_driver_journal_keyboard(
            has_more=True,
            entries=[SimpleNamespace(id=70, metadata_json={"manual": True})],
        ),
        get_driver_journal_entry_keyboard(70),
        get_driver_journal_delete_confirm_keyboard(70),
        get_driver_journal_type_keyboard(),
        get_driver_vehicles_keyboard([]),
        get_driver_vehicle_preset_keyboard(list_vehicle_presets()),
        get_driver_vehicle_preset_confirm_keyboard(),
        get_driver_vehicle_view_keyboard(10),
        get_driver_vehicle_delete_confirm_keyboard(10),
        get_driver_fuel_keyboard([]),
        get_driver_fuel_history_keyboard(10, []),
        get_driver_fuel_entry_keyboard(10, 20),
        get_driver_fuel_delete_confirm_keyboard(10, 20),
        get_driver_expenses_keyboard([]),
        get_driver_expense_view_keyboard(10),
        get_driver_expense_delete_confirm_keyboard(10),
        get_driver_expense_category_keyboard(),
        get_driver_documents_keyboard([]),
        get_driver_document_view_keyboard(10),
        get_driver_document_delete_confirm_keyboard(10),
        get_driver_document_type_keyboard(),
        get_driver_document_remind_keyboard(),
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
