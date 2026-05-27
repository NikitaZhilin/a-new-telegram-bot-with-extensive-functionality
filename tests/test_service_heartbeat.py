"""Service heartbeat and admin status tests."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.api.app import create_application
from src.config import settings
from src.db.session import get_db
from src.services.activity_service import ActivityService
from src.services.service_heartbeat import (
    HEARTBEAT_DOWN_AFTER_SECONDS,
    ServiceStatusService,
    upsert_service_heartbeat,
)


@pytest.mark.asyncio
async def test_service_status_marks_required_stale_heartbeat_down(db_session):
    """Required services are down when last_seen_at is older than two minutes."""
    now = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
    stale_seen_at = now - timedelta(seconds=HEARTBEAT_DOWN_AFTER_SECONDS + 1)

    await upsert_service_heartbeat(
        db_session,
        service_name="api",
        status="ok",
        version="0.1.0-beta",
        started_at=now - timedelta(hours=1),
        last_seen_at=stale_seen_at,
        uptime_seconds=3600,
    )
    await upsert_service_heartbeat(
        db_session,
        service_name="bot",
        status="ok",
        version="0.1.0-beta",
        started_at=now - timedelta(minutes=10),
        last_seen_at=now - timedelta(seconds=30),
        uptime_seconds=600,
    )
    await upsert_service_heartbeat(
        db_session,
        service_name="worker",
        status="degraded",
        version="0.1.0-beta",
        started_at=now - timedelta(minutes=10),
        last_seen_at=now - timedelta(seconds=30),
        uptime_seconds=600,
        last_error="last worker cycle failed",
    )
    await ActivityService(db_session).record_event(
        event_type="critical_error",
        event_name="critical_worker_error",
        domain="system",
        source="system",
    )

    payload = await ServiceStatusService(db_session, clock=lambda: now).get_status()
    services = {item["service_name"]: item for item in payload["services"]}

    assert payload["status"] == "down"
    assert payload["db"]["status"] == "ok"
    assert payload["last_errors_count"] == 2
    assert services["api"]["status"] == "down"
    assert services["api"]["stale"] is True
    assert services["bot"]["status"] == "ok"
    assert services["worker"]["status"] == "degraded"
    assert services["worker"]["last_error"] == "last worker cycle failed"


@pytest.mark.asyncio
async def test_admin_service_status_endpoint_is_token_protected(db_session):
    """Admin service-status returns heartbeat JSON only with X-Admin-Token."""
    now = datetime.now(timezone.utc)
    for service_name in ("api", "bot", "worker"):
        await upsert_service_heartbeat(
            db_session,
            service_name=service_name,
            status="ok",
            version=settings.APP_VERSION,
            started_at=now - timedelta(minutes=5),
            last_seen_at=now,
            uptime_seconds=300,
            metadata_json={"test": True},
        )

    app = create_application()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        rejected = await client.get("/admin/service-status")
        accepted = await client.get(
            "/admin/service-status",
            headers={"X-Admin-Token": settings.ADMIN_TOKEN},
        )

    assert rejected.status_code in {401, 403, 422}
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["status"] == "ok"
    assert payload["version"] == settings.APP_VERSION
    assert {item["service_name"] for item in payload["services"]} >= {"api", "bot", "worker"}
