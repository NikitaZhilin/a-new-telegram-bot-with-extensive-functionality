"""Who uses the bot: detailed report to admins in Telegram, totals to stdout.

Runs inside the api container (it has the database and bot settings):
    docker exec -i <prefix>-api python - < scripts/users-report.py

Read-only. Names and Telegram IDs are sent only to ADMIN_TELEGRAM_IDS via the
bot itself; stdout (which may end up in public CI logs) gets numbers only.
"""

import asyncio
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())

import httpx  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from src.config import settings  # noqa: E402
from src.db.models import (  # noqa: E402
    BotActivityEvent,
    DriverVehicle,
    ListMember,
    Medication,
    Note,
    Reminder,
    TodoList,
    User,
)
from src.db.session import async_session_maker  # noqa: E402

TZ = ZoneInfo(settings.TIMEZONE_DEFAULT or "Europe/Moscow")


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _day(value):
    return _utc(value).astimezone(TZ).strftime("%d.%m.%Y") if value else "—"


async def _counts(session, model, column, *conditions):
    result = await session.execute(
        select(column, func.count()).select_from(model).where(*conditions).group_by(column)
    )
    return dict(result.all())


async def main() -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        users = (await session.execute(select(User).order_by(User.created_at))).scalars().all()

        events = (await session.execute(
            select(BotActivityEvent.user_id, BotActivityEvent.event_name, BotActivityEvent.metadata_json,
                   BotActivityEvent.created_at, BotActivityEvent.event_type)
            .where(BotActivityEvent.user_id.is_not(None), BotActivityEvent.domain != "system")
            .order_by(BotActivityEvent.created_at)
        )).all()

        lists = await _counts(session, TodoList, TodoList.user_id)
        notes = await _counts(session, Note, Note.user_id, Note.is_archived.is_(False))
        reminders = await _counts(session, Reminder, Reminder.user_id)
        meds = await _counts(session, Medication, Medication.user_id, Medication.is_active.is_(True))
        cars = await _counts(session, DriverVehicle, DriverVehicle.user_id)
        memberships = (await session.execute(
            select(ListMember.user_id, ListMember.invited_by_user_id, ListMember.created_at)
        )).all()
        copies = await _counts(session, TodoList, TodoList.user_id, TodoList.title.like("%(копия)"))

    by_id = {u.id: u for u in users}

    def name(user):
        if user is None:
            return "?"
        full = " ".join(p for p in (user.first_name, user.last_name) if p) or "без имени"
        return f"{full} (@{user.username})" if user.username else full

    first_event, last_event, events_30d = {}, {}, Counter()
    for user_id, event_name, meta, created_at, event_type in events:
        first_event.setdefault(user_id, (event_name, meta or {}))
        last_event[user_id] = created_at
        if _utc(created_at) > now - timedelta(days=30):
            events_30d[user_id] += 1
    invited = {}
    for user_id, inviter, created_at in memberships:
        invited.setdefault(user_id, inviter)

    rows, origins, activity = [], Counter(), Counter()
    admin_ids = settings.admin_telegram_id_set
    for index, user in enumerate(users, start=1):
        first_name, first_meta = first_event.get(user.id, (None, {}))
        if user.telegram_id in admin_ids or user.is_admin:
            origin = "администратор"
        elif user.id in invited:
            origin = f"по приглашению в общий список от {name(by_id.get(invited[user.id]))}"
        elif copies.get(user.id):
            origin = "по ссылке «копия списка»"
        elif first_name == "/start" and first_meta.get("has_args"):
            origin = "по ссылке с параметром (список)"
        elif first_name == "/start":
            origin = "сам нашёл бота / ссылка без метки"
        elif first_name:
            origin = f"первое действие: {first_name}"
        else:
            origin = "нет записей активности"
        origins[origin.split(" от ")[0]] += 1

        last = last_event.get(user.id)
        if last and _utc(last) > now - timedelta(days=1):
            activity["сегодня/вчера"] += 1
        elif last and _utc(last) > now - timedelta(days=7):
            activity["за неделю"] += 1
        elif last and _utc(last) > now - timedelta(days=30):
            activity["за месяц"] += 1
        else:
            activity["давно или никогда"] += 1

        usage = ", ".join(
            f"{label} {count}" for label, count in (
                ("списки", lists.get(user.id, 0)), ("заметки", notes.get(user.id, 0)),
                ("напоминания", reminders.get(user.id, 0)), ("лекарства", meds.get(user.id, 0)),
                ("авто", cars.get(user.id, 0)),
            ) if count
        ) or "ничего не создал"
        rows.append(
            f"{index}. {name(user)} · id {user.telegram_id}\n"
            f"   с {_day(user.created_at)}, последняя активность {_day(last)}, действий за 30 дн: {events_30d.get(user.id, 0)}\n"
            f"   откуда: {origin}\n"
            f"   пользуется: {usage}; пояс {user.timezone}"
        )

    header = (
        f"👥 Пользователи бота: {len(users)} (на {now.astimezone(TZ):%d.%m.%Y %H:%M})\n"
        "Источник прихода бот не сохраняет; ниже — то, что видно по данным.\n"
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

    by_month = Counter(_utc(u.created_at).astimezone(TZ).strftime("%Y-%m") for u in users)
    print(f"USERS TOTAL: {len(users)}")
    print("REGISTERED BY MONTH: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_month.items())))
    print("LAST ACTIVITY: " + ", ".join(f"{k}: {v}" for k, v in activity.items()))
    print("ORIGIN: " + ", ".join(f"{k}: {v}" for k, v in origins.most_common()))
    print(f"USING SOMETHING: {sum(1 for u in users if any(d.get(u.id) for d in (lists, notes, reminders, meds, cars)))}")
    print(f"DETAILED REPORT: {sent} message(s) sent to {len(admin_ids)} admin(s) in Telegram")


asyncio.run(main())
