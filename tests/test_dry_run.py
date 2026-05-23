"""Tests for safe dry-run startup modes."""

import pytest

from src import main


class FakeSession:
    def __init__(self):
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def execute(self, statement):
        self.executed.append(str(statement))


@pytest.mark.asyncio
async def test_dry_run_bot_builds_application_without_initialize(monkeypatch):
    from src.bot import app as bot_app_module

    initialized = False

    class FakeApplication:
        handlers = {0: [object()], 1: [object(), object()]}

    async def fail_initialize():
        nonlocal initialized
        initialized = True
        raise AssertionError("dry-run must not initialize Telegram application")

    fake_app = FakeApplication()
    fake_app.initialize = fail_initialize
    monkeypatch.setattr(bot_app_module, "create_application", lambda: fake_app)

    await main.dry_run_bot()

    assert main.count_bot_handlers(fake_app) == 3
    assert initialized is False


@pytest.mark.asyncio
async def test_dry_run_worker_checks_database_without_bot_initialize(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(main, "async_session_maker", lambda: fake_session)

    await main.dry_run_worker()

    assert fake_session.executed == ["SELECT 1"]


@pytest.mark.asyncio
async def test_dry_run_all_uses_safe_component_checks(monkeypatch):
    calls = []

    async def fake_dry_run_bot():
        calls.append("bot")

    async def fake_dry_run_worker():
        calls.append("worker")

    monkeypatch.setattr(main, "dry_run_bot", fake_dry_run_bot)
    monkeypatch.setattr(main, "dry_run_worker", fake_dry_run_worker)

    await main.dry_run_all()

    assert calls == ["bot", "worker"]
