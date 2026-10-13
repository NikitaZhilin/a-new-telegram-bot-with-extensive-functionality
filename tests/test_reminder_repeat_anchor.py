"""Monthly repeats keep their day; downtime does not cause a burst of repeats."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.db.models import Reminder, ReminderStatus, RepeatRule, User
from src.repositories.reminder_repo import ReminderRepository, calculate_next_occurrence
from src.worker.reminder_worker import ReminderWorkerService

MSK = timezone(timedelta(hours=3))
TZ = "Europe/Moscow"


def msk(year, month, day, hour=9):
    return datetime(year, month, day, hour, 0, tzinfo=MSK).astimezone(timezone.utc)


def _monthly_chain(start, day, steps):
    seen = []
    current = start
    for _ in range(steps):
        seen.append(current.astimezone(MSK).strftime("%d.%m"))
        current = calculate_next_occurrence(current, RepeatRule.MONTHLY, TZ, day_of_month=day)
    return seen


@pytest.mark.parametrize(
    "day, expected",
    [
        (29, ["29.01", "28.02", "29.03", "29.04", "29.05"]),
        (30, ["30.01", "28.02", "30.03", "30.04", "30.05"]),
        (31, ["31.01", "28.02", "31.03", "30.04", "31.05"]),
    ],
)
def test_monthly_repeat_returns_to_original_day_after_short_month(day, expected):
    """Before the fix 30.01 -> 28.02 -> 31.03 -> 30.04 -> 31.05 (drift to month end)."""
    assert _monthly_chain(msk(2027, 1, day), day, 5) == expected


def test_monthly_repeat_created_on_30_april_stays_on_30th():
    nxt = calculate_next_occurrence(msk(2027, 4, 30), RepeatRule.MONTHLY, TZ, day_of_month=30)
    assert nxt.astimezone(MSK).day == 30


class _Repo:
    def __init__(self):
        self.created = []

    async def create_next_occurrence(self, reminder, next_time, notify_offsets_minutes=None):
        self.created.append((next_time, getattr(reminder, "repeat_day_of_month", None)))


def _reminder(remind_at, rule, anchor=None):
    return SimpleNamespace(
        id=1,
        remind_at_utc=remind_at,
        repeat_rule=rule,
        repeat_day_of_month=anchor,
        user=SimpleNamespace(timezone=TZ),
    )


@pytest.mark.asyncio
async def test_worker_skips_missed_daily_repeats_after_downtime():
    """Server was down 5 days: one message, next repeat tomorrow — not 6 in a row."""
    repo = _Repo()
    worker = ReminderWorkerService(bot=None)
    now = msk(2027, 3, 10, 15)

    await worker._handle_recurring(None, repo, _reminder(msk(2027, 3, 5), RepeatRule.DAILY), now)

    assert repo.created[0][0] == msk(2027, 3, 11)


@pytest.mark.asyncio
async def test_worker_remembers_monthly_anchor_day():
    repo = _Repo()
    worker = ReminderWorkerService(bot=None)
    reminder = _reminder(msk(2027, 1, 30), RepeatRule.MONTHLY)

    await worker._handle_recurring(None, repo, reminder, msk(2027, 1, 30))
    next_time, anchor = repo.created[0]

    assert anchor == 30
    assert next_time == msk(2027, 2, 28)

    following = _reminder(next_time, RepeatRule.MONTHLY, anchor)
    await worker._handle_recurring(None, repo, following, next_time)
    assert repo.created[1][0] == msk(2027, 3, 30)


@pytest.mark.asyncio
async def test_next_occurrence_row_keeps_anchor(db_session):
    user = User(telegram_id=66001, timezone=TZ)
    db_session.add(user)
    await db_session.flush()
    reminder = Reminder(
        user_id=user.id,
        text="Оплатить интернет",
        remind_at_utc=msk(2027, 1, 30),
        repeat_rule=RepeatRule.MONTHLY,
        repeat_day_of_month=30,
        status=ReminderStatus.ACTIVE,
        notifications=[],
    )
    db_session.add(reminder)
    await db_session.flush()

    created = await ReminderRepository(db_session).create_next_occurrence(
        reminder, msk(2027, 2, 28), notify_offsets_minutes=[0]
    )

    assert created.repeat_day_of_month == 30
