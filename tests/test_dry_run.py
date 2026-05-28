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


def test_build_mini_app_web_url_requires_https(monkeypatch):
    monkeypatch.setattr(main.settings, "WEB_PUBLIC_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(main.settings, "APP_BASE_URL", None)

    assert main.build_mini_app_web_url() is None

    monkeypatch.setattr(main.settings, "WEB_PUBLIC_URL", "https://bot.example.com/")

    assert main.build_mini_app_web_url() == "https://bot.example.com/miniapp"


@pytest.mark.asyncio
async def test_configure_menu_button_dry_run_uses_https_url_without_network(monkeypatch):
    monkeypatch.setattr(main.settings, "WEB_PUBLIC_URL", "https://bot.example.com")
    monkeypatch.setattr(main.settings, "APP_BASE_URL", None)
    monkeypatch.setattr(main.settings, "MINI_APP_MENU_BUTTON_TEXT", "RememberMe")

    result = await main.configure_menu_button(dry_run=True)

    assert result == {
        "text": "RememberMe",
        "url": "https://bot.example.com/miniapp",
        "mode": "dry-run",
    }


def test_production_readiness_check_accepts_strict_mini_app_settings(monkeypatch):
    monkeypatch.setattr(main.settings, "WEB_PUBLIC_URL", "https://bot.example.com")
    monkeypatch.setattr(main.settings, "APP_BASE_URL", None)
    monkeypatch.setattr(main.settings, "API_DOCS_ENABLED", False)
    monkeypatch.setattr(main.settings, "WEB_TEST_LOGIN_ENABLED", False)
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "https://bot.example.com")
    monkeypatch.setattr(main.settings, "USER_AUTH_MAX_AGE_SECONDS", 86400)
    monkeypatch.setattr(main.settings, "MINI_APP_MENU_BUTTON_TEXT", "RememberMe")

    assert main.production_readiness_errors() == []
    assert main.run_production_check() == {
        "url": "https://bot.example.com/miniapp",
        "status": "ok",
    }


def test_production_readiness_check_rejects_insecure_settings(monkeypatch):
    monkeypatch.setattr(main.settings, "WEB_PUBLIC_URL", "http://127.0.0.1:8000/web")
    monkeypatch.setattr(main.settings, "APP_BASE_URL", None)
    monkeypatch.setattr(main.settings, "API_DOCS_ENABLED", True)
    monkeypatch.setattr(main.settings, "WEB_TEST_LOGIN_ENABLED", True)
    monkeypatch.setattr(main.settings, "CORS_ORIGINS", "*, http://example.com")
    monkeypatch.setattr(main.settings, "USER_AUTH_MAX_AGE_SECONDS", 172800)
    monkeypatch.setattr(main.settings, "MINI_APP_MENU_BUTTON_TEXT", "")

    errors = main.production_readiness_errors()

    assert "WEB_PUBLIC_URL or APP_BASE_URL must be an HTTPS URL" in errors
    assert "WEB_PUBLIC_URL/APP_BASE_URL must be the base URL, not the /web or /miniapp URL" in errors
    assert "API_DOCS_ENABLED must be false in production" in errors
    assert "WEB_TEST_LOGIN_ENABLED must be false in production" in errors
    assert "CORS_ORIGINS must not contain * in production" in errors
    assert "CORS_ORIGINS must contain only HTTPS origins in production" in errors
    assert "USER_AUTH_MAX_AGE_SECONDS must not exceed 86400 for Mini App auth" in errors
    assert "MINI_APP_MENU_BUTTON_TEXT must not be empty" in errors
