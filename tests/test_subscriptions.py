"""Subscription service tests."""

import pytest

from src.db.models import User, UserSubscription
from src.services.subscription_service import SubscriptionService


@pytest.mark.asyncio
async def test_subscription_service_returns_default_free_plan(db_session):
    """Users should get a default access context for beta/debug phase."""
    user = User(telegram_id=9101, timezone="UTC")
    db_session.add(user)
    await db_session.flush()

    service = SubscriptionService(db_session)
    context = await service.get_access_context(user.id)

    assert context["plan"] == "free"
    assert context["subscription_status"] == "active"
    assert "lists" in context["features"]
    assert "shared_lists" in context["features"]
    assert "medications" in context["features"]


@pytest.mark.asyncio
async def test_subscription_service_admin_gets_pro_access(db_session):
    """Admin users should bypass paid feature gates for support/debug."""
    admin = User(telegram_id=9102, timezone="UTC", is_admin=True)
    db_session.add(admin)
    await db_session.flush()

    service = SubscriptionService(db_session)
    context = await service.get_access_context(admin.id)

    assert context["is_admin"] is True
    assert context["plan"] == "pro"
    assert "exports" in context["features"]


@pytest.mark.asyncio
async def test_subscription_service_uses_existing_active_subscription(db_session):
    """Paid plan records should define effective access."""
    user = User(telegram_id=9103, timezone="UTC")
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserSubscription(user_id=user.id, plan_code="plus", status="active"))
    await db_session.flush()

    service = SubscriptionService(db_session)
    context = await service.get_access_context(user.id)

    assert context["plan"] == "plus"
    assert "priority_support" in context["features"]
