"""Timezone helpers for bot context.

python-telegram-bot v21 does not expose an aiogram-style middleware API. Timezone lookup is
handled explicitly in services/handlers for now; this module remains importable
so future middleware work has a stable place to land.
"""

from src.config import settings


def get_default_timezone() -> str:
    """Return the configured default timezone."""
    return settings.TIMEZONE_DEFAULT
