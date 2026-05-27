"""Runtime heartbeat writers and admin status aggregation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import BotActivityEvent, ServiceHeartbeat
from src.db.session import async_session_maker

logger = logging.getLogger(__name__)

HEARTBEAT_DOWN_AFTER_SECONDS = 120
REQUIRED_SERVICE_NAMES = ("api", "bot", "worker")
VALID_HEARTBEAT_STATUSES = {"ok", "degraded", "down"}


def utc_now() -> datetime:
    """Return current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Normalize database datetimes to aware UTC values."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ServiceHeartbeatWriter:
    """Periodically write one runtime process heartbeat to the database."""

    def __init__(
        self,
        service_name: str,
        *,
        version: str | None = None,
        interval_seconds: int | None = None,
        metadata_factory: Callable[[], dict[str, Any]] | None = None,
        session_factory=async_session_maker,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.service_name = service_name[:60]
        self.version = (version or settings.APP_VERSION)[:80]
        self.interval_seconds = interval_seconds or settings.SERVICE_HEARTBEAT_INTERVAL_SECONDS
        self.metadata_factory = metadata_factory
        self.session_factory = session_factory
        self.clock = clock
        self.started_at = ensure_utc(clock()) or utc_now()
        self.status = "ok"
        self.last_error: str | None = None
        self._running = False

    def mark_ok(self) -> None:
        """Mark the next heartbeat as healthy."""
        self.status = "ok"
        self.last_error = None

    def mark_degraded(self, error: str | None = None) -> None:
        """Mark the next heartbeat as degraded and store a safe error summary."""
        self.status = "degraded"
        if error:
            self.last_error = str(error)[:1000]

    async def write_once(self) -> None:
        """Write the current heartbeat state once."""
        now = ensure_utc(self.clock()) or utc_now()
        uptime_seconds = max(int((now - self.started_at).total_seconds()), 0)
        metadata = self._safe_metadata()

        async with self.session_factory() as session:
            await upsert_service_heartbeat(
                session,
                service_name=self.service_name,
                status=self.status,
                version=self.version,
                started_at=self.started_at,
                last_seen_at=now,
                uptime_seconds=uptime_seconds,
                last_error=self.last_error,
                metadata_json=metadata,
            )
            await session.commit()

    async def run(self) -> None:
        """Run heartbeat loop until cancelled or stopped."""
        self._running = True
        while self._running:
            try:
                await self.write_once()
            except asyncio.CancelledError:
                self._running = False
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to write service heartbeat",
                    extra={"service_name": self.service_name, "error": str(exc)},
                    exc_info=True,
                )
            await asyncio.sleep(max(int(self.interval_seconds), 1))

    def stop(self) -> None:
        """Ask the heartbeat loop to stop."""
        self._running = False

    def _safe_metadata(self) -> dict[str, Any]:
        if not self.metadata_factory:
            return {}
        try:
            metadata = self.metadata_factory()
        except Exception as exc:
            self.mark_degraded(f"metadata error: {exc}")
            return {"metadata_error": str(exc)[:300]}
        return metadata if isinstance(metadata, dict) else {"value": str(metadata)[:300]}


