"""Tests for driver assistant input parsing helpers."""

from types import SimpleNamespace

import pytest

from src.bot.handlers import reminders as reminders_module
from src.bot.handlers.driver import _clear_driver_context, _limit_text, _parse_bool
from src.bot.states import ReminderStates


def test_driver_full_tank_parser_accepts_clear_values():
    """Full-tank input should handle common Russian and compact values."""
    assert _parse_bool("да") is True
    assert _parse_bool("полный") is True
    assert _parse_bool("нет") is False
    assert _parse_bool("частично") is False


def test_driver_full_tank_parser_rejects_ambiguous_values():
    """Ambiguous full-tank input should not silently become True."""
    with pytest.raises(ValueError):
        _parse_bool("наверное")


def test_driver_text_limit_trims_database_sized_fields():
    """Compact text fields should be safe for bounded database columns."""
    assert _limit_text("  АЗС  ", 255) == "АЗС"
    assert len(_limit_text("x" * 300, 255)) == 255


def test_clear_driver_context_removes_wizard_ids_and_keeps_unrelated_state():
    """Driver cleanup should remove every driver_* key, including wizard message ids."""
    context = SimpleNamespace(
        user_data={
            "driver_vehicle_id": 1,
            "driver_wizard_chat_id": 2,
            "driver_wizard_message_id": 3,
            "reminder_text": "keep me",
        }
    )

    _clear_driver_context(context)

    assert context.user_data == {"reminder_text": "keep me"}


@pytest.mark.asyncio
async def test_driver_reminder_template_starts_reminder_flow(monkeypatch):
    """Driver reminder templates should prefill text and open the reminder date step."""
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeQuery:
        data = "driver_reminder_template:oil"
        edited = None
        reply_markup = None

        async def answer(self):
            return None

        async def edit_message_text(self, text, reply_markup=None):
            self.edited = text
            self.reply_markup = reply_markup

    async def fake_get_user_timezone(update, session):
        return "Europe/Moscow"

    monkeypatch.setattr(reminders_module, "async_session_maker", lambda: FakeSession())
    monkeypatch.setattr(reminders_module, "_get_user_timezone", fake_get_user_timezone)

    query = FakeQuery()
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={"linked_list_id": 1, "linked_list_title": "Old"})

    state = await reminders_module.reminder_create_start(update, context)

    assert state == ReminderStates.WAIT_DATE
    assert context.user_data["reminder_text"] == "Заменить моторное масло и масляный фильтр"
    assert context.user_data["user_timezone"] == "Europe/Moscow"
    assert "Авто-напоминание" in query.edited
    assert "linked_list_id" not in context.user_data
