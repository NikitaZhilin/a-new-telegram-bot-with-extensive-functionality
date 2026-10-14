"""Full per-user report WITH content, for the bot owner only.

Runs inside the api container:
    docker exec -i <prefix>-api python - < scripts/users-content-report.py
Set REPORT_DRY_RUN=1 to only check the recipients.

Read-only. Contains users' private data (reminder texts, notes, lists,
medications), so it is sent ONLY to ADMIN_TELEGRAM_IDS, and the script
refuses to send if that list looks wrong. stdout (public CI logs) gets
anonymous numbers and masked recipient IDs only.
"""

import asyncio
import html
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

from src.config import settings  # noqa: E402
from src.db.models import (  # noqa: E402
    BotActivityEvent,
    ChecklistRun,
    DriverDocument,
    DriverExpense,
    DriverFuelEntry,
    DriverVehicle,
    ListItem,
    ListMember,
    Medication,
    MedicationIntake,
    Note,
    Reminder,
    ReminderNotification,
    TodoList,
    User,
)
from src.db.session import async_session_maker  # noqa: E402
from src.services.activity_service import format_event_label  # noqa: E402

DEFAULT_TZ = settings.TIMEZONE_DEFAULT or "Europe/Moscow"
MAX_RECIPIENTS = 3
SECTION = {"general": "Напоминания", "list": "Списки", "note": "Заметки", "medication": "Лекарства",
           "driver": "Водитель"}
REPEAT = {"none": "разово", "daily": "ежедневно", "weekly": "еженедельно", "monthly": "ежемесячно"}
STATUS = {"active": "активно", "done": "выполнено", "canceled": "отменено", "missed": "пропущено"}
MED_WORDS = re.compile(r"таблет|капсул|витамин|лекарств|препарат|\bмг\b|капл|укол|инъекц|сироп|антибиот|принять|выпить|пить ", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-–—•*+]|\d+[.)]|☐|✅|⬜)\s*\S", re.M)


def _v(value):
    return (value.value if hasattr(value, "value") else str(value)).lower()


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _tz(stored):
    name = DEFAULT_TZ if not stored or (stored == "UTC" and DEFAULT_TZ != "UTC") else stored
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _fmt(value, tz, with_time=True):
    if not value:
        return "—"
    return _utc(value).astimezone(tz).strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


def e(value) -> str:
    return html.escape(str(value or ""))


def _offsets(minutes):
    labels = []
    for m in sorted(set(minutes), reverse=True):
        if m == 0:
            labels.append("в момент")
        elif m % 1440 == 0:
            labels.append(f"за {m // 1440} дн.")
        elif m % 60 == 0:
            labels.append(f"за {m // 60} ч")
        else:
            labels.append(f"за {m} мин")
    return ", ".join(labels) or "в момент"


def _check_recipients():
    recipients = sorted(settings.admin_telegram_id_set)
    if not recipients:
        raise SystemExit("REFUSED: ADMIN_TELEGRAM_IDS is empty")
    if len(recipients) > MAX_RECIPIENTS:
        raise SystemExit(f"REFUSED: {len(recipients)} recipients configured, max {MAX_RECIPIENTS}")
    return recipients


