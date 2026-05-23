"""Regression tests for startup stabilization fixes."""

import inspect

from src.api.routes import admin
from src.api import app as api_app
from src.bot import app as bot_app
from src.config import Settings
from src.bot.handlers.settings import settings_timezone_conv
from src.bot.states import SettingsStates
from src.db.models import TodoList


def test_pagination_callbacks_are_async():
    """PTB callback handlers must await async Telegram methods."""
    assert inspect.iscoroutinefunction(bot_app.lists_page_callback)
    assert inspect.iscoroutinefunction(bot_app.reminders_page_callback)


def test_timezone_custom_handler_precedes_generic_tz_handler():
    """tz_custom must not be swallowed by the generic ^tz_ handler."""
    handlers = settings_timezone_conv.states[SettingsStates.WAIT_TIMEZONE]

    custom_index = next(
        i for i, handler in enumerate(handlers)
        if handler.pattern.pattern == "^tz_custom$"
    )
    generic_index = next(
        i for i, handler in enumerate(handlers)
        if handler.pattern.pattern == "^tz_"
    )

    assert custom_index < generic_index


def test_admin_stats_uses_todo_list_model():
    """The admin stats route should count TodoList rows, not typing.List."""
    assert admin.get_stats.__globals__["TodoList"] is TodoList
    assert "get_count(TodoList)" in inspect.getsource(admin.get_stats)


def test_api_docs_can_be_disabled(monkeypatch):
    """Public deployments should be able to hide interactive API docs."""
    monkeypatch.setattr(api_app.settings, "API_DOCS_ENABLED", False)

    app = api_app.create_application()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_cors_origins_are_parsed_from_comma_separated_env():
    settings = Settings(
        BOT_TOKEN="123:test",
        ADMIN_TOKEN="secret",
        CORS_ORIGINS="https://admin.example.com, https://bot.example.com ",
    )

    assert settings.cors_origin_list == [
        "https://admin.example.com",
        "https://bot.example.com",
    ]
