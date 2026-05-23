"""
FSM states for Telegram bot conversations.

Each state group corresponds to a feature (notes, lists, reminders, settings).
"""

from telegram.ext import ApplicationHandlerStop


class StatesGroupMeta(type):
    """Metaclass for creating state groups."""
    pass


class StatesGroup(metaclass=StatesGroupMeta):
    """Base class for state groups."""
    pass


class State:
    """State marker class."""
    def __init__(self, name: str = ""):
        self.name = name
    
    def __str__(self) -> str:
        return self.name or id(self)


class NoteStates(StatesGroup):
    """Note creation/editing states."""
    WAIT_TITLE = State("WAIT_TITLE")
    WAIT_BODY = State("WAIT_BODY")
    WAIT_EDIT_TITLE = State("WAIT_EDIT_TITLE")
    WAIT_EDIT_BODY = State("WAIT_EDIT_BODY")


class ListStates(StatesGroup):
    """List creation/editing states."""
    WAIT_TITLE = State("WAIT_TITLE")
    WAIT_ADD_ITEM = State("WAIT_ADD_ITEM")
    WAIT_ADD_ITEMS_BULK = State("WAIT_ADD_ITEMS_BULK")
    WAIT_EDIT_TITLE = State("WAIT_EDIT_TITLE")
    WAIT_EDIT_ITEM = State("WAIT_EDIT_ITEM")


class ReminderStates(StatesGroup):
    """Reminder creation states."""
    WAIT_TEXT = State("WAIT_TEXT")
    WAIT_DATE = State("WAIT_DATE")
    WAIT_TIME = State("WAIT_TIME")
    WAIT_TIME_CUSTOM = State("WAIT_TIME_CUSTOM")
    WAIT_CONFIRM = State("WAIT_CONFIRM")
    WAIT_REPEAT = State("WAIT_REPEAT")


class SettingsStates(StatesGroup):
    """Settings states."""
    WAIT_TIMEZONE = State("WAIT_TIMEZONE")
    WAIT_TIMEZONE_CUSTOM = State("WAIT_TIMEZONE_CUSTOM")
