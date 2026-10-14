"""What users did in the bot: per-user activity to admins in Telegram,
anonymous totals to stdout.

Runs inside the api container:
    docker exec -i <prefix>-api python - < scripts/users-activity.py

Read-only. Uses the bot's own sanitized activity log (button/menu names, no
message text) and record counts. The content of notes, reminders, lists and
medications is deliberately not read: it is the users' private data.
"""

import asyncio
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from src.config import settings  # noqa: E402
from src.db.models import (  # noqa: E402
    BotActivityEvent,
    ChecklistRun,
    DriverFuelEntry,
    DriverVehicle,
    ListItem,
    Medication,
    MedicationIntake,
    Note,
    Reminder,
    ReminderNotification,
    ReminderNotificationStatus,
    TodoList,
    User,
)
from src.db.session import async_session_maker  # noqa: E402
from src.services.activity_service import DOMAIN_LABELS, format_event_label  # noqa: E402

TZ = ZoneInfo(settings.TIMEZONE_DEFAULT or "Europe/Moscow")
NOISE = {"text_input", "home", "back", "menu:help", "help"}


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _day(value):
    return _utc(value).astimezone(TZ).strftime("%d.%m.%Y") if value else "—"


async def _per_user(session, query):
    return {row[0]: row[1:] if len(row) > 2 else row[1] for row in (await session.execute(query)).all()}


