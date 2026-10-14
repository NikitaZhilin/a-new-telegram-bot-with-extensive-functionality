"""Error journal (admin) and user feedback."""

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.base import Base
from src.db.models import ErrorEvent
from src.services.error_journal import (
    ErrorJournalHandler,
    ErrorJournalService,
    _section_from_path,
    capture_record,
    detect_section,
    store_errors,
)
from src.services.feedback_service import FeedbackLimitError, FeedbackService, HOURLY_LIMIT


def _record(logger_name="src.bot.app", msg="boom", exc=None, **extra):
    exc_info = (type(exc), exc, exc.__traceback__) if exc is not None else None
    record = logging.LogRecord(logger_name, logging.ERROR, __file__, 10, msg, None, exc_info)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _raise(exc):
    try:
        raise exc
    except Exception as caught:  # noqa: BLE001
        return caught


# --- Section detection -------------------------------------------------------

@pytest.mark.parametrize(
    "path, section",
    [
        ("/app/src/bot/handlers/medications.py", "medications"),
        ("/app/src/bot/handlers/reminders.py", "reminders"),
        ("/app/src/services/note_service.py", "notes"),
        ("/app/src/repositories/list_repo.py", "lists"),
        ("/app/src/bot/handlers/checklists.py", "checklists"),
        ("/app/src/bot/handlers/driver.py", "driver"),
        ("/app/src/worker/reminder_worker.py", "worker"),
        ("/app/src/api/routes/web.py", "web"),
        ("/app/src/api/routes/admin.py", "api"),
        ("/app/src/bot/handlers/feedback.py", "feedback"),
        ("/usr/lib/python3/site-packages/telegram/_bot.py", None),
    ],
)
def test_section_from_code_place(path, section):
    assert _section_from_path(path) == section


def test_section_from_pressed_button_when_code_place_is_unknown():
    exc = _raise(ValueError("x"))
    assert detect_section(service="bot", exc=exc, logger_name="src.bot.app", callback_data="rem_finish") == "reminders"
    assert detect_section(service="bot", exc=exc, logger_name="src.bot.app", callback_data="med_taken:1:2") == "medications"
    assert detect_section(service="worker", exc=None, logger_name="something") == "worker"


def test_telegram_network_errors_have_own_section():
    from telegram.error import NetworkError

    assert detect_section(service="bot", exc=NetworkError("down"), logger_name="telegram.ext.Updater") == "telegram"


# --- Capture and grouping ----------------------------------------------------

def test_capture_keeps_context_and_user_but_not_free_text():
    exc = _raise(KeyError("reminder_id"))
    item = capture_record(
        _record(exc=exc, error_context="Кнопка: rem_finish", telegram_id=42, callback_data="rem_finish"),
        "bot",
    )
    assert item.error_type == "KeyError"
    assert item.section == "reminders"
    assert item.context == "Кнопка: rem_finish"
    assert item.telegram_id == 42
    assert "Traceback" in item.traceback


def test_structlog_json_messages_group_despite_timestamps():
    first = capture_record(_record(msg=json.dumps({"event": "Menu failed", "timestamp": "2026-10-14T10:00:00"})), "bot")
    second = capture_record(_record(msg=json.dumps({"event": "Menu failed", "timestamp": "2026-10-14T11:00:00"})), "bot")
    assert first.fingerprint == second.fingerprint
    assert first.message == "Menu failed"


def test_all_in_one_process_tells_services_apart():
    item = capture_record(_record(logger_name="src.worker.reminder_worker"), "all")
    assert item.service == "worker"
    item = capture_record(_record(logger_name="uvicorn.error"), "all")
    assert item.service == "api"


@pytest.mark.asyncio
async def test_same_error_is_counted_and_resolved_error_reopens(db_session):
    exc = _raise(ValueError("bad"))
    one = capture_record(_record(exc=exc), "bot")
    two = capture_record(_record(exc=exc), "bot")
    await store_errors(db_session, [one, two])
    events = (await db_session.execute(select(ErrorEvent))).scalars().all()
    assert len(events) == 1 and events[0].count == 2

    journal = ErrorJournalService(db_session)
    assert await journal.resolve(events[0].id)
    assert await journal.list_events() == []

    await store_errors(db_session, [capture_record(_record(exc=exc), "bot")])
    reopened = await journal.list_events()
    assert [event.id for event in reopened] == [events[0].id]
    assert reopened[0].count == 3 and reopened[0].resolved_at is None
    summary = await journal.summary()
    assert summary["open_kinds"] == 1 and summary["by_section"][0]["occurrences"] == 3


