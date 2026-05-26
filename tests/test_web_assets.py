"""Static web asset regression checks."""

from pathlib import Path


def test_web_app_uses_inline_forms_instead_of_browser_prompts():
    """Browser prompt/alert/confirm dialogs should not be part of the web UX."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert "prompt(" not in script
    assert "alert(" not in script
    assert "confirm(" not in script
    assert "boolFromPrompt" not in script


def test_web_theme_and_reload_controls_are_in_topbar():
    """Theme/reload controls must stay visible on mobile without opening sidebar."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    topbar = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]

    assert 'id="themeToggle"' in topbar
    assert 'id="reloadButton"' in topbar


def test_web_dashboard_has_release_info_block():
    """Web dashboard should expose version/changelog metadata without opening menus."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert 'id="releaseInfo"' in html
    assert '"/app/info"' in script
    assert "renderReleaseInfo" in script
    assert "started_at_display" in script
    assert "user_changes" in script
    assert "technical_changes" in script
    assert "release_history" in script
