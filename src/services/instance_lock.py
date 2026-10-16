"""Only one bot process may poll Telegram with the same token.

A second copy (a manual `python -m src.main bot` on the server, an old
container left running) makes Telegram answer getUpdates with «Conflict», and
both copies start losing updates. A PostgreSQL advisory lock, held on its own
connection for the whole life of the process, lets exactly one copy run; the
other one waits and logs why.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)

LOCK_KEYS = {"bot": 724_331_001}
RETRY_SECONDS = 30


class InstanceLock:
    def __init__(self, connection: Optional[AsyncConnection], name: str):
        self.connection = connection
        self.name = name

    async def release(self) -> None:
        if self.connection is None:
            return
        try:
            await self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEYS[self.name]})
            await self.connection.close()
        except Exception:
            logger.debug("Could not release instance lock", exc_info=True)
        self.connection = None


async def acquire_instance_lock(engine: AsyncEngine, name: str = "bot", wait: bool = True) -> Optional[InstanceLock]:
    """Hold the lock for ``name``; waits while another copy has it. No-op outside PostgreSQL."""
    if engine.dialect.name != "postgresql":
        return InstanceLock(None, name)
    key = LOCK_KEYS[name]
    warned = False
    while True:
        connection = await engine.connect()
        try:
            got = (await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})).scalar()
            await connection.commit()
        except Exception:
            await connection.close()
            raise
        if got:
            if warned:
                logger.warning("Instance lock '%s' acquired: the other copy has stopped", name)
            return InstanceLock(connection, name)
        await connection.close()
        if not wait:
            return None
        if not warned:
            logger.error(
                "Another '%s' process is already running with this database; this copy waits and does not "
                "poll Telegram (two copies would steal each other's updates)",
                name,
            )
            warned = True
        await asyncio.sleep(RETRY_SECONDS)