async def main() -> None:
    recipients = _check_recipients()
    masked = ", ".join("***" + str(r)[-3:] for r in recipients)
    print(f"RECIPIENTS: {len(recipients)} (Telegram ID ends with {masked}); only ADMIN_TELEGRAM_IDS are used")
    now = datetime.now(timezone.utc)

    async with async_session_maker() as session:
        async def all_of(model, *order):
            return (await session.execute(select(model).order_by(*order))).scalars().all()

        users = await all_of(User, User.created_at)
        known_ids = {u.telegram_id for u in users}
        for r in recipients:
            if r not in known_ids:
                print(f"NOTE: recipient ***{str(r)[-3:]} has not started the bot")
        reminders = await all_of(Reminder, Reminder.remind_at_utc)
        notifications = defaultdict(list)
        for n in await all_of(ReminderNotification, ReminderNotification.id):
            notifications[n.reminder_id].append(n)
        meds = await all_of(Medication, Medication.id)
        intakes = defaultdict(list)
        for i in await all_of(MedicationIntake, MedicationIntake.taken_at_utc):
            intakes[i.medication_id].append(i)
        lists = await all_of(TodoList, TodoList.id)
        items = defaultdict(list)
        for it in await all_of(ListItem, ListItem.list_id, ListItem.position, ListItem.id):
            items[it.list_id].append(it)
        members = await all_of(ListMember, ListMember.id)
        runs = await all_of(ChecklistRun, ChecklistRun.id)
        notes = await all_of(Note, Note.id)
        cars = await all_of(DriverVehicle, DriverVehicle.id)
        fuel = await all_of(DriverFuelEntry, DriverFuelEntry.filled_at_utc)
        docs = await all_of(DriverDocument, DriverDocument.id)
        expenses = await all_of(DriverExpense, DriverExpense.spent_at_utc)
        events = (await session.execute(
            select(BotActivityEvent.user_id, BotActivityEvent.event_name, BotActivityEvent.created_at)
            .where(BotActivityEvent.user_id.is_not(None), BotActivityEvent.domain != "system")
            .order_by(BotActivityEvent.created_at)
        )).all()

    by_user = defaultdict(lambda: defaultdict(list))
    for kind, rows in (("reminders", reminders), ("meds", meds), ("lists", lists), ("notes", notes),
                       ("cars", cars), ("fuel", fuel), ("docs", docs), ("expenses", expenses), ("runs", runs)):
        for row in rows:
            by_user[row.user_id][kind].append(row)
    for user_id, name, created_at in events:
        by_user[user_id]["events"].append((name, created_at))
    list_title = {t.id: t.title for t in lists}
    note_title = {n.id: n.title for n in notes}
    med_name = {m.id: m.name for m in meds}
    shared_with = defaultdict(list)
    for m in members:
        shared_with[m.user_id].append(m)
    user_name = {u.id: (" ".join(p for p in (u.first_name, u.last_name) if p) or "без имени")
                 + (f" (@{u.username})" if u.username else "") for u in users}

    stats = Counter()
    sections_html = []
    toc = []
    for index, u in enumerate(users, start=1):
        tz = _tz(u.timezone)
        data = by_user.get(u.id, {})
        evs = data.get("events", [])
        hints = []
        parts = []

        # --- reminders, grouped: one daily repeat creates one row per day
        groups = defaultdict(list)
        for r in data.get("reminders", []):
            key = (r.source_module, r.title or "", r.text, _v(r.repeat_rule), r.list_id, r.note_id, r.medication_id,
                   r.driver_document_id)
            groups[key].append(r)
        rem_rows = []
        manual_repeats = Counter()
        for (source, title, text, repeat, list_id, note_id, med_id, doc_id), rs in groups.items():
            statuses = Counter(_v(r.status) for r in rs)
            ns = [n for r in rs for n in notifications.get(r.id, [])]
            sent = sum(1 for n in ns if _v(n.status) == "sent")
            failed = [n for n in ns if _v(n.status) == "failed"]
            active = [r for r in rs if _v(r.status) == "active"]
            pending_future = sorted(_utc(n.notify_at_utc) for r in active for n in notifications.get(r.id, [])
                                    if _v(n.status) == "pending" and _utc(n.notify_at_utc) > now)
            offsets = [n.offset_minutes for n in notifications.get(rs[-1].id, [])]
            if active:
                verdict = (f"✅ следующее {_fmt(pending_future[0], tz)}" if pending_future
                           else "❌ активно, но уведомление не запланировано")
            elif failed:
                verdict = "❌ не доставлено: " + e((failed[-1].last_error or "")[:160])
            else:
                verdict = "завершено"
            linked = (f"список «{e(list_title.get(list_id, '?'))}»" if list_id else
                      f"заметка «{e(note_title.get(note_id, '?'))}»" if note_id else
                      f"лекарство «{e(med_name.get(med_id, '?'))}»" if med_id else
                      "документ авто" if doc_id else "")
            history = ", ".join(f"{STATUS.get(k, k)} {v}" for k, v in statuses.items())
            rem_rows.append(
                f"<tr><td>{e(SECTION.get(source, source))}</td><td><b>{e(title)}</b> {e(text)}"
                f"{'<br><small>' + linked + '</small>' if linked else ''}</td>"
                f"<td>{REPEAT.get(repeat, repeat)}<br><small>{_offsets(offsets)}</small></td>"
                f"<td>{_fmt(rs[0].remind_at_utc, tz)}<br>…{_fmt(rs[-1].remind_at_utc, tz)}</td>"
                f"<td>{len(rs)} раз(а): {history}<br><small>доставлено {sent}, ошибок {len(failed)}</small></td>"
                f"<td>{verdict}</td></tr>"
            )
            if source == "general" and not med_id and MED_WORDS.search(f"{title} {text}"):
                hints.append(f"Напоминание «{e(text[:60])}» похоже на приём лекарства — в разделе «Лекарства» "
                             "есть отметки «принял/пропустил» и учёт приёма.")
            if repeat == "none":
                manual_repeats[text.strip().lower()] += len(rs)
            stats["reminder_groups"] += 1
        for text, count in manual_repeats.items():
            if count >= 3:
                hints.append(f"Разовое напоминание «{e(text[:60])}» создано вручную {count} раз — "
                             "можно один раз поставить повтор.")
        if rem_rows:
            parts.append("<h3>⏰ Напоминания</h3><table><tr><th>Раздел</th><th>Текст</th><th>Повтор / уведомления</th>"
                         "<th>Первое … последнее</th><th>История</th><th>Работает?</th></tr>" + "".join(rem_rows)
                         + "</table>")

        # --- medications
        med_rows = []
        for m in data.get("meds", []):
            schedule = sorted({_utc(r.remind_at_utc).astimezone(tz).strftime("%H:%M")
                               for r in data.get("reminders", [])
                               if r.medication_id == m.id and _v(r.status) == "active" and _v(r.repeat_rule) == "daily"})
            marks = intakes.get(m.id, [])
            recent = [i for i in marks if _utc(i.taken_at_utc) > now - timedelta(days=14)]
            taken = sum(1 for i in recent if _v(i.status) != "skipped")
            skipped = len(recent) - taken
            planned = len(schedule) * 14
            delivered = sum(1 for r in data.get("reminders", []) if r.medication_id == m.id
                            for n in notifications.get(r.id, []) if _v(n.status) == "sent"
                            and _utc(n.notify_at_utc) > now - timedelta(days=14))
            if not m.is_active:
                verdict = "в архиве"
            elif not schedule:
                verdict = "⚠️ нет времени приёма — напоминания не приходят"
                hints.append(f"Лекарство «{e(m.name)}» без времени приёма — бот о нём не напоминает.")
            else:
                verdict = f"✅ напоминания в {', '.join(schedule)}"
                if planned and delivered >= 5 and (taken + skipped) < delivered * 0.3:
                    hints.append(f"По «{e(m.name)}» напоминания приходят ({delivered} за 14 дн.), но приём почти "
                                 f"не отмечается ({taken + skipped}).")
            med_rows.append(
                f"<tr><td><b>{e(m.name)}</b><br><small>{e(m.dosage)} {e(m.instructions)}</small></td>"
                f"<td>{e(m.importance)}</td><td>{', '.join(schedule) or '—'}</td>"
                f"<td>принял {taken}, пропустил {skipped} из ~{planned or '—'}; всего отметок {len(marks)}</td>"
                f"<td>{_fmt(marks[-1].taken_at_utc, tz) if marks else '—'}</td><td>{verdict}</td></tr>"
            )
        if med_rows:
            parts.append("<h3>💊 Лекарства</h3><table><tr><th>Лекарство</th><th>Важность</th><th>Время</th>"
                         "<th>За 14 дней</th><th>Последняя отметка</th><th>Работает?</th></tr>"
                         + "".join(med_rows) + "</table>")

        # --- lists
        list_blocks = []
        for t in data.get("lists", []):
            its = items.get(t.id, [])
            done = sum(1 for it in its if it.is_completed)
            list_runs = [r for r in runs if r.source_list_id == t.id]
            completed = sum(1 for r in list_runs if r.status == "completed")
            shared = sum(1 for m in members if m.list_id == t.id)
            shown = "".join(f"<li>{'✅' if it.is_completed else '⬜'} {e(it.text)}</li>" for it in its[:40])
            more = f"<li>… ещё {len(its) - 40}</li>" if len(its) > 40 else ""
            list_blocks.append(
                f"<details><summary><b>{e(t.title)}</b> · {e(SECTION.get(t.source_module, t.source_module))} · "
                f"пунктов {len(its)}, отмечено {done}, чек-листов пройдено {completed}"
                f"{f', участников {shared}' if shared else ''} · изменён {_fmt(t.updated_at, tz, False)}</summary>"
                f"<ul>{shown}{more}</ul></details>"
            )
        for m in shared_with.get(u.id, []):
            list_blocks.append(f"<p>👥 участник чужого списка «{e(list_title.get(m.list_id, '?'))}» ({e(m.role)})</p>")
        if list_blocks:
            parts.append("<h3>📋 Списки</h3>" + "".join(list_blocks))

        # --- notes
        note_blocks = []
        for n in data.get("notes", []):
            text = n.text or ""
            if len(LIST_LINE.findall(text)) >= 3:
                hints.append(f"Заметка «{e(n.title)}» оформлена как список — в «Списках» пункты можно отмечать.")
            note_blocks.append(
                f"<details><summary><b>{e(n.title)}</b> · {e(n.category)}{' · 📌' if n.is_pinned else ''}"
                f"{' · в архиве' if n.is_archived else ''} · {_fmt(n.updated_at, tz, False)}</summary>"
                f"<pre>{e(text[:1500])}{'…' if len(text) > 1500 else ''}</pre></details>"
            )
        if note_blocks:
            parts.append("<h3>📝 Заметки</h3>" + "".join(note_blocks))

        # --- driver
        driver = []
        for c in data.get("cars", []):
            car_fuel = [f for f in data.get("fuel", []) if f.vehicle_id == c.id]
            driver.append(f"<p>🚗 <b>{e(c.title)}</b> {e(c.make)} {e(c.model)} {e(c.year)} · пробег "
                          f"{c.current_mileage_km} км · заправок {len(car_fuel)} · последнее ТО "
                          f"{_fmt(c.last_service_at_utc, tz, False)}</p>")
        for d in data.get("docs", []):
            driver.append(f"<p>📄 {e(d.title)} ({e(d.document_type)}) до {_fmt(d.expires_at_utc, tz, False)}, "
                          f"напомнить за {d.remind_before_days} дн.{'' if d.is_active else ' · неактивен'}</p>")
        if data.get("expenses"):
            total = sum(x.amount or 0 for x in data["expenses"])
            driver.append(f"<p>💰 расходов {len(data['expenses'])} на {total:.0f} ₽</p>")
        if driver:
            parts.append("<h3>🚗 Водитель</h3>" + "".join(driver))

        # --- timeline
        if evs:
            days = sorted({_utc(c).astimezone(tz).date() for _, c in evs})
            tail = evs[-40:]
            timeline = "".join(f"<li>{_fmt(c, tz)} — {e(format_event_label(n))}</li>" for n, c in tail)
            parts.append(f"<h3>🕒 Последние действия</h3><p>Активен {len(days)} дн., всего действий {len(evs)}. "
                         f"Показаны последние {len(tail)}:</p><details><summary>открыть</summary><ul>{timeline}</ul></details>")

        if hints:
            parts.insert(0, "<div class='hint'><b>💡 Подсказки</b><ul>" + "".join(f"<li>{h}</li>" for h in hints)
                         + "</ul></div>")
        stats["hints"] += len(hints)
        last = _fmt(evs[-1][1], tz, False) if evs else "—"
        anchor = f"u{index}"
        toc.append(f"<li><a href='#{anchor}'>{index}. {e(user_name[u.id])}</a> — последний раз {last}"
                   f"{f' · 💡 {len(hints)}' if hints else ''}</li>")
        sections_html.append(
            f"<section id='{anchor}'><h2>{index}. {e(user_name[u.id])}</h2>"
            f"<p class='meta'>Telegram ID {u.telegram_id} · пояс {e(u.timezone)} · пришёл {_fmt(u.created_at, tz, False)}"
            f" · последний раз {last}</p>"
            + ("".join(parts) or "<p>Ничего не создавал.</p>") + "</section>"
        )

    page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Пользователи бота</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:16px;max-width:1100px;color:#1d1d1f;background:#fff}}
