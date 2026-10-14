"""Technical export of what every user set up and whether it works.

Runs inside the api container:
    docker exec -i <prefix>-api python - < scripts/users-export.py

Read-only. Sends CSV files (open in Excel) to ADMIN_TELEGRAM_IDS through the
bot; stdout gets anonymous totals only. Texts of reminders, notes and lists,
and medication names/dosages are NOT exported: they are the users' private
(and for medications, health) data and are not needed to see whether things
work.
"""

import asyncio
import csv
import io
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
    DriverVehicle,
    ListItem,
    ListMember,
    Medication,
    MedicationIntake,
    Note,
    Reminder,
    ReminderNotification,
    RepeatRule,
    TodoList,
    User,
)
from src.db.session import async_session_maker  # noqa: E402
from src.utils.timezones import effective_user_timezone  # noqa: E402

DEFAULT_TZ = settings.TIMEZONE_DEFAULT or "Europe/Moscow"
REPORT_TZ = ZoneInfo(DEFAULT_TZ)
SECTION = {"general": "Напоминания", "list": "Списки", "note": "Заметки", "medication": "Лекарства",
           "driver": "Водитель"}
REPEAT = {"none": "разово", "daily": "ежедневно", "weekly": "еженедельно", "monthly": "ежемесячно"}
STATUS = {"active": "активно", "done": "выполнено", "canceled": "отменено", "missed": "пропущено"}


def _v(value):
    return value.value if hasattr(value, "value") else str(value)


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _fmt(value, tz):
    return _utc(value).astimezone(tz).strftime("%d.%m.%Y %H:%M") if value else ""


def _csv(header, rows) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")  # BOM: Excel reads Cyrillic


def _blocked(error: str) -> bool:
    text = (error or "").lower()
    return "blocked" in text or "forbidden" in text or "deactivated" in text or "chat not found" in text


