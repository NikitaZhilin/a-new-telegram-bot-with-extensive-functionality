"""Broken buttons answer the user and alert admins; web hides login keys."""

import logging
from types import SimpleNamespace

import httpx
import pytest

from src.api.app import RedactTokenFilter, create_application, redact_query_tokens
from src.bot import app as bot_app
from src.config import settings


class FakeQuery:
    def __init__(self, data="med_taken:5", fail_answer=False):
        self.data = data
        self.fail_answer = fail_answer
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        if self.fail_answer:
            raise RuntimeError("query already answered")
        self.answers.append((text, show_alert))


class FakeMessage:
    def __init__(self, text=None):
        self.text = text
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text, kwargs))


def _update(query=None, message=None):
    return SimpleNamespace(
        callback_query=query,
        effective_message=message,
        effective_user=SimpleNamespace(id=123),
    )


@pytest.fixture(autouse=True)
def _reset_admin_cooldown(monkeypatch):
    bot_app._admin_error_last_sent.clear()
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_IDS", "999")


def _broken():
    try:
        raise ValueError("boom <module> & co")
    except ValueError as exc:
        return exc


@pytest.mark.asyncio
async def test_broken_button_gets_an_answer_and_admin_is_notified(monkeypatch):
    query = FakeQuery()
    update = _update(query=query)
    bot = FakeBot()
    context = SimpleNamespace(error=_broken(), bot=bot)

    await bot_app.error_handler(update, context)

    assert query.answers and query.answers[0][1] is True
    assert len(bot.sent) == 1
    chat_id, text, kwargs = bot.sent[0]
    assert chat_id == 999
    assert "ValueError" in text and "med_taken:5" in text
    assert "parse_mode" not in kwargs, "plain text: tracebacks with <module> must not break it"
    assert len(text) <= bot_app.ADMIN_ERROR_MAX_CHARS


@pytest.mark.asyncio
async def test_already_answered_button_falls_back_to_chat_message(monkeypatch):
    message = FakeMessage()
    update = _update(query=FakeQuery(fail_answer=True), message=message)
    context = SimpleNamespace(error=_broken(), bot=FakeBot())

    await bot_app.error_handler(update, context)

    assert message.replies == [bot_app.USER_ERROR_TEXT]


@pytest.mark.asyncio
async def test_same_error_is_reported_to_admin_once_per_cooldown(monkeypatch):
    bot = FakeBot()
    error = _broken()

    for _ in range(5):
        await bot_app.error_handler(_update(query=FakeQuery()), SimpleNamespace(error=error, bot=bot))

    assert len(bot.sent) == 1


def test_login_key_is_hidden_in_access_log():
    assert redact_query_tokens("GET /web?token=secretKEY_1&x=1") == "GET /web?token=***&x=1"
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/web?token=secretKEY_1", "1.1", 200),
        None,
    )
    RedactTokenFilter().filter(record)
    assert "secretKEY_1" not in record.getMessage()


@pytest.mark.asyncio
async def test_web_pages_are_not_cached_and_send_no_referrer():
    app = create_application()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/web")
        health = await client.get("/health")

    assert page.status_code == 200
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["cache-control"] == "no-store"
    assert health.headers["referrer-policy"] == "no-referrer"
