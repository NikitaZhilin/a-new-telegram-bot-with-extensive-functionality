"""Subscription and feature access service."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import User, UserSubscription


@dataclass(frozen=True)
class PlanDefinition:
    """Static subscription plan definition."""

    code: str
    title: str
    features: frozenset[str]
    limits: dict[str, int | None]


CORE_FEATURES = frozenset(
    {
        "lists",
        "shared_lists",
        "reminders",
        "medications",
    }
)

PLAN_DEFINITIONS: dict[str, PlanDefinition] = {
    "free": PlanDefinition(
        code="free",
        title="Базовый",
        features=CORE_FEATURES,
        limits={
            "lists": None,
            "shared_list_members": None,
            "active_reminders": None,
            "medications": None,
        },
    ),
    "plus": PlanDefinition(
        code="plus",
        title="Plus",
        features=CORE_FEATURES | {"advanced_history", "priority_support"},
        limits={
            "lists": None,
            "shared_list_members": None,
            "active_reminders": None,
            "medications": None,
        },
    ),
    "pro": PlanDefinition(
        code="pro",
        title="Pro",
        features=CORE_FEATURES | {"advanced_history", "priority_support", "exports", "family_access"},
        limits={
            "lists": None,
            "shared_list_members": None,
            "active_reminders": None,
            "medications": None,
        },
    ),
}


class SubscriptionService:
    """Business logic for subscription state and feature gates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_subscription(self, user_id: int) -> Optional[UserSubscription]:
        """Return the active, non-expired subscription for a user."""
        now = datetime.now(timezone.utc)
        query = (
            select(UserSubscription)
            .where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status == "active",
                )
            )
            .order_by(UserSubscription.created_at.desc(), UserSubscription.id.desc())
        )
        result = await self.db.execute(query)
        for subscription in result.scalars().all():
            expires_at = subscription.expires_at_utc
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at is None or expires_at > now:
                return subscription
        return None

    async def ensure_default_subscription(self, user_id: int) -> UserSubscription:
        """Create default subscription if user does not have an active one."""
        subscription = await self.get_active_subscription(user_id)
        if subscription:
            return subscription

        subscription = UserSubscription(
            user_id=user_id,
            plan_code=settings.DEFAULT_SUBSCRIPTION_PLAN,
            status="active",
        )
        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(subscription)
        return subscription

    async def get_plan_for_user(self, user_id: int) -> PlanDefinition:
        """Return effective plan for a user."""
        user = await self.db.get(User, user_id)
        if user and user.is_admin:
            return PLAN_DEFINITIONS["pro"]

        subscription = await self.ensure_default_subscription(user_id)
        return PLAN_DEFINITIONS.get(subscription.plan_code, PLAN_DEFINITIONS["free"])

    async def has_feature(self, user_id: int, feature: str) -> bool:
        """Check if a user has a feature in their effective plan."""
        plan = await self.get_plan_for_user(user_id)
        return feature in plan.features

    async def get_access_context(self, user_id: int) -> dict:
        """Return serializable access info for bot/admin diagnostics."""
        user = await self.db.get(User, user_id)
        plan = await self.get_plan_for_user(user_id)
        subscription = await self.get_active_subscription(user_id)
        return {
            "is_admin": bool(user and user.is_admin),
            "plan": plan.code,
            "plan_title": plan.title,
            "features": sorted(plan.features),
            "limits": plan.limits,
            "subscription_status": subscription.status if subscription else "inactive",
            "expires_at_utc": subscription.expires_at_utc.isoformat() if subscription and subscription.expires_at_utc else None,
        }
