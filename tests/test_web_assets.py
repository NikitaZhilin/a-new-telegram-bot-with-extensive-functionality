"""Static web asset regression checks."""

from pathlib import Path


def test_web_app_uses_inline_forms_instead_of_browser_prompts():
    """Browser prompt/alert/confirm dialogs should not be part of the web UX."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert "prompt(" not in script
    assert "alert(" not in script
    assert "confirm(" not in script
    assert "boolFromPrompt" not in script
