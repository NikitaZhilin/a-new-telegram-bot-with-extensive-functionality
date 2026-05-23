"""Text formatting utilities."""


def escape_markdown(text: str) -> str:
    """
    Escape special Markdown v2 characters.
    
    Args:
        text: Text to escape
    
    Returns:
        Escaped text
    """
    escape_chars = "_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def truncate(text: str, length: int = 50, suffix: str = "...") -> str:
    """
    Truncate text to specified length.
    
    Args:
        text: Text to truncate
        length: Maximum length
        suffix: Suffix to add
    
    Returns:
        Truncated text
    """
    if len(text) <= length:
        return text
    return text[:length - len(suffix)] + suffix
