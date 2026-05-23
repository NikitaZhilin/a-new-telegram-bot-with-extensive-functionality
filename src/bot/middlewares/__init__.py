"""Bot middleware setup.

python-telegram-bot v21 has no middleware registration API matching aiogram.
Keep this hook as a no-op until the bot needs PTB-specific hooks.
"""

from telegram.ext import Application


def setup_middlewares(application: Application) -> None:
    """Setup bot middlewares."""
    return None
