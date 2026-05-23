"""Bot handlers package."""

import warnings

from telegram.warnings import PTBUserWarning


# These conversations intentionally mix inline buttons for entry/navigation
# with message handlers for text input. Switching to per_message=True would
# change conversation tracking semantics, so suppress only this known PTB hint.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked.*",
    category=PTBUserWarning,
)

from src.bot.handlers.navigation import (
    start_handler,
    help_handler,
    back_handler,
    home_handler,
)
from src.bot.handlers.lists import (
    import_list_handler,
    join_list_handler,
    list_create_conv,
    list_add_item_conv,
    list_add_bulk_conv,
    list_edit_item_conv,
    list_rename_conv,
)
from src.bot.handlers.medications import (
    medication_create_conv,
    medication_reminder_conv,
)
from src.bot.handlers.reminders import (
    reminder_create_conv,
)
from src.bot.handlers.settings import (
    settings_timezone_conv,
)

__all__ = [
    # Navigation
    "start_handler",
    "help_handler",
    "back_handler",
    "home_handler",
    # Lists
    "list_create_conv",
    "list_add_item_conv",
    "list_add_bulk_conv",
    "list_edit_item_conv",
    "list_rename_conv",
    "import_list_handler",
    "join_list_handler",
    # Medications
    "medication_create_conv",
    "medication_reminder_conv",
    # Reminders
    "reminder_create_conv",
    # Settings
    "settings_timezone_conv",
]
