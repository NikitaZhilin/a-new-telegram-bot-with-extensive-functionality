"""Error journal: every logged error is stored for the admin.

How it works:
* ``install_error_journal(service)`` adds a logging handler to the process.
  Any ``logger.error`` / ``logger.exception`` / unhandled exception that reaches
  logging (bot handlers, the reminder worker, FastAPI, python-telegram-bot
  internals) is captured.
* Records are queued in memory and written to ``error_events`` by a background
  task, so logging never waits for the database.
* Errors are grouped by kind: the same exception type at the same code place is
  one row whose ``count`` grows. A resolved error that happens again reopens.

The admin sees the journal in the bot (Настройки → О боте → Журнал ошибок) and
on /admin/ui. Message texts typed by users are never stored by this module.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import traceback as traceback_module
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ErrorEvent

SECTION_LABELS: dict[str, str] = {
    "reminders": "Напоминания",
    "notes": "Заметки",
    "medications": "Лекарства",
    "lists": "Списки",
    "checklists": "Чек-листы",
    "driver": "Автомобиль",
    "settings": "Настройки",
    "navigation": "Меню и навигация",
    "web": "Веб-кабинет",
    "api": "API и админка",
    "worker": "Рассылка напоминаний",
    "telegram": "Связь с Telegram",
    "database": "База данных",
    "feedback": "Обратная связь",
    "other": "Прочее",
}
SERVICE_LABELS = {"bot": "бот", "worker": "воркер", "api": "api"}

# Name fragments of modules / callback prefixes → section.
_MODULE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("reminder", "reminders"),
    ("note", "notes"),
    ("medication", "medications"),
    ("checklist", "checklists"),
    ("list", "lists"),
    ("driver", "driver"),
    ("vehicle", "driver"),
    ("settings", "settings"),
    ("subscription", "settings"),
    ("timezone", "settings"),
    ("web_auth", "web"),
    ("navigation", "navigation"),
    ("free_text", "navigation"),
    ("conversation_exit", "navigation"),
    ("feedback", "feedback"),
    ("error_journal", "api"),
)
_CALLBACK_SECTIONS: tuple[tuple[str, str], ...] = (
    ("fb_", "feedback"),
    ("feedback", "feedback"),
    ("settings_error", "settings"),
    ("rem", "reminders"),
    ("free_reminder", "reminders"),
    ("note", "notes"),
    ("free_note", "notes"),
    ("med", "medications"),
    ("checklist", "checklists"),
    ("chk", "checklists"),
    ("list", "lists"),
    ("item", "lists"),
    ("drv", "driver"),
    ("driver", "driver"),
    ("settings", "settings"),
    ("tz_", "settings"),
    ("home", "navigation"),
    ("back", "navigation"),
    ("menu", "navigation"),
)

# Loggers whose errors must not be journaled (would loop or are pure noise).
_IGNORED_LOGGERS = ("src.services.error_journal", "sqlalchemy", "asyncpg", "aiosqlite")

MAX_MESSAGE = 1000
MAX_TRACEBACK = 6000
MAX_CONTEXT = 300
QUEUE_LIMIT = 500
FLUSH_INTERVAL_SECONDS = 3.0
RETENTION_DAYS = 90
CLEANUP_EVERY = timedelta(hours=6)


@dataclass
class CapturedError:
    """Everything needed to store one error, taken at the moment it was logged."""

    service: str
    section: str
    error_type: str
    message: str
    location: Optional[str]
    context: Optional[str]
    traceback: Optional[str]
    telegram_id: Optional[int]
    fingerprint: str
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _section_from_name(name: str) -> Optional[str]:
    lowered = name.lower()
    for fragment, section in _MODULE_SECTIONS:
        if fragment in lowered:
            return section
    return None


def section_from_callback(data: Optional[str]) -> Optional[str]:
    if not data:
        return None
    lowered = data.lower()
    for prefix, section in _CALLBACK_SECTIONS:
        if lowered.startswith(prefix):
            return section
    return None


def _section_from_path(path: str) -> Optional[str]:
    parts = PurePath(path).parts
    if "src" not in parts:
        return None
    rel = parts[parts.index("src") + 1:]
    if not rel:
        return None
    if rel[0] == "worker":
        return "worker"
    if rel[0] == "api":
        name = rel[-1]
        if name in ("web.py", "me.py", "user_auth.py"):
            return "web"
        return "api"
    if rel[0] in ("bot", "services", "repositories"):
        return _section_from_name("/".join(rel[1:]))
    return None


def _src_frames(tb) -> list[traceback_module.FrameSummary]:
    frames = traceback_module.extract_tb(tb) if tb is not None else []
    return [frame for frame in frames if "/src/" in frame.filename.replace("\\", "/")]


def _short_path(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    index = normalized.rfind("/src/")
    return normalized[index + 1:] if index >= 0 else PurePath(filename).name


def detect_section(
    *,
    service: str,
    exc: Optional[BaseException],
    logger_name: str,
    callback_data: Optional[str] = None,
    explicit: Optional[str] = None,
) -> str:
    """Pick the bot section the error belongs to."""
    if explicit in SECTION_LABELS:
        return explicit
    if exc is not None:
        module = type(exc).__module__ or ""
        if module.startswith("telegram") and type(exc).__name__ in ("NetworkError", "TimedOut", "Conflict"):
            return "telegram"
        if module.startswith(("sqlalchemy", "asyncpg")):
            if type(exc).__name__ in ("OperationalError", "InterfaceError", "ConnectionDoesNotExistError"):
                return "database"
        for frame in reversed(_src_frames(exc.__traceback__)):
            section = _section_from_path(frame.filename)
            if section:
                return section
    section = section_from_callback(callback_data)
    if section:
        return section
    if logger_name.startswith("src."):
        section = _section_from_path("/" + logger_name.replace(".", "/") + ".py")
        if section:
            return section
    if logger_name.startswith("telegram"):
        return "telegram"
    if service == "worker":
        return "worker"
    if service == "api" or logger_name.startswith("uvicorn"):
        return "api"
    return "other"


def _location(exc: Optional[BaseException], record: logging.LogRecord) -> str:
    if exc is not None and exc.__traceback__ is not None:
        frames = _src_frames(exc.__traceback__) or traceback_module.extract_tb(exc.__traceback__)
        if frames:
            frame = frames[-1]
            return f"{_short_path(frame.filename)}:{frame.lineno} in {frame.name}"[:200]
    return f"{_short_path(record.pathname)}:{record.lineno} in {record.funcName}"[:200]


def fingerprint_for(service: str, error_type: str, location: str, template: str = "") -> str:
    raw = f"{service}|{error_type}|{location}|{template[:200]}"
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()


_STRUCTLOG_NOISE = {"timestamp", "level", "logger", "event"}


def _plain_log_text(text: str) -> tuple[str, Optional[str]]:
    """structlog renders JSON with a timestamp; keep the event and fields only."""
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return text, None
    try:
        data = json.loads(stripped)
    except ValueError:
        return text, None
    if not isinstance(data, dict) or "event" not in data:
        return text, None
    event = str(data.get("event"))
    extras = ", ".join(f"{key}={value}" for key, value in data.items() if key not in _STRUCTLOG_NOISE)
    return (f"{event} ({extras})" if extras else event), event


def _infer_service(record: logging.LogRecord, exc: Optional[BaseException]) -> str:
    """For ``python -m src.main all``: tell bot / worker / api apart by code place."""
    names = [record.name or ""]
    if exc is not None:
        names += [frame.filename.replace("\\", "/") for frame in _src_frames(exc.__traceback__)]
    joined = " ".join(names)
    if "src.worker" in joined or "/src/worker/" in joined:
        return "worker"
    if "src.api" in joined or "/src/api/" in joined or (record.name or "").startswith("uvicorn"):
        return "api"
    return "bot"


def capture_record(record: logging.LogRecord, service: str) -> CapturedError:
    """Turn a log record into a ``CapturedError``. Never raises."""
    exc: Optional[BaseException] = None
    if record.exc_info and record.exc_info[1] is not None:
        exc = record.exc_info[1]
    if service == "all":
        service = _infer_service(record, exc)

    try:
        logged = record.getMessage()
    except Exception:
        logged = str(record.msg)
    logged, event_name = _plain_log_text(logged)
    if exc is not None:
        error_type = type(exc).__name__
        exc_text = str(exc)
        message = exc_text if not logged or logged == exc_text else f"{logged}: {exc_text}"
        tb_text = "".join(traceback_module.format_exception(type(exc), exc, exc.__traceback__))
        template = ""
    else:
        error_type = f"log:{record.levelname}"
        message = logged
        tb_text = None
        template = event_name or str(record.msg)

    location = _location(exc, record)
    callback_data = getattr(record, "callback_data", None)
    section = detect_section(
        service=service,
        exc=exc,
        logger_name=record.name or "",
        callback_data=callback_data,
        explicit=getattr(record, "error_section", None),
    )
    context = getattr(record, "error_context", None)
    if not context and record.name and not record.name.startswith("src."):
        context = f"logger {record.name}"
    telegram_id = getattr(record, "telegram_id", None)
    return CapturedError(
        service=service,
        section=section,
        error_type=error_type[:120],
        message=(message or "")[:MAX_MESSAGE],
        location=location,
        context=context[:MAX_CONTEXT] if context else None,
        traceback=tb_text[-MAX_TRACEBACK:] if tb_text else None,
        telegram_id=int(telegram_id) if isinstance(telegram_id, int) else None,
        fingerprint=fingerprint_for(service, error_type, location, template),
    )


async def store_errors(session: AsyncSession, errors: Iterable[CapturedError]) -> int:
    """Insert new kinds of errors or bump the counter of known ones."""
    stored = 0
    for item in errors:
        event = (
            await session.execute(select(ErrorEvent).where(ErrorEvent.fingerprint == item.fingerprint))
        ).scalar_one_or_none()
        if event is None:
            session.add(
                ErrorEvent(
                    fingerprint=item.fingerprint,
                    service=item.service,
                    section=item.section,
                    error_type=item.error_type,
                    message=item.message,
                    location=item.location,
                    context=item.context,
                    traceback=item.traceback,
                    telegram_id=item.telegram_id,
                    count=1,
                    first_seen_at=item.seen_at,
                    last_seen_at=item.seen_at,
                )
            )
            await session.flush()
        else:
            event.count = (event.count or 0) + 1
            event.last_seen_at = item.seen_at
            event.message = item.message
            event.context = item.context or event.context
            event.traceback = item.traceback or event.traceback
            event.telegram_id = item.telegram_id or event.telegram_id
            event.section = item.section
            event.resolved_at = None
        stored += 1
    return stored


class ErrorJournalHandler(logging.Handler):
    """Logging handler that queues ERROR records and writes them in the background."""

    def __init__(self, service: str, session_factory=None) -> None:
        super().__init__(level=logging.ERROR)
        self.service = service
        self._session_factory = session_factory
        self._queue: deque[CapturedError] = deque(maxlen=QUEUE_LIMIT)
        self._task: Optional[asyncio.Task] = None
        self._last_cleanup: Optional[datetime] = None

    # -- logging side ---------------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith(_IGNORED_LOGGERS) or getattr(record, "skip_error_journal", False):
            return
        exc = record.exc_info[1] if record.exc_info else None
        if exc is not None and getattr(exc, "__error_journaled__", False):
            return  # the same exception logged again higher up (e.g. by uvicorn)
        try:
            self._queue.append(capture_record(record, self.service))
            if exc is not None:
                try:
                    exc.__error_journaled__ = True
                except Exception:
                    pass
            self.ensure_started()
        except Exception:
            # Logging must never break the caller.
            print("error journal: could not capture record", file=sys.stderr)

    # -- background writer ----------------------------------------------------
    def ensure_started(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is None or self._task.done() or self._task.get_loop() is not loop:
            self._task = loop.create_task(self._run(), name=f"error-journal-{self.service}")

    def _factory(self):
        if self._session_factory is None:
            from src.db.session import async_session_maker

            self._session_factory = async_session_maker
        return self._session_factory

    async def flush(self) -> int:
        if not self._queue:
            return 0
        batch: list[CapturedError] = []
        while self._queue:
            batch.append(self._queue.popleft())
        try:
            async with self._factory()() as session:
                stored = await store_errors(session, batch)
                await self._maybe_cleanup(session)
                await session.commit()
                return stored
        except Exception as exc:  # database down: keep the newest records for the next try
            for item in batch[-50:]:
                self._queue.appendleft(item)
            print(f"error journal: could not save errors: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 0

    async def _maybe_cleanup(self, session: AsyncSession) -> None:
        now = datetime.now(timezone.utc)
        if self._last_cleanup and now - self._last_cleanup < CLEANUP_EVERY:
            return
        self._last_cleanup = now
        await session.execute(
            delete(ErrorEvent).where(ErrorEvent.last_seen_at < now - timedelta(days=RETENTION_DAYS))
        )

    async def _run(self) -> None:
        try:
            while True:
                await self.flush()
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            await self.flush()
            raise


_installed: Optional[ErrorJournalHandler] = None


def install_error_journal(service: str) -> ErrorJournalHandler:
    """Attach the journal to the root logger (and uvicorn, which does not propagate)."""
    global _installed
    if _installed is not None:
        return _installed
    handler = ErrorJournalHandler(service)
    logging.getLogger().addHandler(handler)
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.addHandler(handler)
    _installed = handler
    return handler


def current_journal() -> Optional[ErrorJournalHandler]:
    return _installed


async def start_error_journal() -> None:
    """Start the background writer in the running loop (safe to call many times)."""
    if _installed is not None:
        _installed.ensure_started()


async def flush_error_journal() -> None:
    """Write queued errors now, e.g. right before the process exits."""
    if _installed is not None:
        await _installed.flush()


# --- Reading side (admin API and bot screen) ---------------------------------

class ErrorJournalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_events(
        self,
        *,
        days: int = 30,
        section: Optional[str] = None,
        service: Optional[str] = None,
        include_resolved: bool = False,
        limit: int = 100,
    ) -> list[ErrorEvent]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = select(ErrorEvent).where(ErrorEvent.last_seen_at >= since)
        if section:
            query = query.where(ErrorEvent.section == section)
        if service:
            query = query.where(ErrorEvent.service == service)
        if not include_resolved:
            query = query.where(ErrorEvent.resolved_at.is_(None))
        query = query.order_by(ErrorEvent.last_seen_at.desc()).limit(limit)
        return list((await self.session.execute(query)).scalars().all())

    async def get(self, event_id: int) -> Optional[ErrorEvent]:
        return await self.session.get(ErrorEvent, event_id)

    async def resolve(self, event_id: int) -> bool:
        event = await self.get(event_id)
        if event is None:
            return False
        event.resolved_at = datetime.now(timezone.utc)
        await self.session.flush()
        return True

    async def resolve_all(self) -> int:
        result = await self.session.execute(
            update(ErrorEvent)
            .where(ErrorEvent.resolved_at.is_(None))
            .values(resolved_at=datetime.now(timezone.utc))
        )
        await self.session.flush()
        return result.rowcount or 0

    async def summary(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        open_kinds = await self.session.scalar(
            select(func.count()).select_from(ErrorEvent).where(ErrorEvent.resolved_at.is_(None))
        )
        last_24h = await self.session.scalar(
            select(func.count())
            .select_from(ErrorEvent)
            .where(ErrorEvent.last_seen_at >= now - timedelta(hours=24))
        )
        by_section_rows = await self.session.execute(
            select(ErrorEvent.section, func.count(), func.sum(ErrorEvent.count))
            .where(ErrorEvent.resolved_at.is_(None))
            .group_by(ErrorEvent.section)
        )
        by_section = [
            {"section": row[0], "label": SECTION_LABELS.get(row[0], row[0]), "kinds": row[1], "occurrences": int(row[2] or 0)}
            for row in by_section_rows.all()
        ]
        by_section.sort(key=lambda item: item["occurrences"], reverse=True)
        return {"open_kinds": int(open_kinds or 0), "kinds_seen_24h": int(last_24h or 0), "by_section": by_section}
