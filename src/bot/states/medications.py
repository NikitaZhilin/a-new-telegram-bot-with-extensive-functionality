"""Medication states."""


class StatesGroupMeta(type):
    pass


class StatesGroup(metaclass=StatesGroupMeta):
    pass


class State:
    def __init__(self, name: str = ""):
        self.name = name

    def __str__(self) -> str:
        return self.name or id(self)


class MedicationStates(StatesGroup):
    """Medication creation/reminder states."""

    WAIT_NAME = State("WAIT_NAME")
    WAIT_DOSAGE = State("WAIT_DOSAGE")
    WAIT_INSTRUCTIONS = State("WAIT_INSTRUCTIONS")
    WAIT_IMPORTANCE = State("WAIT_IMPORTANCE")
    WAIT_REMINDER_TIME = State("WAIT_REMINDER_TIME")
    WAIT_EDIT_NAME = State("WAIT_EDIT_NAME")
    WAIT_EDIT_DOSAGE = State("WAIT_EDIT_DOSAGE")
    WAIT_EDIT_INSTRUCTIONS = State("WAIT_EDIT_INSTRUCTIONS")
