"""Web login token service."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config import settings
from src.db.models import User, WebLoginToken
from src.utils.public_url import normalize_public_base_url


@dataclass(frozen=True)
class WebLoginKey:
    """Raw login key returned only once to the user."""

    token: str
    url: str | None
    expires_at_utc: datetime


class WebAuthService:
    """Create and verify hashed access keys for the web client."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a raw access token before storing or comparing it."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def build_login_url(token: str) -> str | None:
        """Build a clickable web login URL when a public base URL is configured."""
        base_url = normalize_public_base_url(settings.WEB_PUBLIC_URL or settings.APP_BASE_URL)
        if not base_url:
            return None
        return f"{base_url}/web?token={quote(token)}"

    async def create_login_key(self, user_id: int, ttl_days: int | None = None) -> WebLoginKey:
        """Issue a new active web key and invalidate older active keys for this user."""
        ttl = ttl_days if ttl_days is not None else settings.WEB_LOGIN_TOKEN_TTL_DAYS
        expires_at = datetime.now(timezone.utc) + timedelta(days=max(ttl, 1))
        token = secrets.token_urlsafe(32)

        await self.db.execute(
            update(WebLoginToken)
            .where(WebLoginToken.user_id == user_id, WebLoginToken.is_active.is_(True))
            .values(is_active=False)
        )

        self.db.add(
            WebLoginToken(
                user_id=user_id,
                token_hash=self.hash_token(token),
                expires_at_utc=expires_at,
            )
        )
        await self.db.flush()
        return WebLoginKey(
            token=token,
            url=self.build_login_url(token),
            expires_at_utc=expires_at,
        )

    async def authenticate(self, token: str | None) -> User | None:
        """Return the token owner if the key is active and not expired."""
        if not token:
            return None

        now = datetime.now(timezone.utc)
        query = (
            select(WebLoginToken)
            .options(selectinload(WebLoginToken.user))
            .where(
                WebLoginToken.token_hash == self.hash_token(token.strip()),
                WebLoginToken.is_active.is_(True),
            )
        )
        result = await self.db.execute(query)
        login_token = result.scalar_one_or_none()
        if not login_token:
            return None

        expires_at = login_token.expires_at_utc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            login_token.is_active = False
            await self.db.flush()
            return None

        login_token.last_used_at_utc = now
        login_token.use_count += 1
        await self.db.flush()
        return login_token.user