@pytest.mark.asyncio
async def test_logging_handler_writes_errors_in_background():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    handler = ErrorJournalHandler("bot", session_factory=maker)
    handler.ensure_started = lambda: None  # flush by hand in this test
    logger = logging.getLogger("src.bot.handlers.notes.test")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        exc = _raise(RuntimeError("db hiccup"))
        logger.error("Note save failed", exc_info=exc)
        logger.error("Again higher up", exc_info=exc)  # same exception re-logged (uvicorn style)
        logger.warning("not an error")
        assert await handler.flush() == 1
    finally:
        logger.removeHandler(handler)
    async with maker() as session:
        events = (await session.execute(select(ErrorEvent))).scalars().all()
    await engine.dispose()
    assert len(events) == 1
    assert events[0].count == 1
    assert events[0].section == "notes"
    assert "db hiccup" in events[0].message


@pytest.mark.asyncio
async def test_journal_never_records_its_own_failures():
    handler = ErrorJournalHandler("bot", session_factory=lambda: None)
    handler.emit(_record(logger_name="src.services.error_journal"))
    handler.emit(_record(logger_name="sqlalchemy.engine"))
    assert len(handler._queue) == 0


# --- Feedback ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_feedback_is_stored_and_matched_with_user_errors(db_session):
    service = FeedbackService(db_session)
    item = await service.create(telegram_id=555, kind="bug", text="  Не приходит напоминание  ", first_name="Аня")
    assert item.id and item.status == "new" and item.text == "Не приходит напоминание"
    assert (await service.create(telegram_id=555, kind="strange", text="x")).kind == "other"

    exc = _raise(ValueError("boom"))
    await store_errors(db_session, [capture_record(_record(exc=exc, telegram_id=555), "bot")])
    errors = await service.recent_errors_for(555)
    assert len(errors) == 1

    assert await service.count_new() == 2
    await service.save_reply(item.id, "Исправили, спасибо!")
    assert (await service.get(item.id)).status == "answered"
    assert await service.count_new() == 1


@pytest.mark.asyncio
async def test_feedback_hourly_limit(db_session):
    service = FeedbackService(db_session)
    for _ in range(HOURLY_LIMIT):
        await service.create(telegram_id=777, kind="idea", text="идея")
    with pytest.raises(FeedbackLimitError):
        await service.create(telegram_id=777, kind="idea", text="ещё")
    await service.create(telegram_id=778, kind="idea", text="другой человек")


def test_admin_feedback_text_lists_user_errors():
    from src.bot.handlers.feedback import format_feedback_for_admin

    item = SimpleNamespace(
        id=3, kind="bug", first_name="Аня", username="anya", telegram_id=555, created_at=datetime.now(timezone.utc),
        app_version="0.1.81-beta", status="new", text="Кнопка не работает", admin_reply=None,
    )
    event = SimpleNamespace(id=12, section="reminders", error_type="KeyError", count=2)
    text = format_feedback_for_admin(item, [event], "Europe/Moscow")
    assert "Обращение №3" in text and "@anya" in text and "№12 Напоминания — KeyError (2×)" in text


def test_feedback_and_admin_buttons_are_registered():
    from tests.test_callback_registration import _collect_application_callback_patterns, _is_registered

    patterns = _collect_application_callback_patterns()
    for callback in (
        "feedback_start", "fb_kind:bug", "fb_reply:1", "fb_read:1",
        "settings_errors", "settings_error:1", "settings_error_resolve:1", "settings_errors_resolve_all",
        "settings_feedback_list", "settings_feedback:1",
        "settings_broadcast", "bc_pick:0", "bc_toggle:5:0", "bc_select_new:0", "bc_clear:1",
        "bc_confirm:me", "bc_confirm:new", "bc_confirm:sel", "bc_send:me", "bc_send:new", "bc_send:sel",
    ):
        assert _is_registered(callback, patterns), callback


def test_admin_buttons_only_for_admin():
    from src.bot.keyboards import get_about_keyboard, get_settings_keyboard

    def callbacks(markup):
        return {button.callback_data for row in markup.inline_keyboard for button in row}

    assert "feedback_start" in callbacks(get_settings_keyboard())
    assert "settings_errors" not in callbacks(get_about_keyboard())
    assert {"settings_errors", "settings_feedback_list", "settings_broadcast"} <= callbacks(get_about_keyboard(is_admin=True))
    assert "settings_broadcast" not in callbacks(get_about_keyboard())


