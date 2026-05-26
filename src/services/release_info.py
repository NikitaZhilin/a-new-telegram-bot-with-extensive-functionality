"""Release metadata and startup announcement policy."""

import base64
import binascii
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


STARTUP_UPDATE_FALLBACK_MESSAGE = "Можно продолжать пользоваться."
ANNOUNCE_MODES = {"off", "major", "always"}
ANNOUNCE_IMPORTANCE = {"minor", "major", "critical"}
ADMIN_ANNOUNCE_MODES = {"off", "once_per_version", "always"}
APP_STARTED_AT_UTC = datetime.now(timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def optional_release_change_lines(
    startup_message: str,
    startup_message_b64: str | None = None,
) -> list[str]:
    """Return changelog lines only when optional text is configured and valid."""
    encoded = (startup_message_b64 or "").strip()
    raw_message = (startup_message or "").strip()
    if not encoded and not raw_message:
        return []

    message = resolve_startup_update_message(raw_message, encoded)
    if message == STARTUP_UPDATE_FALLBACK_MESSAGE and (
        not raw_message or looks_like_broken_encoding(raw_message)
    ):
        return []
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


def normalize_admin_announce_mode(value: str | None) -> str:
    """Normalize admin-only startup notice mode."""
    normalized = (value or "once_per_version").strip().lower()
    return normalized if normalized in ADMIN_ANNOUNCE_MODES else "once_per_version"


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


def should_send_admin_startup_notice(config: Any) -> bool:
    """Return whether startup should send an admin-only technical notice."""
    return normalize_admin_announce_mode(
        getattr(config, "STARTUP_ADMIN_ANNOUNCE_MODE", "once_per_version")
    ) != "off"


def _display_timezone(config: Any) -> tuple[str, timezone | ZoneInfo]:
    """Return a configured timezone, falling back to UTC when invalid."""
    timezone_name = getattr(config, "TIMEZONE_DEFAULT", "UTC") or "UTC"
    try:
        return timezone_name, ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return "UTC", timezone.utc


def release_history(limit: int = 5, changelog_path: Path | None = None) -> list[dict]:
    """Read recent release notes from CHANGELOG.md."""
    path = changelog_path or PROJECT_ROOT / "CHANGELOG.md"
    if not path.exists():
        return []

    entries: list[dict] = []
    current: dict | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current:
                entries.append(current)
                if len(entries) >= limit:
                    break
            current = {"version": line.removeprefix("## ").strip(), "items": []}
            continue
        if current and line.startswith("- "):
            current["items"].append(line.removeprefix("- ").strip())

    if current and len(entries) < limit:
        entries.append(current)
    return entries[:limit]


def app_info(config: Any) -> dict:
    """Build public app/release metadata for Telegram and web UI."""
    timezone_name, display_timezone = _display_timezone(config)
    started_at_local = APP_STARTED_AT_UTC.astimezone(display_timezone)
    user_changes = release_change_lines(
        getattr(config, "STARTUP_UPDATE_MESSAGE", ""),
        getattr(config, "STARTUP_UPDATE_MESSAGE_B64", None),
    )
    technical_changes = optional_release_change_lines(
        getattr(config, "STARTUP_TECHNICAL_MESSAGE", ""),
        getattr(config, "STARTUP_TECHNICAL_MESSAGE_B64", None),
    )
    return {
        "version": getattr(config, "APP_VERSION", "0.1.0-beta"),
        "release_channel": getattr(config, "APP_RELEASE_CHANNEL", "beta"),
        "release_importance": normalize_release_importance(
            getattr(config, "STARTUP_ANNOUNCE_IMPORTANCE", "minor")
        ),
        "startup_announce_mode": normalize_announce_mode(
            getattr(config, "STARTUP_ANNOUNCE_MODE", "off")
        ),
        "startup_admin_announce_mode": normalize_admin_announce_mode(
            getattr(config, "STARTUP_ADMIN_ANNOUNCE_MODE", "once_per_version")
        ),
        "started_at_utc": APP_STARTED_AT_UTC,
        "started_at_local": started_at_local,
        "started_timezone": timezone_name,
        "started_at_display": started_at_local.strftime("%d.%m.%Y %H:%M"),
        "github_url": getattr(config, "APP_GITHUB_URL", "") or "",
        "changelog_url": getattr(config, "APP_CHANGELOG_URL", "") or "",
        "testing_notice_enabled": bool(getattr(config, "TESTING_NOTICE_ENABLED", True)),
        "testing_notice_text": getattr(config, "TESTING_NOTICE_TEXT", ""),
        "changes": user_changes,
        "user_changes": user_changes,
        "technical_changes": technical_changes,
        "release_history": release_history(),
    }