async def main() -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        users = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
        events = (await session.execute(
            select(BotActivityEvent.user_id, BotActivityEvent.event_name, BotActivityEvent.domain,
                   BotActivityEvent.created_at)
            .where(BotActivityEvent.user_id.is_not(None), BotActivityEvent.domain != "system")
        )).all()

        reminders = defaultdict(Counter)
        for user_id, status, source, count in (await session.execute(
            select(Reminder.user_id, Reminder.status, Reminder.source_module, func.count())
            .group_by(Reminder.user_id, Reminder.status, Reminder.source_module)
        )).all():
            status = status.value if hasattr(status, "value") else str(status)
            reminders[user_id][status.lower()] += count
            reminders[user_id]["src:" + source] += count
        delivered = await _per_user(session, select(Reminder.user_id, func.count())
            .join(ReminderNotification, ReminderNotification.reminder_id == Reminder.id)
            .where(ReminderNotification.status == ReminderNotificationStatus.SENT).group_by(Reminder.user_id))
        lists = await _per_user(session, select(TodoList.user_id, func.count()).group_by(TodoList.user_id))
        items = await _per_user(session, select(TodoList.user_id, func.count(ListItem.id))
            .join(ListItem, ListItem.list_id == TodoList.id).group_by(TodoList.user_id))
        notes = await _per_user(session, select(Note.user_id, func.count()).group_by(Note.user_id))
        meds = await _per_user(session, select(Medication.user_id, func.count()).group_by(Medication.user_id))
        intakes = await _per_user(session, select(MedicationIntake.user_id, func.count())
            .group_by(MedicationIntake.user_id))
        cars = await _per_user(session, select(DriverVehicle.user_id, func.count()).group_by(DriverVehicle.user_id))
        fuel = await _per_user(session, select(DriverFuelEntry.user_id, func.count())
            .group_by(DriverFuelEntry.user_id))
        checklists = await _per_user(session, select(ChecklistRun.user_id, func.count())
            .where(ChecklistRun.status == "completed").group_by(ChecklistRun.user_id))

    per_user_events = defaultdict(list)
    for user_id, event_name, domain, created_at in events:
        per_user_events[user_id].append((event_name, domain, _utc(created_at)))

    def name(user):
        full = " ".join(p for p in (user.first_name, user.last_name) if p) or "без имени"
        return f"{full} (@{user.username})" if user.username else full

    totals = Counter()
    domain_users = Counter()
    rows = []
    admin_ids = settings.admin_telegram_id_set
    for index, user in enumerate(users, start=1):
        evs = per_user_events.get(user.id, [])
        days = {e[2].astimezone(TZ).date() for e in evs}
        actions = Counter(e[0] for e in evs if e[0] not in NOISE)
        domains = Counter(e[1] for e in evs if e[1] not in ("unknown", "general", "navigation"))
        for domain in domains:
            domain_users[domain] += 1
        for key in ("reminder_create", "rem_confirm_create", "med_create", "list_create", "note_create",
                    "driver_vehicle_create"):
            totals[key] += actions.get(key, 0)

        r = reminders.get(user.id, Counter())
        created = []
        if r:
            created.append(
                f"напоминаний {sum(v for k, v in r.items() if not k.startswith('src:'))}"
                f" (активных {r['active']}, выполнено {r['done']}, отменено {r['canceled']},"
                f" пропущено {r['missed']}; пришло уведомлений {delivered.get(user.id, 0)})"
            )
        if lists.get(user.id):
            created.append(f"списков {lists[user.id]} ({items.get(user.id, 0)} пунктов)")
        if checklists.get(user.id):
            created.append(f"пройдено чек-листов {checklists[user.id]}")
        if notes.get(user.id):
            created.append(f"заметок {notes[user.id]}")
        if meds.get(user.id):
            created.append(f"лекарств {meds[user.id]} (отметок приёма {intakes.get(user.id, 0)})")
        if cars.get(user.id):
            created.append(f"авто {cars[user.id]} (заправок {fuel.get(user.id, 0)})")

        unfinished = []
        if actions.get("reminder_create", 0) > actions.get("rem_confirm_create", 0):
            unfinished.append(
                f"начинал создавать напоминание {actions['reminder_create']} раз, "
                f"подтвердил {actions.get('rem_confirm_create', 0)}"
            )
        if actions.get("med_create") and not meds.get(user.id):
            unfinished.append("начинал добавлять лекарство, но не сохранил")
        if actions.get("driver_vehicle_create") and not cars.get(user.id):
            unfinished.append("начинал добавлять авто, но не сохранил")

        top = ", ".join(f"{format_event_label(n)} ×{c}" for n, c in actions.most_common(6)) or "—"
        sections = ", ".join(DOMAIN_LABELS.get(d, d) for d, _ in domains.most_common()) or "—"
        is_admin = user.telegram_id in admin_ids or user.is_admin
        rows.append(
            f"{index}. {name(user)}{' — админ' if is_admin else ''}\n"
            f"   активен {len(days)} дн., {_day(min(e[2] for e in evs) if evs else None)} — "
            f"{_day(max(e[2] for e in evs) if evs else None)}, действий {len(evs)}\n"
            f"   разделы: {sections}\n"
            f"   чаще всего: {top}\n"
            f"   создал: {'; '.join(created) or 'ничего'}"
            + (f"\n   не довёл до конца: {'; '.join(unfinished)}" if unfinished else "")
        )

    header = (
        f"📊 Что делали пользователи (на {now.astimezone(TZ):%d.%m.%Y %H:%M})\n"
        "Только действия и количество записей; тексты заметок, напоминаний и названия лекарств не читались.\n"
    )
    messages, current = [], header
    for row in rows:
        if len(current) + len(row) + 2 > 3900:
            messages.append(current)
            current = ""
        current += "\n" + row + "\n"
    messages.append(current)

    sent = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for chat_id in admin_ids:
            for text in messages:
                response = await client.post(
                    f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                )
                sent += response.status_code == 200

    all_reminders = Counter()
    for counter in reminders.values():
        all_reminders.update(counter)
    print(f"USERS: {len(users)}, with any action: {sum(1 for u in users if per_user_events.get(u.id))}")
    print("SECTIONS (users): " + ", ".join(f"{DOMAIN_LABELS.get(d, d)}: {c}" for d, c in domain_users.most_common()))
    print(
        f"REMINDERS: started {totals['reminder_create']}, confirmed {totals['rem_confirm_create']}, "
        f"in db {sum(v for k, v in all_reminders.items() if not k.startswith('src:'))} "
        f"(active {all_reminders['active']}, done {all_reminders['done']}, canceled {all_reminders['canceled']}, "
        f"missed {all_reminders['missed']}); by section: "
        + ", ".join(f"{k[4:]} {v}" for k, v in all_reminders.items() if k.startswith("src:"))
    )
    print(
        f"OTHER: lists {sum(lists.values())} ({sum(items.values())} items), notes {sum(notes.values())}, "
        f"medications {sum(meds.values())} ({sum(intakes.values())} intakes), cars {sum(cars.values())} "
        f"({sum(fuel.values())} fuel), checklists done {sum(checklists.values())}"
    )
    print(f"DETAILED REPORT: {sent} message(s) sent to {len(admin_ids)} admin(s) in Telegram")


asyncio.run(main())
