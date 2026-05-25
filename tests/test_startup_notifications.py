"""Startup notification deduplication tests."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src import main
from src.db.base import Base


@pytest.mark.asyncio
async def test_startup_update_marker_deduplicates_per_user_and_version(monkeypatch):
    """Startup update should be sent once per Telegram user per app version."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "async_session_maker", session_maker)

    telegram_id = 95001
    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.0-beta") is False

    await main._record_startup_update_sent(
        telegram_id=telegram_id,
        user_id=None,
        app_version="0.8.0-beta",
    )

    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.0-beta") is True
    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.1-beta") is False
    assert await main._startup_update_sent(telegram_id=telegram_id + 1, app_version="0.8.0-beta") is False

    await engine.dispose()