async def main() -> None:
    now = datetime.now(timezone.utc)
    async with async_session_maker() as session:
        users = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
        reminders = (await session.execute(select(Reminder).order_by(Reminder.user_id, Reminder.id))).scalars().all()
        notifications = defaultdict(list)
        for n in (await session.execute(select(ReminderNotification))).scalars().all():
            notifications[n.reminder_id].append(n)
        meds = (await session.execute(select(Medication).order_by(Medication.user_id, Medication.id))).scalars().all()
        intakes = defaultdict(list)
        for i in (await session.execute(select(MedicationIntake))).scalars().all():
            intakes[i.medication_id].append(i)
        lists = (await session.execute(select(TodoList).order_by(TodoList.user_id, TodoList.id))).scalars().all()
        items = defaultdict(lambda: [0, 0])
        for list_id, done, count in (await session.execute(
            select(ListItem.list_id, ListItem.is_completed, func.count()).group_by(ListItem.list_id, ListItem.is_completed)
        )).all():
            items[list_id][0] += count
            if done:
                items[list_id][1] += count
        members = Counter(r[0] for r in (await session.execute(select(ListMember.list_id))).all())
        member_of = defaultdict(list)
        for list_id, user_id in (await session.execute(select(ListMember.list_id, ListMember.user_id))).all():
            member_of[user_id].append(list_id)
        runs = defaultdict(Counter)
        for list_id, status, count in (await session.execute(
            select(ChecklistRun.source_list_id, ChecklistRun.status, func.count())
            .group_by(ChecklistRun.source_list_id, ChecklistRun.status)
        )).all():
            runs[list_id][status] += count
        notes = dict((await session.execute(select(Note.user_id, func.count()).group_by(Note.user_id))).all())
        cars = dict((await session.execute(select(DriverVehicle.user_id, func.count()).group_by(DriverVehicle.user_id))).all())
        activity = {}
        for user_id, first, last, total in (await session.execute(
            select(BotActivityEvent.user_id, func.min(BotActivityEvent.created_at),
                   func.max(BotActivityEvent.created_at), func.count())
            .where(BotActivityEvent.user_id.is_not(None), BotActivityEvent.domain != "system")
            .group_by(BotActivityEvent.user_id)
        )).all():
            activity[user_id] = (first, last, total)

    by_id = {u.id: u for u in users}
    user_no = {u.id: index for index, u in enumerate(users, start=1)}
    tz_of = {u.id: ZoneInfo(effective_user_timezone(u.timezone, DEFAULT_TZ)) for u in users}

    def who(user_id):
        user = by_id.get(user_id)
        if not user:
            return f"#{user_id}"
        full = " ".join(p for p in (user.first_name, user.last_name) if p) or "без имени"
        return f"{user_no[user_id]}. {full}" + (f" (@{user.username})" if user.username else "")

    problems = []
    blocked_users = set()

    # --- reminders ---------------------------------------------------------------------
    reminder_rows = []
    done_old = Counter()
    for r in reminders:
        status = _v(r.status).lower()
        ns = notifications.get(r.id, [])
        sent = [n for n in ns if _v(n.status) == "SENT"]
        pending = [n for n in ns if _v(n.status) == "PENDING"]
        failed = [n for n in ns if _v(n.status) == "FAILED"]
        last_error = next((n.last_error for n in sorted(ns, key=lambda n: n.id, reverse=True) if n.last_error), "")
        if any(_blocked(n.last_error) for n in failed):
            blocked_users.add(r.user_id)
        # Finished repeats pile up (one row per day); keep only recent ones.
        if status == "done" and not failed and _utc(r.remind_at_utc) < now - timedelta(days=14):
            done_old[r.user_id] += 1
            continue
        tz = tz_of.get(r.user_id, REPORT_TZ)
        if status == "active":
            future = sorted(_utc(n.notify_at_utc) for n in pending if _utc(n.notify_at_utc) > now)
            overdue = [n for n in pending if _utc(n.notify_at_utc) <= now - timedelta(minutes=10)]
            if overdue:
                verdict = "⚠️ просрочено: уведомление не ушло вовремя"
            elif future:
                verdict = f"✅ работает, ближайшее уведомление {_fmt(future[0], tz)}"
            else:
                verdict = "❌ не придёт: нет запланированных уведомлений"
        elif failed:
            verdict = "❌ не доставлено" + (" — пользователь заблокировал бота" if _blocked(last_error) else "")
        elif status == "missed":
            verdict = "⚠️ пропущено"
        elif status == "done":
            verdict = "✅ отработало" if sent else "✅ закрыто пользователем"
        else:
            verdict = "отменено"
        if verdict.startswith(("❌", "⚠️")):
            problems.append((who(r.user_id), f"Напоминание #{r.id} ({SECTION.get(r.source_module, r.source_module)})",
                             verdict, (last_error or "")[:200]))
        linked = ("список" if r.list_id else "заметка" if r.note_id else "лекарство" if r.medication_id
                  else "документ авто" if r.driver_document_id else "")
        reminder_rows.append([
            who(r.user_id), r.id, SECTION.get(r.source_module, r.source_module), linked,
            REPEAT.get(_v(r.repeat_rule).lower(), _v(r.repeat_rule)), STATUS.get(status, status),
            _fmt(r.remind_at_utc, tz), _fmt(r.created_at, tz), len(sent), len(pending), len(failed),
            verdict, (last_error or "")[:200],
        ])

    # --- medications -------------------------------------------------------------------
    med_reminders = defaultdict(list)
    for r in reminders:
        if r.medication_id and _v(r.status).lower() == "active":
            med_reminders[r.medication_id].append(r)
    med_rows = []
    for m in meds:
        tz = tz_of.get(m.user_id, REPORT_TZ)
        daily = [r for r in med_reminders.get(m.id, []) if _v(r.repeat_rule).lower() == "daily"]
        times = sorted({_utc(r.remind_at_utc).astimezone(tz).strftime("%H:%M") for r in daily})
        marks = intakes.get(m.id, [])
        taken = sum(1 for i in marks if _v(i.status).lower() != "skipped")
        skipped = len(marks) - taken
        recent = [i for i in marks if _utc(i.taken_at_utc) > now - timedelta(days=14)]
        expected = len(times) * 14
        adherence = f"{min(100, round(len(recent) * 100 / expected))}%" if expected else ""
        last_mark = max((_utc(i.taken_at_utc) for i in marks), default=None)
        if not m.is_active:
            verdict = "в архиве"
        elif not times:
            verdict = "⚠️ нет расписания: напоминания не приходят"
        else:
            verdict = f"✅ напоминания в {', '.join(times)}"
        if verdict.startswith("⚠️"):
            problems.append((who(m.user_id), f"Лекарство #{m.id}", verdict, ""))
        med_rows.append([
            who(m.user_id), m.id, "активно" if m.is_active else "архив", m.importance,
            ", ".join(times), taken, skipped, adherence, _fmt(last_mark, tz), _fmt(m.created_at, tz), verdict,
        ])

    # --- lists ---------------------------------------------------------------------------
    list_reminders = Counter(r.list_id for r in reminders if r.list_id and _v(r.status).lower() == "active")
    list_rows = []
    for todo in lists:
        tz = tz_of.get(todo.user_id, REPORT_TZ)
        total, done = items[todo.id]
        list_rows.append([
            who(todo.user_id), todo.id, SECTION.get(todo.source_module, todo.source_module), total, done,
            members.get(todo.id, 0), runs[todo.id].get("completed", 0), runs[todo.id].get("active", 0),
            list_reminders.get(todo.id, 0), _fmt(todo.created_at, tz), _fmt(todo.updated_at, tz),
        ])

    # --- users ---------------------------------------------------------------------------
    user_rows = []
    for u in users:
        tz = tz_of[u.id]
        first, last, total = activity.get(u.id, (None, None, 0))
        own_reminders = [r for r in reminders if r.user_id == u.id]
        active = sum(1 for r in own_reminders if _v(r.status).lower() == "active")
        user_rows.append([
            who(u.id), u.username or "", u.telegram_id, effective_user_timezone(u.timezone, DEFAULT_TZ),
            _fmt(u.created_at, tz), _fmt(last, tz), total,
            active, len(own_reminders), sum(1 for m in meds if m.user_id == u.id and m.is_active),
            sum(1 for t in lists if t.user_id == u.id), len(member_of.get(u.id, [])), notes.get(u.id, 0),
            cars.get(u.id, 0), "да" if u.id in blocked_users else "",
        ])
        if u.id in blocked_users:
            problems.append((who(u.id), "Доставка", "❌ бот заблокирован пользователем или чат недоступен", ""))

    files = {
        "1_пользователи.csv": _csv(
            ["Пользователь", "Username", "Telegram ID", "Часовой пояс", "Пришёл", "Последняя активность",
             "Действий", "Активных напоминаний", "Напоминаний всего (с повторами)", "Активных лекарств",
             "Своих списков", "Участник чужих списков", "Заметок", "Авто", "Заблокировал бота"], user_rows),
        "2_напоминания.csv": _csv(
            ["Пользователь", "ID", "Раздел", "Привязано к", "Повтор", "Статус", "Когда (местное)", "Создано",
             "Уведомлений отправлено", "Ожидает", "Ошибок доставки", "Работает?", "Последняя ошибка"],
            reminder_rows),
        "3_лекарства.csv": _csv(
            ["Пользователь", "ID", "Статус", "Важность", "Время приёма", "Отмечено «принял»", "«Пропустил»",
             "Отмечено за 14 дней от плана", "Последняя отметка", "Добавлено", "Работает?"], med_rows),
        "4_списки.csv": _csv(
            ["Пользователь", "ID", "Раздел", "Пунктов", "Выполнено", "Участников", "Чек-листов пройдено",
             "Чек-листов в процессе", "Активных напоминаний", "Создан", "Изменён"], list_rows),
        "5_проблемы.csv": _csv(["Пользователь", "Что", "Проблема", "Ошибка"], problems),
    }
    caption = (
        f"📦 Выгрузка на {now.astimezone(REPORT_TZ):%d.%m.%Y %H:%M}: пользователей {len(users)}, "
        f"проблем {len(problems)}. Тексты напоминаний/заметок/списков и названия лекарств не выгружались. "
        f"Выполненные повторы старше 14 дней посчитаны в «Напоминаний всего», но не перечислены."
    )

    sent = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for chat_id in settings.admin_telegram_id_set:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": caption},
            )
            sent += response.status_code == 200
            for filename, content in files.items():
                response = await client.post(
                    f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument",
                    data={"chat_id": str(chat_id)},
                    files={"document": (filename, content, "text/csv")},
                )
                sent += response.status_code == 200
                if response.status_code != 200:
                    print(f"SEND ERROR {filename}: {response.status_code}")

    kinds = Counter(p[2].split(":")[0].split(" —")[0] for p in problems)
    print(f"EXPORT: users {len(users)}, reminder rows {len(reminder_rows)}, medications {len(med_rows)}, lists {len(list_rows)}")
    print("PROBLEMS: " + (", ".join(f"{k}: {v}" for k, v in kinds.most_common()) or "none"))
    print(f"BLOCKED THE BOT: {len(blocked_users)} user(s)")
    print(f"DELIVERED: {sent} message(s)/file(s) to {len(settings.admin_telegram_id_set)} admin(s) in Telegram")


asyncio.run(main())
