"""Helpers for public web and Mini App URLs."""

from __future__ import annotations


def normalize_public_base_url(raw_url: str | None) -> str:
    """Return a base URL without known app entrypoint suffixes."""
    base_url = (raw_url or "").strip().rstrip("/")
    for suffix in ("/web", "/miniapp"):
        if base_url.endswith(suffix):
            return base_url[: -len(suffix)]
    return base_url


def is_https_url(url: str) -> bool:
    """Return whether a URL can be used for Telegram WebApp launch."""
    return url.startswith("https://")