async def upsert_service_heartbeat(
    db: AsyncSession,
    *,
    service_name: str,
    status: str,
    version: str,
    started_at: datetime,
    last_seen_at: datetime,
    uptime_seconds: int,
    last_error: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ServiceHeartbeat:
    """Insert or update one heartbeat row."""
    normalized_status = status if status in VALID_HEARTBEAT_STATUSES else "degraded"
    result = await db.execute(
        select(ServiceHeartbeat).where(ServiceHeartbeat.service_name == service_name)
    )
    heartbeat = result.scalar_one_or_none()
    if heartbeat is None:
        heartbeat = ServiceHeartbeat(service_name=service_name)
        db.add(heartbeat)

    heartbeat.status = normalized_status
    heartbeat.version = version[:80]
    heartbeat.started_at = ensure_utc(started_at) or utc_now()
    heartbeat.last_seen_at = ensure_utc(last_seen_at) or utc_now()
    heartbeat.uptime_seconds = max(int(uptime_seconds), 0)
    heartbeat.last_error = last_error[:1000] if last_error else None
    heartbeat.metadata_json = metadata_json or None
    await db.flush()
    return heartbeat


class ServiceStatusService:
    """Build read-only service status payloads for admin/status bots."""

    def __init__(self, db: AsyncSession, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.db = db
        self.clock = clock

    async def get_status(self) -> dict[str, Any]:
        """Return combined heartbeat, database, version, and error status."""
        now = ensure_utc(self.clock()) or utc_now()
        heartbeats_result = await self.db.execute(select(ServiceHeartbeat))
        heartbeats = list(heartbeats_result.scalars().all())
        rows_by_name = {row.service_name: row for row in heartbeats}
        service_names = list(REQUIRED_SERVICE_NAMES)
        service_names.extend(
            sorted(name for name in rows_by_name if name not in REQUIRED_SERVICE_NAMES)
        )

        db_status = await self._database_status()
        recent_errors_count = await self._recent_errors_count(now)
        services = {
            name: self._format_service(row=rows_by_name.get(name), service_name=name, now=now)
            for name in service_names
        }
        heartbeat_errors_count = sum(1 for service in services.values() if service["last_error"])
        last_errors_count = recent_errors_count + heartbeat_errors_count
        overall_status = self._overall_status(services, db_status, last_errors_count)

        return {
            "status": overall_status,
            "version": settings.APP_VERSION,
            "generated_at": now.isoformat(),
            "database": db_status["status"],
            "last_errors_count": last_errors_count,
            "heartbeat_down_after_seconds": HEARTBEAT_DOWN_AFTER_SECONDS,
            "services": services,
        }

    async def _database_status(self) -> dict[str, Any]:
        try:
            await self.db.execute(text("SELECT 1"))
            return {"status": "ok", "last_error": None}
        except Exception as exc:
            return {"status": "degraded", "last_error": str(exc)[:1000]}

    async def _recent_errors_count(self, now: datetime) -> int:
        since = now - timedelta(hours=24)
        result = await self.db.execute(
            select(func.count(BotActivityEvent.id)).where(
                BotActivityEvent.created_at >= since,
                or_(
                    BotActivityEvent.event_type.in_(("error", "critical_error")),
                    BotActivityEvent.event_name.ilike("%error%"),
                    BotActivityEvent.event_name.ilike("%critical%"),
                ),
            )
        )
        return int(result.scalar() or 0)

    def _format_service(
        self,
        *,
        row: ServiceHeartbeat | None,
        service_name: str,
        now: datetime,
    ) -> dict[str, Any]:
        required = service_name in REQUIRED_SERVICE_NAMES
        if row is None:
            status = "down" if required else "degraded"
            return {
                "service_name": service_name,
                "status": status,
                "reported_status": None,
                "required": required,
                "stale": True,
                "seconds_since_seen": None,
                "version": None,
                "started_at": None,
                "last_seen_at": None,
                "uptime_seconds": 0,
                "last_error": "heartbeat is missing",
                "metadata_json": {},
            }

        last_seen_at = ensure_utc(row.last_seen_at)
        seconds_since_seen = (
            int((now - last_seen_at).total_seconds())
            if last_seen_at
            else None
        )
        stale = seconds_since_seen is None or seconds_since_seen > HEARTBEAT_DOWN_AFTER_SECONDS
        if stale and required:
            status = "down"
        elif stale or row.status == "degraded" or row.last_error:
            status = "degraded"
        else:
            status = row.status if row.status in VALID_HEARTBEAT_STATUSES else "degraded"

        return {
            "service_name": row.service_name,
            "status": status,
            "reported_status": row.status,
            "required": required,
            "stale": stale,
            "seconds_since_seen": seconds_since_seen,
            "version": row.version,
            "started_at": (ensure_utc(row.started_at) or row.started_at).isoformat(),
            "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
            "uptime_seconds": row.uptime_seconds,
            "last_error": row.last_error,
            "metadata_json": row.metadata_json or {},
        }

    @staticmethod
    def _overall_status(
        services: dict[str, dict[str, Any]],
        db_status: dict[str, Any],
        recent_errors_count: int,
    ) -> str:
        if db_status["status"] != "ok":
            return "degraded"
        service_values = services.values()
        if any(service["required"] and service["status"] == "down" for service in service_values):
            return "down"
        if recent_errors_count > 0:
            return "degraded"
        if any(service["status"] == "degraded" for service in services.values()):
            return "degraded"
        return "ok"
