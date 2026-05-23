"""Tests for driver assistant input parsing helpers."""

import pytest

from src.bot.handlers.driver import _limit_text, _parse_bool


def test_driver_full_tank_parser_accepts_clear_values():
    """Full-tank input should handle common Russian and compact values."""
    assert _parse_bool("да") is True
    assert _parse_bool("полный") is True
    assert _parse_bool("нет") is False
    assert _parse_bool("частично") is False


def test_driver_full_tank_parser_rejects_ambiguous_values():
    """Ambiguous full-tank input should not silently become True."""
    with pytest.raises(ValueError):
        _parse_bool("наверное")


def test_driver_text_limit_trims_database_sized_fields():
    """Compact text fields should be safe for bounded database columns."""
    assert _limit_text("  АЗС  ", 255) == "АЗС"
    assert len(_limit_text("x" * 300, 255)) == 255
