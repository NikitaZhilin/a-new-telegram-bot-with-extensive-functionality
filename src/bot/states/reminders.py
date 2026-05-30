"""Reminder states."""

from telegram.ext import ApplicationHandlerStop


class StatesGroupMeta(type):
    pass


class StatesGroup(metaclass=StatesGroupMeta):
    pass


class State:
    def __init__(self, name: str = ""):
        self.name = name
    
    def __str__(self) -> str:
        return self.name or id(self)


class ReminderStates(StatesGroup):
    """Reminder creation states."""
    WAIT_TEXT = State("WAIT_TEXT")
    WAIT_DATE = State("WAIT_DATE")
    WAIT_TIME = State("WAIT_TIME")
    WAIT_TIME_CUSTOM = State("WAIT_TIME_CUSTOM")
    WAIT_NOTIFY = State("WAIT_NOTIFY")
    WAIT_CONFIRM = State("WAIT_CONFIRM")
    WAIT_REPEAT = State("WAIT_REPEAT")
    WAIT_EDIT_TEXT = State("WAIT_EDIT_TEXT")
    WAIT_EDIT_TIME = State("WAIT_EDIT_TIME")
