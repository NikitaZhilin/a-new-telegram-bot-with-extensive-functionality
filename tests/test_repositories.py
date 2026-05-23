"""Repository tests."""

import pytest

from src.config import settings
from src.db.models import User
from src.repositories.list_repo import ListRepository
from src.repositories.user_repo import UserRepository

@pytest.mark.asyncio
async def test_list_repository_counts_lists_by_owner(db_session):
    """ListRepository should count only the requested user's lists."""
    user = User(telegram_id=3001, timezone="UTC")
    other_user = User(telegram_id=3002, timezone="UTC")
    db_session.add_all([user, other_user])
    await db_session.flush()

    repo = ListRepository(db_session)
    await repo.create({"user_id": user.id, "title": "First"})
    await repo.create({"user_id": user.id, "title": "Second"})
    await repo.create({"user_id": other_user.id, "title": "Hidden"})

    assert await repo.count_by_user(user.id) == 2
    assert await repo.count_by_user(other_user.id) == 1


@pytest.mark.asyncio
async def test_user_repo_marks_admin_and_creates_default_subscription(db_session, monkeypatch):
    """New users should be isolated regular users unless listed as admins."""
    monkeypatch.setattr(settings, "ADMIN_TELEGRAM_IDS", "9001, 9003")
    monkeypatch.setattr(settings, "DEFAULT_SUBSCRIPTION_PLAN", "free")

    repo = UserRepository(db_session)
    admin = await repo.get_or_create(telegram_id=9001, username="admin")
    regular = await repo.get_or_create(telegram_id=9002, username="user")

    assert admin.is_admin is True
    assert regular.is_admin is False
    assert admin.onboarding_source == "telegram_link"
    assert regular.subscriptions[0].plan_code == "free"
