"""Release metadata and startup announcement policy."""

import base64
import binascii
from typing import Any


STARTUP_UPDATE_FALLBACK_MESSAGE = "Можно продолжать пользоваться."
ANNOUNCE_MODES = {"off", "major", "always"}
ANNOUNCE_IMPORTANCE = {"minor", "major", "critical"}


def looks_like_broken_encoding(value: str) -> bool:
    """Detect strings that were replaced with question marks during deploy."""
    stripped = value.strip()
    return stripped.count("?") >= 5 and "???" in stripped


def resolve_startup_update_message(
    startup_message: str,
    startup_message_b64: str | None = None,
) -> str:
    """Return a safe UTF-8 startup changelog, preferring base64 when provided."""
    candidate = startup_message
    encoded = (startup_message_b64 or "").strip()
    if encoded:
        try:
            candidate = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            candidate = startup_message

    candidate = candidate.strip().strip("\"'").strip()
    if not candidate or looks_like_broken_encoding(candidate):
        return STARTUP_UPDATE_FALLBACK_MESSAGE
    return candidate


def release_change_lines(
    startup_message: str,
    startup_message_b64: str | None = None,
) -> list[str]:
    """Return clean changelog lines from env text."""
    message = resolve_startup_update_message(startup_message, startup_message_b64)
    return [
        line.strip().lstrip("-•").strip()
        for line in message.replace(";", "\n").splitlines()
        if line.strip()
    ]


def normalize_announce_mode(value: str | None) -> str:
    """Normalize announcement mode to a safe value."""
    normalized = (value or "off").strip().lower()
    return normalized if normalized in ANNOUNCE_MODES else "off"


def normalize_release_importance(value: str | None) -> str:
    """Normalize release importance to a safe value."""
    normalized = (value or "minor").strip().lower()
    return normalized if normalized in ANNOUNCE_IMPORTANCE else "minor"


def should_send_startup_announcement(config: Any) -> bool:
    """Return whether this startup should broadcast a release announcement."""
    if not getattr(config, "SEND_STARTUP_MENU_ON_BOOT", True):
        return False

    mode = normalize_announce_mode(getattr(config, "STARTUP_ANNOUNCE_MODE", "off"))
    importance = normalize_release_importance(
        getattr(config, "STARTUP_ANNOUNCE_IMPORTANCE", "minor")
    )
    if mode == "always":
        return True
    if mode == "major":
        return importance in {"major", "critical"}
    return False


def app_info(config: Any) -> dict:
    """Build public app/release metadata for Telegram and web UI."""
    return {
        "version": getattr(config, "APP_VERSION", "0.1.0-beta"),
        "release_channel": getattr(config, "APP_RELEASE_CHANNEL", "beta"),
        "release_importance": normalize_release_importance(
            getattr(config, "STARTUP_ANNOUNCE_IMPORTANCE", "minor")
        ),
        "github_url": getattr(config, "APP_GITHUB_URL", "") or "",
        "changelog_url": getattr(config, "APP_CHANGELOG_URL", "") or "",
        "testing_notice_enabled": bool(getattr(config, "TESTING_NOTICE_ENABLED", True)),
        "testing_notice_text": getattr(config, "TESTING_NOTICE_TEXT", ""),
        "changes": release_change_lines(
            getattr(config, "STARTUP_UPDATE_MESSAGE", ""),
            getattr(config, "STARTUP_UPDATE_MESSAGE_B64", None),
        ),
    }
