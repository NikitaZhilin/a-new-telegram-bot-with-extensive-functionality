"""Settings states."""

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


class SettingsStates(StatesGroup):
    """Settings states."""
    WAIT_TIMEZONE = State("WAIT_TIMEZONE")
    WAIT_TIMEZONE_CUSTOM = State("WAIT_TIMEZONE_CUSTOM")
