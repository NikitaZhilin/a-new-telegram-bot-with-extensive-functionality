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


def test_web_uses_top_tabs_navigation():
    """Main web navigation should be top tabs with mobile horizontal scrolling."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert '<aside class="sidebar">' not in html
    assert '<nav id="mobileNav" class="nav nav-tabs"' in html
    assert html.index('<header class="topbar">') < html.index('<nav id="mobileNav"')
    assert ".nav-tabs" in styles
    assert "overflow-x: auto" in styles
    assert ".menu-toggle {\n  display: none;" in styles


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


def test_web_loads_telegram_sdk_before_local_app_script():
    """Telegram Mini App SDK must be available before the local app boot code."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")

    sdk_index = html.index("https://telegram.org/js/telegram-web-app.js")
    app_index = html.index("/web/assets/app.js")

    assert sdk_index < app_index


def test_web_initializes_telegram_mini_app_runtime():
    """Web client should use Telegram initData, ready, theme, viewport, and safe-area APIs."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert "initTelegramRuntime" in script
    assert "Telegram?.WebApp" in script
    assert "telegram.initData" in script
    assert 'dataset.telegramMiniApp = "true"' in script
    assert "telegram.ready" in script
    assert "telegram.expand" in script
    assert "themeChanged" in script
    assert "viewportChanged" in script
    assert "safeAreaChanged" in script
    assert "contentSafeAreaChanged" in script
    assert "--app-height" in styles
    assert "--safe-area-bottom" in styles


def test_web_hides_manual_login_and_admin_nav_in_telegram_mode():
    """Mini App launch should rely on initData and keep admin UI out of the user shell."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert 'Boolean(state.user) || isTelegramMiniApp()' in script
    assert 'section === "admin" && isTelegramMiniApp()' in script
    assert '.telegram-mini-app #loginPanel' in styles
    assert '.telegram-mini-app [data-section="admin"]' in styles


def test_web_background_uses_soft_theme_gradient():
    """Web app background should use a subtle theme gradient instead of a flat fill."""
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert "--page-gradient" in styles
    assert "var(--page-gradient)" in styles


def test_web_design_system_styles_cards_forms_and_metrics():
    """Dashboard/cards/forms should share the same design-system primitives."""
    script = Path("src/web/app.js").read_text(encoding="utf-8")
    styles = Path("src/web/styles.css").read_text(encoding="utf-8")

    assert "--radius-lg" in styles
    assert "--panel-bg" in styles
    assert "--card-bg" in styles
    assert ".panel > h2:first-child" in styles
    assert ".metric::before" in styles
    assert ".metric-accent-4" in styles
    assert 'class="metric metric-accent-${(index % 4) + 1}"' in script


def test_web_reminders_can_link_general_lists():
    """Web reminder UI should expose list linking and list-to-reminder navigation."""
    html = Path("src/web/index.html").read_text(encoding="utf-8")
    script = Path("src/web/app.js").read_text(encoding="utf-8")

    assert '<select name="list_id">' in html
    assert "renderReminderListOptions" in script
    assert "prefillReminderFromList" in script
    assert 'data-action="remind-list"' in script
    assert 'data-action="open-reminder-list"' in script
    assert "list_id: form.list_id.value ? Number(form.list_id.value) : null" in script
