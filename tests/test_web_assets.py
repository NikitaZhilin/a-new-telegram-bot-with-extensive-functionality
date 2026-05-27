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


def test_web_driver_journal_has_forms_and_filters():
    """Driver journal should be visible in web and use inline forms."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert 'id="journalCreateForm"' in html
    assert 'id="driverJournalFilterForm"' in html
    assert 'id="journalContainer"' in html
    assert "handleJournalCreate" in script
    assert "handleJournalUpdate" in script
    assert "handleJournalFilter" in script
    assert "renderJournalEditForm" in script
    assert '"/me/driver/journal"' in script
    assert "`/me/driver/journal/${form.dataset.id}`" in script
    assert '`/me/driver/journal/${id}`' in script


def test_web_lists_use_single_active_checklist_surface():
    """Active list checks should render one checklist surface and collapse source rows."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert "renderSourceListPanel" in script
    assert "source-list-panel" in script
    assert "Проверка идет выше" in script
    assert "${checklistPanel}" in script
    assert "${sourceListPanel}" in script
    assert ".accordion-panel" in styles
    assert ".source-list-items" in styles


def test_web_reminder_datetime_avoids_native_picker():
    """Reminder web form should use the styled text datetime input, not native calendar UI."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert 'name="remind_at_local" type="text" inputmode="numeric"' in html
    assert 'name="remind_at_local" type="datetime-local"' not in html
    assert "normalizeLocalDatetimeInput" in script
    assert "formatLocalDatetimeText" in script


def test_web_repeat_and_importance_use_choice_groups():
    """Repeat and medication importance controls should avoid native select dropdowns."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert 'class="choice-group" data-field="repeat_rule"' in html
    assert 'class="choice-group" data-field="importance"' in html
    assert "renderChoiceGroup" in script
    assert "handleChoiceButton" in script
    assert ".choice-button.active" in styles


def test_web_dashboard_testing_notice_is_not_duplicated():
    """Testing notice should stay in the topbar and not repeat inside release info."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert html.count("Тестовый режим: данные могут быть изменены или утеряны.") == 1
    assert "info.testing_notice_text" not in script
