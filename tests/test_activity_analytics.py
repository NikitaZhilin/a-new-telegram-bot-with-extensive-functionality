"""Tests for privacy-safe bot activity analytics."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db.models import User
from src.services.activity_service import (
    ActivityService,
    infer_domain,
    normalize_callback_data,
    normalize_menu_text,
)


def test_activity_normalizes_callback_data_without_row_ids_or_tokens():
    """Callback analytics should keep action names, not record private IDs/tokens."""
    assert normalize_callback_data("list_item_delete_confirm:12345") == "list_item_delete_confirm:{id}"
    assert normalize_callback_data("join_list:abcdef1234567890") == "join_list:{token}"
    assert infer_domain("driver_fuel_view:{id}") == "driver"
    assert infer_domain("list_share:{id}") == "sharing"


def test_activity_normalizes_menu_text():
    """Reply menu clicks should be grouped by stable action names."""
    assert normalize_menu_text("📋 Списки") == "menu:lists"
    assert normalize_menu_text("💊 Лекарства") == "menu:medications"
    assert normalize_menu_text("🚗 Для водителя") == "menu:driver"


@pytest.mark.asyncio
async def test_activity_summary_counts_top_domains_and_actions(db_session):
    """Admin summary should show recent usage without message contents."""
    admin = User(telegram_id=92001, timezone="UTC", is_admin=True)
    other = User(telegram_id=92002, timezone="UTC")
    db_session.add_all([admin, other])
    await db_session.flush()

    service = ActivityService(db_session)
    await service.record_event(
        user_id=admin.id,
        telegram_id=admin.telegram_id,
        event_type="callback",
        event_name="settings_stats",
        domain="settings",
    )
    await service.record_event(
        user_id=other.id,
        telegram_id=other.telegram_id,
        event_type="menu",
        event_name="menu:driver",
        domain="driver",
    )
    await service.record_event(
        user_id=other.id,
        telegram_id=other.telegram_id,
        event_type="callback",
        event_name="driver_fuel_add:{id}",
        domain="driver",
    )
    old_event = await service.record_event(
        user_id=other.id,
        telegram_id=other.telegram_id,
        event_type="callback",
        event_name="lists_list",
        domain="lists",
    )
    old_event.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db_session.flush()

    summary = await service.get_admin_event_summary(admin.id, days=7)

    assert summary["events_period"] == 3
    assert summary["events_24h"] == 3
    assert summary["active_other_users_period"] == 1
    assert summary["top_domains"][0]["domain"] == "driver"
    assert summary["top_domains"][0]["count"] == 2
    assert {item["event_name"] for item in summary["top_actions"]} >= {
        "menu:driver",
        "driver_fuel_add:{id}",
    }
