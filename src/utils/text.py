"""Text utilities."""

def truncate(text: str, limit: int = 100, suffix: str = "...") -> str:
    """Return text shortened to the requested limit."""
    if len(text) <= limit:
        return text
    if limit <= len(suffix):
        return suffix[:limit]
    return text[: limit - len(suffix)] + suffix
