"""List states."""

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


class ListStates(StatesGroup):
    """List creation/editing states."""
    WAIT_TITLE = State("WAIT_TITLE")
    WAIT_ADD_ITEM = State("WAIT_ADD_ITEM")
    WAIT_ADD_ITEMS_BULK = State("WAIT_ADD_ITEMS_BULK")
    WAIT_VOICE_MESSAGE = State("WAIT_VOICE_MESSAGE")
    WAIT_VOICE_CONFIRM = State("WAIT_VOICE_CONFIRM")
    WAIT_VOICE_TEXT_EDIT = State("WAIT_VOICE_TEXT_EDIT")
    WAIT_EDIT_TITLE = State("WAIT_EDIT_TITLE")
    WAIT_EDIT_ITEM = State("WAIT_EDIT_ITEM")
