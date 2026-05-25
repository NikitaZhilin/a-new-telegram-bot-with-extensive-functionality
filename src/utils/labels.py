"""Human-readable labels for user-facing enum values."""

from src.db.models import ReminderStatus, RepeatRule


def repeat_rule_label(value: RepeatRule | str | None) -> str:
    """Return a Russian label for reminder repeat rules."""
    raw = value.value if hasattr(value, "value") else value
    return {
        RepeatRule.NONE.value: "нет",
        RepeatRule.DAILY.value: "ежедневно",
        RepeatRule.WEEKLY.value: "еженедельно",
        RepeatRule.MONTHLY.value: "ежемесячно",
    }.get(str(raw or RepeatRule.NONE.value), str(raw or "нет"))


def reminder_status_label(value: ReminderStatus | str | None) -> str:
    """Return a Russian label for reminder status."""
    raw = value.value if hasattr(value, "value") else value
    return {
        ReminderStatus.ACTIVE.value: "активно",
        ReminderStatus.DONE.value: "выполнено",
        ReminderStatus.CANCELED.value: "отменено",
        ReminderStatus.MISSED.value: "пропущено",
    }.get(str(raw or ReminderStatus.ACTIVE.value), str(raw or "активно"))
