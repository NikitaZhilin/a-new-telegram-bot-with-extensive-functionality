"""Anonymous diagnostics of user-facing problems (safe for public CI logs).

Runs inside the api container. Read-only. Prints no names, IDs or record
texts: only error types, wizard steps and counts.
"""

import asyncio
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())

from sqlalchemy import select  # noqa: E402

from src.db.models import (  # noqa: E402
    BotActivityEvent,
    Medication,
    MedicationIntake,
    Note,
    Reminder,
    ReminderNotification,
    TodoList,
)
from src.db.session import async_session_maker  # noqa: E402

MED_WORDS = re.compile(r"таблет|капсул|витамин|лекарств|препарат|\bмг\b|капл|укол|инъекц|сироп|антибиот|принять|выпить|пить ", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-–—•*+]|\d+[.)]|☐|✅|⬜)\s*\S", re.M)
REMINDER_STEPS = ("reminder_create", "list_remind", "note_remind", "driver_reminder_template")


def _v(value):
    return (value.value if hasattr(value, "value") else str(value)).lower()


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


def redact(text: str) -> str:
    text = re.sub(r"\"[^\"]*\"|'[^']*'|«[^»]*»", "<…>", text or "")
    return re.sub(r"\d{5,}", "<n>", text)[:220]


async def main() -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        reminders = {r.id: r for r in (await session.execute(select(Reminder))).scalars().all()}
        notifications = (await session.execute(select(ReminderNotification))).scalars().all()
        meds = (await session.execute(select(Medication))).scalars().all()
        intakes = (await session.execute(select(MedicationIntake))).scalars().all()
        notes = (await session.execute(select(Note))).scalars().all()
        lists = (await session.execute(select(TodoList))).scalars().all()
        events = (await session.execute(
            select(BotActivityEvent.user_id, BotActivityEvent.event_name, BotActivityEvent.event_type,
                   BotActivityEvent.created_at)
            .where(BotActivityEvent.user_id.is_not(None), BotActivityEvent.domain != "system")
            .order_by(BotActivityEvent.user_id, BotActivityEvent.created_at)
        )).all()

    print("== FAILED / ERRORED DELIVERIES")
    for n in notifications:
        if _v(n.status) == "failed" or (n.last_error and _v(n.status) != "sent"):
            r = reminders.get(n.reminder_id)
            print(f"  status={_v(n.status)} source={r.source_module if r else '?'} repeat={_v(r.repeat_rule) if r else '?'}"
                  f" reminder={_v(r.status) if r else '?'} due={_utc(n.notify_at_utc):%Y-%m-%d %H:%M} "
                  f"text_len={len(r.text) if r else 0} has_lt_gt={bool(r and re.search('[<>&]', (r.title or '') + r.text))}"
                  f" error={redact(n.last_error)}")
    missed = [r for r in reminders.values() if _v(r.status) == "missed"]
    print(f"== MISSED REMINDERS: {len(missed)}; sources {Counter(r.source_module for r in missed)}")

    print("== MEDICATIONS")
    active_med_reminders = Counter(r.medication_id for r in reminders.values()
                                   if r.medication_id and _v(r.status) == "active")
    any_med_reminders = Counter(r.medication_id for r in reminders.values() if r.medication_id)
    marks = Counter(i.medication_id for i in intakes)
    for m in meds:
        print(f"  med active={m.is_active} importance={m.importance} active_reminders={active_med_reminders[m.id]} "
              f"reminders_ever={any_med_reminders[m.id]} marks={marks[m.id]} created={m.created_at:%Y-%m-%d}")

    print("== HINT TYPES")
    hint = Counter()
    for r in reminders.values():
        if r.source_module == "general" and not r.medication_id and MED_WORDS.search(f"{r.title or ''} {r.text}"):
            hint["medication kept as plain reminder (rows)"] += 1
    one_time = Counter((r.user_id, r.text.strip().lower()) for r in reminders.values() if _v(r.repeat_rule) == "none")
    hint["one-time reminder re-created >=3 times (groups)"] = sum(1 for c in one_time.values() if c >= 3)
    hint["note formatted as a list"] = sum(1 for n in notes if len(LIST_LINE.findall(n.text or "")) >= 3)
    hint["lists"] = len(lists)
    print("  " + ", ".join(f"{k}: {v}" for k, v in hint.items()))

    print("== REMINDER WIZARD: where people stop")
    per_user = defaultdict(list)
    for user_id, name, kind, created_at in events:
        per_user[user_id].append((name, kind, _utc(created_at)))
    outcome = Counter()
    last_step = Counter()
    for evs in per_user.values():
        i = 0
        while i < len(evs):
            name, _, at = evs[i]
            if name.split(":")[0] in REMINDER_STEPS:
                steps = []
                j = i + 1
                saved = False
                while j < len(evs) and evs[j][2] - at < timedelta(minutes=20):
                    n2, k2, _ = evs[j]
                    base = n2.split(":")[0]
                    if base in REMINDER_STEPS:
                        break
                    if base.startswith("rem_notify") or base == "rem_confirm_create":
                        saved = True
                        break
                    if base.startswith(("rem_", "driver_rem_")) or k2 == "text_input":
                        steps.append("text" if k2 == "text_input" else base)
                    elif k2 in ("callback", "menu", "command"):
                        steps.append("LEFT->" + base)
                        break
                    j += 1
                outcome["saved" if saved else "abandoned"] += 1
                if not saved:
                    last_step[" > ".join(steps[-3:]) or "(nothing after start)"] += 1
                i = j
            else:
                i += 1
    print(f"  {dict(outcome)}")
    for k, v in last_step.most_common(12):
        print(f"  abandoned after: {k}  x{v}")

    print("== OTHER WIZARDS")
    starts = Counter()
    for evs in per_user.values():
        names = [n for n, _, _ in evs]
        for key in ("med_create", "list_create", "note_create", "driver_vehicle_create", "med_remind",
                    "settings_timezone", "list_add_item", "list_add_bulk"):
            starts[key] += sum(1 for n in names if n.split(":")[0] == key)
    print("  starts: " + ", ".join(f"{k} {v}" for k, v in starts.items()))
    texts = Counter()
    for evs in per_user.values():
        for idx, (name, kind, _) in enumerate(evs):
            if kind == "text_input":
                prev = next((evs[p][0] for p in range(idx - 1, -1, -1) if evs[p][1] != "text_input"), "start")
                texts[prev.split(":")[0]] += 1
    print("  text typed after: " + ", ".join(f"{k} {v}" for k, v in texts.most_common(12)))
    print(f"== DONE at {now:%Y-%m-%d %H:%M} UTC")


asyncio.run(main())
