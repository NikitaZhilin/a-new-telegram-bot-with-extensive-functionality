"""Tests for bot callback registration."""

from telegram.ext import ConversationHandler

from src.bot.app import create_application
from src.bot.keyboards import get_main_menu_inline_keyboard, get_main_menu_keyboard


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


def test_important_callback_patterns_are_registered():
    """Buttons for implemented flows should have registered handlers."""
    app = create_application()

    patterns = set()
    for handlers in app.handlers.values():
        for handler in handlers:
            patterns.update(_collect_callback_patterns(handler))

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
        "^med_taken:",
        "^med_skip:",
        "^med_snooze:",
        "^med_remind:",
        "^med_rem_freq:",
        "^med_rem_time:",
        "^list_delete_confirm:",
        "^list_item_delete_confirm:",
        "^reminders_page:",
        "^rem_date_after_tomorrow$",
        "^rem_date_next_week$",
        "^rem_time_back$",
        "^rem_time_custom$",
        "^rem_confirm_back$",
        "^settings_timezone$",
        "^settings_subscription$",
        "^tz_custom$",
    }

    assert expected <= patterns


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
        "⚙️ Настройки",
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
        "⚙️ Настройки",
        "👥 Поделиться ботом",
    }
