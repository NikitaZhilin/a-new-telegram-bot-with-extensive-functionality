"""Global bot activity tracking handler."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.db.session import async_session_maker
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


async def activity_event_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Best-effort analytics hook that never blocks user-facing handlers."""
    try:
        async with async_session_maker() as session:
            await ActivityService(session).record_telegram_update(update)
            await session.commit()
    except Exception:
        logger.debug("Could not record bot activity event", exc_info=True)