h2{{border-top:2px solid #ddd;padding-top:16px;margin-top:32px}} h3{{margin:18px 0 6px}}
table{{border-collapse:collapse;width:100%;font-size:14px}} td,th{{border:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}}
th{{background:#f4f4f6}} small,.meta{{color:#666}} pre{{white-space:pre-wrap;background:#f7f7f7;padding:8px}}
.hint{{background:#fff7e0;border:1px solid #f0d58a;padding:8px 12px;border-radius:8px}}
details{{margin:4px 0}} summary{{cursor:pointer}}
@media (prefers-color-scheme: dark){{body{{background:#121212;color:#eee}} th{{background:#222}} td,th{{border-color:#333}}
pre{{background:#1d1d1d}} .hint{{background:#2b2410;border-color:#6b5a1e}} small,.meta{{color:#aaa}} a{{color:#8ab4f8}}}}
</style></head><body>
<h1>Пользователи бота — {now.astimezone(ZoneInfo(DEFAULT_TZ)):%d.%m.%Y %H:%M}</h1>
<p>Конфиденциально: содержит личные записи пользователей. Не пересылайте.</p>
<ol>{''.join(toc)}</ol>{''.join(sections_html)}</body></html>"""

    if os.environ.get("REPORT_DRY_RUN") == "1":
        print("DRY RUN: nothing sent")
        return

    sent = 0
    filename = f"users_{now.astimezone(ZoneInfo(DEFAULT_TZ)):%Y-%m-%d}.html"
    async with httpx.AsyncClient(timeout=60) as client:
        for chat_id in recipients:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendDocument",
                data={"chat_id": str(chat_id), "caption": (
                    "🔒 Полный отчёт по пользователям с содержимым записей. Откройте файл в браузере. "
                    "Содержит личные данные — не пересылайте."
                )},
                files={"document": (filename, page.encode("utf-8"), "text/html")},
            )
            sent += response.status_code == 200
            if response.status_code != 200:
                print(f"SEND ERROR: {response.status_code}")

    print(f"REPORT: users {len(users)}, reminder groups {stats['reminder_groups']}, hints {stats['hints']}, "
          f"size {len(page) // 1024} KB")
    print(f"DELIVERED: {sent} file(s) to {len(recipients)} admin recipient(s); other users received nothing")


asyncio.run(main())