@pytest.mark.asyncio
async def test_admin_screens_refuse_regular_users(monkeypatch):
    from src.bot.handlers import feedback as feedback_handlers

    async def not_admin(_telegram_id):
        return False

    monkeypatch.setattr(feedback_handlers, "_is_admin", not_admin)
    edits = []

    class Query:
        data = "settings_errors"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, text, reply_markup=None):
            edits.append(text)

    update = SimpleNamespace(callback_query=Query(), effective_user=SimpleNamespace(id=1))
    await feedback_handlers.admin_errors_callback(update, SimpleNamespace(user_data={}))
    await feedback_handlers.admin_feedback_list_callback(update, SimpleNamespace(user_data={}))
    assert all("только администратору" in text for text in edits) and len(edits) == 2


# --- Admin API and announcement ----------------------------------------------

@pytest.mark.asyncio
async def test_admin_api_lists_and_resolves_errors_and_feedback(db_session):
    from src.api.app import create_application
    from src.config import settings
    from src.db.session import get_db

    exc = _raise(ZeroDivisionError("division by zero"))
    await store_errors(db_session, [capture_record(_record(exc=exc, error_context="Кнопка: <b>x</b>"), "bot")])
    await FeedbackService(db_session).create(telegram_id=1, kind="idea", text="Добавить тёмную тему")
    await db_session.flush()

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    headers = {"X-Admin-Token": settings.ADMIN_TOKEN}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/admin/errors")).status_code in (401, 403, 422)
        errors = (await client.get("/admin/errors", headers=headers)).json()
        event_id = errors["errors"][0]["id"]
        detail = (await client.get(f"/admin/errors/{event_id}", headers=headers)).json()
        resolved = await client.post(f"/admin/errors/{event_id}/resolve", headers=headers)
        after = (await client.get("/admin/errors", headers=headers)).json()
        feedback = (await client.get("/admin/feedback", headers=headers)).json()
        marked = await client.post(
            f"/admin/feedback/{feedback['feedback'][0]['id']}/status", headers=headers, json={"status": "read"}
        )
        ui = (await client.get("/admin/ui")).text

    assert errors["summary"]["open_kinds"] == 1
    assert detail["error_type"] == "ZeroDivisionError" and "Traceback" in detail["traceback"]
    assert resolved.status_code == 200 and after["errors"] == []
    assert feedback["new"] == 1 and feedback["feedback"][0]["text"] == "Добавить тёмную тему"
    assert marked.status_code == 200
    assert "Журнал ошибок" in ui and "Обращения пользователей" in ui and "function esc" in ui


def test_announcement_mentions_testing_version_and_feedback():
    from src.services.announcements import ANNOUNCEMENT_ID, announcement_text

    text = announcement_text("0.1.81-beta")
    assert ANNOUNCEMENT_ID
    assert "режиме тестирования" in text and "0.1.81-beta" in text and "/feedback" in text
    assert len(text) < 4096


# --- Announcement: sent only by the admin, to chosen people -------------------

class _Bot:
    def __init__(self, blocked=()):
        self.sent = []
        self.blocked = set(blocked)

    async def send_message(self, chat_id, text, reply_markup=None):
        from telegram.error import Forbidden

        if chat_id in self.blocked:
            raise Forbidden("bot was blocked by the user")
        self.sent.append(chat_id)


@pytest.mark.asyncio
async def test_announcement_is_sent_once_and_test_send_is_not_counted():
    from src.services.announcements import delivered_telegram_ids, send_announcement

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    bot = _Bot(blocked={3})

    test_send = await send_announcement(bot, [(1, None)], maker, text="t", record=False, pause_seconds=0)
    async with maker() as session:
        assert await delivered_telegram_ids(session) == set()

    result = await send_announcement(bot, [(1, None), (2, None), (3, None)], maker, text="t", pause_seconds=0)
    async with maker() as session:
        delivered = await delivered_telegram_ids(session)
    await engine.dispose()

    assert test_send.sent == 1
    assert (result.sent, result.blocked, result.failed) == (2, 1, 0)
    assert delivered == {1, 2}


def test_bot_startup_no_longer_broadcasts_automatically():
    import inspect

    import src.main as main_module

    assert "send_announcement" not in inspect.getsource(main_module.run_bot)
    assert not hasattr(main_module, "_send_one_time_announcement")


@pytest.mark.asyncio
async def test_broadcast_screens_refuse_regular_users(monkeypatch):
    from src.bot.handlers import broadcast

    async def not_admin(_telegram_id):
        return False

    monkeypatch.setattr(broadcast, "_is_admin", not_admin)
    edits = []

    class Query:
        data = "bc_send:new"

        async def answer(self, *args, **kwargs):
            pass

        async def edit_message_text(self, text, reply_markup=None):
            edits.append(text)

    update = SimpleNamespace(callback_query=Query(), effective_user=SimpleNamespace(id=1))
    await broadcast.broadcast_send_callback(update, SimpleNamespace(user_data={}, bot=_Bot()))
    assert edits and "только администратору" in edits[0]
