"""Button review: stale buttons, wizards left through other screens,
duplicate buttons and the reminder list time."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telegram import CallbackQuery, Chat, Message, Update
from telegram import User as TgUser
from telegram.ext import CallbackQueryHandler, ConversationHandler

from src.bot.app import create_application
from src.bot.handlers import conversation_exit
from src.bot.handlers.conversation_exit import LeaveWizardHandler, stale_button_callback
from src.bot.keyboards import (
    get_back_home_inline_keyboard,
    get_list_members_keyboard,
    get_reminders_list_keyboard,
    get_web_entry_keyboard,
)
from src.bot.keyboards.builder import get_driver_journal_keyboard


def _callback_update(data: str) -> Update:
    user = TgUser(id=42, first_name="T", is_bot=False)
    message = Message(
        message_id=1,
        date=datetime(2026, 10, 14, tzinfo=timezone.utc),
        chat=Chat(id=42, type="private"),
    )
    query = CallbackQuery(id="1", from_user=user, chat_instance="ci", data=data, message=message)
    return Update(update_id=1, callback_query=query)


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


# --- Registration ----------------------------------------------------------------------

def test_stale_button_handler_is_registered_last():
    app = create_application()
    group = app.handlers[0]
    last = group[-1]
    assert isinstance(last, CallbackQueryHandler)
    assert last.callback is stale_button_callback
    assert last.pattern is None


def test_every_wizard_reenters_cancels_and_hands_off_other_buttons():
    app = create_application()
    conversations = [h for h in app.handlers[0] if isinstance(h, ConversationHandler)]
    assert len(conversations) >= 20

    for conv in conversations:
        assert conv.allow_reentry, conv.name
        assert isinstance(conv.fallbacks[-1], LeaveWizardHandler), conv.name
        cancel_patterns = {
            h.pattern.pattern for h in conv.fallbacks
            if isinstance(h, CallbackQueryHandler) and getattr(h, "pattern", None) is not None
        }
        assert "^cancel$" in cancel_patterns, conv.name


# --- Leaving a wizard through another screen's button -------------------------------------

def test_navigation_button_inside_wizard_is_handed_to_its_screen():
    """Before: «⬅️ К лекарству» opened the medication but the wizard kept
    waiting for text and swallowed the next message."""
    create_application()
    leave = LeaveWizardHandler()

    target = leave.check_update(_callback_update("med_view:5"))
    assert target is not None
    handler, _ = target
    assert handler.callback.__name__ == "medication_view_callback"

    # A button that only a closed wizard understands is not "navigation".
    assert leave.check_update(_callback_update("rem_time_10min")) is None


@pytest.mark.asyncio
async def test_leave_wizard_runs_target_and_ends_conversation():
    calls = []

    class Target:
        async def handle_update(self, update, application, check_result, context):
            calls.append(check_result)

    result = await LeaveWizardHandler().handle_update(
        _callback_update("notes_list"), None, (Target(), "match"), SimpleNamespace()
    )

    assert calls == ["match"]
    assert result == ConversationHandler.END


def test_wizard_routes_navigation_through_leave_handler():
    """End to end on the real reminder wizard waiting for a custom time."""
    app = create_application()
    conv = next(
        h for h in app.handlers[0]
        if isinstance(h, ConversationHandler) and any(
            getattr(e, "pattern", None) is not None and e.pattern.pattern == "^reminder_create$"
            for e in h.entry_points
        )
    )
    update = _callback_update("notes_list")
    key = conv._get_key(update)
    waiting_state = next(iter(conv.states))
    conv._conversations[key] = waiting_state
    try:
        check = conv.check_update(update)
    finally:
        conv._conversations.pop(key, None)

    assert check is not None
    assert any(isinstance(part, LeaveWizardHandler) for part in check if not isinstance(part, (tuple, str, int)))


# --- Stale buttons ------------------------------------------------------------------------

class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_reply_markup(self, reply_markup=None):
        self.edits.append(reply_markup)

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append(text)


@pytest.mark.asyncio
async def test_stale_wizard_button_gets_an_answer():
    query = FakeQuery("rem_time_10min")
    context = SimpleNamespace(user_data={"reminder_text": "x"})

    await stale_button_callback(SimpleNamespace(callback_query=query), context)

    assert query.answers and query.answers[0][1] is True
    assert "устарела" in query.answers[0][0]
    assert context.user_data == {}


@pytest.mark.asyncio
async def test_stale_cancel_button_just_cancels():
    query = FakeQuery("cancel")

    await stale_button_callback(SimpleNamespace(callback_query=query), SimpleNamespace(user_data={}))

    assert query.answers == [("Отменено", False)]
    assert query.edits == ["❌ Отменено"]


# --- Duplicate / misleading buttons -----------------------------------------------------------

def test_back_button_no_longer_duplicates_menu():
    assert _callbacks(get_back_home_inline_keyboard()) == ["home"]
    assert _callbacks(get_back_home_inline_keyboard("lists_list")) == ["lists_list", "home"]


def test_web_entry_has_single_menu_button():
    callbacks = _callbacks(get_web_entry_keyboard())
    assert len(callbacks) == len(set(callbacks))


def test_list_owner_row_does_not_leave_the_members_screen():
    markup = get_list_members_keyboard(
        1,
        [{"role": "owner", "display_name": "A"}, {"role": "editor", "display_name": "B", "member_id": 7}],
    )
    callbacks = _callbacks(markup)
    assert callbacks[0].startswith("noop")
    assert len(callbacks) == len(set(callbacks))


def test_journal_reset_vehicle_only_when_a_vehicle_is_selected():
    assert len(_callbacks(get_driver_journal_keyboard())) == len(set(_callbacks(get_driver_journal_keyboard())))
    with_vehicle = _callbacks(get_driver_journal_keyboard(vehicle_id=3))
    assert "driver_journal_filter:all:0:all" in with_vehicle


# --- Reminder list -------------------------------------------------------------------------

def test_reminder_list_shows_user_local_time_and_real_status():
    """Before: a 09:00 Moscow reminder was listed as 06:00 and canceled ones as ✅."""
    reminders = [
        SimpleNamespace(id=1, text="Зарядка", status=SimpleNamespace(value="active"),
                        remind_at_utc=datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)),
        SimpleNamespace(id=2, text="Отменённое", status=SimpleNamespace(value="canceled"),
                        remind_at_utc=datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)),
    ]

    markup = get_reminders_list_keyboard(reminders, user_timezone="Europe/Moscow")
    labels = [row[0].text for row in markup.inline_keyboard[:2]]

    assert labels[0] == "⏰ [14.10 09:00] Зарядка"
    assert labels[1].startswith("🚫 ")


def test_conversation_exit_binds_application():
    app = create_application()
    assert conversation_exit._application is app
