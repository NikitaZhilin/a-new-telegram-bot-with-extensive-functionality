"""init-db Alembic bootstrap tests."""

import pytest

from src import main as main_module


@pytest.mark.asyncio
async def test_init_db_runs_alembic_upgrade_for_clean_database(monkeypatch):
    """A fresh database should be initialized by Alembic migrations."""
    calls: list[str] = []

    async def fake_has_table(table_name: str) -> bool:
        return False

    async def fake_upgrade() -> None:
        calls.append("upgrade")

    async def fake_legacy_schema() -> None:
        calls.append("legacy")

    async def fake_stamp() -> None:
        calls.append("stamp")

    monkeypatch.setattr(main_module, "_database_has_table", fake_has_table)
    monkeypatch.setattr(main_module, "_run_alembic_upgrade_head", fake_upgrade)
    monkeypatch.setattr(main_module, "_ensure_legacy_unversioned_schema", fake_legacy_schema)
    monkeypatch.setattr(main_module, "_run_alembic_stamp_head", fake_stamp)

    await main_module.init_db()

    assert calls == ["upgrade"]


@pytest.mark.asyncio
async def test_init_db_upgrades_versioned_database(monkeypatch):
    """A database with alembic_version should use regular Alembic upgrade."""
    calls: list[str] = []

    async def fake_has_table(table_name: str) -> bool:
        return table_name == "alembic_version"

    async def fake_upgrade() -> None:
        calls.append("upgrade")

    async def fake_legacy_schema() -> None:
        calls.append("legacy")

    async def fake_stamp() -> None:
        calls.append("stamp")

    monkeypatch.setattr(main_module, "_database_has_table", fake_has_table)
    monkeypatch.setattr(main_module, "_run_alembic_upgrade_head", fake_upgrade)
    monkeypatch.setattr(main_module, "_ensure_legacy_unversioned_schema", fake_legacy_schema)
    monkeypatch.setattr(main_module, "_run_alembic_stamp_head", fake_stamp)

    await main_module.init_db()

    assert calls == ["upgrade"]


@pytest.mark.asyncio
async def test_init_db_stamps_legacy_unversioned_database(monkeypatch):
    """A legacy create_all database should be normalized and stamped once."""
    calls: list[str] = []

    async def fake_has_table(table_name: str) -> bool:
        return table_name == "users"

    async def fake_upgrade() -> None:
        calls.append("upgrade")

    async def fake_legacy_schema() -> None:
        calls.append("legacy")

    async def fake_stamp() -> None:
        calls.append("stamp")

    monkeypatch.setattr(main_module, "_database_has_table", fake_has_table)
    monkeypatch.setattr(main_module, "_run_alembic_upgrade_head", fake_upgrade)
    monkeypatch.setattr(main_module, "_ensure_legacy_unversioned_schema", fake_legacy_schema)
    monkeypatch.setattr(main_module, "_run_alembic_stamp_head", fake_stamp)

    await main_module.init_db()

    assert calls == ["legacy", "stamp"]


def test_alembic_config_uses_active_database_url():
    """Programmatic Alembic runs should not use the placeholder URL from alembic.ini."""
    config = main_module._make_alembic_config()

    assert config.get_main_option("sqlalchemy.url") == main_module.settings.DATABASE_URL
    assert config.get_main_option("script_location").endswith("alembic")
