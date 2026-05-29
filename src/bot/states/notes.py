"""Note states."""

from src.bot.states.lists import State, StatesGroup


class NoteStates(StatesGroup):
    """Note creation/editing states."""

    WAIT_TITLE = State("NOTE_WAIT_TITLE")
    WAIT_TEXT = State("NOTE_WAIT_TEXT")
    WAIT_EDIT_TITLE = State("NOTE_WAIT_EDIT_TITLE")
    WAIT_EDIT_TEXT = State("NOTE_WAIT_EDIT_TEXT")
