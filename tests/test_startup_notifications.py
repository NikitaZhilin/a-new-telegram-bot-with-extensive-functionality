"""Startup notification deduplication tests."""

import base64
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src import main
from src.db.base import Base
from src.services.release_info import optional_release_change_lines, release_history


@pytest.mark.asyncio
async def test_startup_update_marker_deduplicates_per_user_and_version(monkeypatch):
    """Startup update should be sent once per Telegram user per app version."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "async_session_maker", session_maker)

    telegram_id = 95001
    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.0-beta") is False

    await main._record_startup_update_sent(
        telegram_id=telegram_id,
        user_id=None,
        app_version="0.8.0-beta",
    )

    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.0-beta") is True
    assert await main._startup_update_sent(telegram_id=telegram_id, app_version="0.8.1-beta") is False
    assert await main._startup_update_sent(telegram_id=telegram_id + 1, app_version="0.8.0-beta") is False

    await engine.dispose()


def test_startup_update_message_prefers_base64_utf8():
    message = "Добавлены напоминания по документам водителя;Улучшена web-версия"
    encoded = base64.b64encode(message.encode("utf-8")).decode("ascii")

    assert main._resolve_startup_update_message("?????????", encoded) == message


def test_startup_update_message_rejects_question_mark_mojibake():
    assert (
        main._resolve_startup_update_message("????????? ??????????? ?? ?????????? ????????")
        == main.STARTUP_UPDATE_FALLBACK_MESSAGE
    )


def _startup_config(mode: str, importance: str, legacy_enabled: bool = True):
    return SimpleNamespace(
        SEND_STARTUP_MENU_ON_BOOT=legacy_enabled,
        STARTUP_ANNOUNCE_MODE=mode,
        STARTUP_ANNOUNCE_IMPORTANCE=importance,
    )


def test_startup_announcement_policy_is_quiet_by_default():
    assert main._should_send_startup_announcement(_startup_config("off", "critical")) is False
    assert main._should_send_startup_announcement(_startup_config("major", "minor")) is False
    assert main._should_send_startup_announcement(_startup_config("major", "major")) is True
    assert main._should_send_startup_announcement(_startup_config("major", "critical")) is True
    assert main._should_send_startup_announcement(_startup_config("always", "minor")) is True
    assert main._should_send_startup_announcement(_startup_config("always", "critical", False)) is False


def test_admin_startup_notice_policy_is_separate_from_user_broadcasts():
    assert main._should_send_admin_startup_notice(
        SimpleNamespace(STARTUP_ADMIN_ANNOUNCE_MODE="off")
    ) is False
    assert main._should_send_admin_startup_notice(
        SimpleNamespace(STARTUP_ADMIN_ANNOUNCE_MODE="once_per_version")
    ) is True
    assert main._should_send_admin_startup_notice(
        SimpleNamespace(STARTUP_ADMIN_ANNOUNCE_MODE="always")
    ) is True
    assert main._should_send_admin_startup_notice(
        SimpleNamespace(STARTUP_ADMIN_ANNOUNCE_MODE="bad-value")
    ) is True


def test_admin_startup_notice_text_is_explicitly_admin_only():
    """Admin startup notice should not look like a user broadcast."""
    text = main._format_admin_startup_notice_text(
        {
            "started_at_display": "26.05.2026 18:02",
            "started_timezone": "Europe/Moscow",
            "startup_announce_mode": "off",
            "startup_admin_announce_mode": "once_per_version",
        }
    )

    assert "только администраторам" in text
    assert "Версия:" in text
    assert "Технические изменения:" not in text
    assert "Пользовательские релизные сообщения" not in text
    assert "Служебные admin-уведомления" not in text


def test_optional_technical_changes_are_empty_when_not_configured():
    assert optional_release_change_lines("", None) == []
    assert optional_release_change_lines("????????? ???????????", None) == []


def test_release_history_reads_recent_changelog_entries(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## 0.2.0-beta\n\n"
        "- Пользовательское изменение\n"
        "- Техническое изменение\n\n"
        "## 0.1.0-beta\n\n"
        "- Первый релиз\n",
        encoding="utf-8",
    )

    assert release_history(limit=1, changelog_path=changelog) == [
        {
            "version": "0.2.0-beta",
            "items": ["Пользовательское изменение", "Техническое изменение"],
        }
    ]
