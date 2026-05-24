"""Telegram WebApp user authentication for user-scoped API routes."""

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import User
from src.db.session import get_db
from src.repositories.user_repo import UserRepository


class TelegramAuthData(dict):
    """Validated Telegram auth payload."""


def verify_telegram_webapp_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> TelegramAuthData:
    """Validate Telegram WebApp initData and return decoded user data."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing Telegram auth hash")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram auth hash")

    auth_date_raw = params.get("auth_date")
    if not auth_date_raw or not auth_date_raw.isdigit():
        raise ValueError("Missing Telegram auth date")
    auth_date = int(auth_date_raw)
    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise ValueError("Telegram auth data expired")

    raw_user = params.get("user")
    if not raw_user:
        raise ValueError("Missing Telegram user")
    user = json.loads(raw_user)
    if not isinstance(user, dict) or not user.get("id"):
        raise ValueError("Invalid Telegram user")

    payload: dict[str, Any] = dict(params)
    payload["user"] = user
    return TelegramAuthData(payload)


async def get_current_web_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve current user from validated Telegram WebApp initData."""
    try:
        auth_data = verify_telegram_webapp_init_data(
            x_telegram_init_data,
            settings.BOT_TOKEN,
            max_age_seconds=settings.USER_AUTH_MAX_AGE_SECONDS,
        )
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram WebApp auth data",
        ) from None

    telegram_user = auth_data["user"]
    repo = UserRepository(db)
    user = await repo.get_or_create(
        telegram_id=int(telegram_user["id"]),
        username=telegram_user.get("username"),
        first_name=telegram_user.get("first_name"),
        last_name=telegram_user.get("last_name"),
    )
    await db.commit()
    return user
