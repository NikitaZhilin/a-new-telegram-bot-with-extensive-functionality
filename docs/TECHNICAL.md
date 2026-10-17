# Technical Guide

Документ описывает текущее техническое устройство `new_architecture`.

## Назначение

Проект - модульный Telegram productivity bot с web-версией и API. Основные домены:

- списки и общие списки;
- заметки;
- напоминания;
- учет приема лекарств;
- автомобильный журнал;
- настройки, подписки, аналитика активности;
- web-клиент и admin UI.

## Runtime Режимы

CLI entrypoint: `python -B -m src.main`.

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
python -B -m src.main production-check
```

Dry-run проверки:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
python -B -m src.main production-check
```

Особенности:

- `bot` запускает Telegram polling или webhook, если задан `WEBHOOK_URL`;
- `worker` отправляет due reminders и спит `WORKER_INTERVAL` секунд между циклами;
- `api` отдает FastAPI, `/web`, `/admin/ui`, `/me/...`, `/admin/...`;
- `all` запускает `bot`, `worker`, `api` в одном процессе и подходит только для простого локального запуска;
- `init-db` выполняет Alembic migrations до `head`.
- `production-check` валидирует production-настройки Mini App: HTTPS public URL, strict CORS, выключенные docs/test-login и срок действия Telegram `initData`.

## Архитектура

```text
Telegram handlers -> services -> repositories -> db
FastAPI routes    -> services -> repositories -> db
worker            -> services/repositories -> db -> Telegram
```

Основные каталоги:

```text
src/
  api/
    app.py
    auth.py
    user_auth.py
    routes/
      admin.py
      admin_ui.py
      health.py
      me.py
      web.py
  bot/
    app.py
    handlers/
    keyboards/
    states/
  db/
    base.py
    session.py
    models/
  repositories/
  services/
  utils/
  worker/
alembic/
tests/
docs/
```

Правило для разработки: handlers/routes не должны напрямую реализовывать бизнес-логику, если она относится к домену. Логика должна жить в `services`, доступ к данным - в `repositories` или через аккуратно ограниченный service-level SQLAlchemy код.

## Домены

### Lists

Файлы:

- `src/bot/handlers/lists.py`
- `src/services/list_service.py`
- `src/repositories/list_repo.py`

Ключевые возможности:

- CRUD списков и пунктов;
- bulk add;
- personal checklist runs with snapshot items;
- ownership/access checks;
- share-token для копии;
- collaboration-token для общего списка;
- роли `owner`, `editor`, `viewer`.

Checklist-run не использует `ListItem.is_completed`. Исходный список остается источником шаблона, а прохождение хранится отдельно в `checklist_runs` и `checklist_run_items`. Это сохраняет корректную работу общих списков, напоминаний на список и web/API.

### Notes

Файлы:

- `src/bot/handlers/notes.py`
- `src/services/note_service.py`
- `src/repositories/note_repo.py`

Ключевые возможности:

- автономные текстовые заметки без чек-листов и отметок;
- создание, просмотр, редактирование названия, текста и категории;
- поиск по названию и тексту в рамках данных текущего пользователя;
- фильтр по allowlist-категориям: `recipe`, `instruction`, `idea`, `personal`, `other`;
- закрепление через `notes.is_pinned`, сортировка закрепленных выше обычных и фильтр `pinned_only`;
- web/Mini App отображает простое форматирование заметок на клиенте без хранения HTML;
- мягкое удаление через архивирование;
- ownership checks: пользователь видит и меняет только свои заметки;
- отдельный раздел в Telegram, `/web` и `/miniapp`;
- связь с напоминаниями через `reminders.note_id` и `source_module="note"` без превращения заметки в список;
- учет заметок в пользовательской статистике и admin records.

Заметки не смешиваются со списками и напоминаниями. Их задача - хранить текст, который нужно открыть и прочитать: рецепты, инструкции, идеи, справочную информацию. Категория хранится в таблице `notes` как компактное поле `category`, закрепление - как `is_pinned`; свободные теги можно добавить отдельной таблицей позже, если появится реальная потребность. Форматирование в web/Mini App строится из plain text: заголовки, списки и переносы рендерятся только после HTML-экранирования пользовательского текста.

### Reminders

Файлы:

- `src/bot/handlers/reminders.py`
- `src/services/reminder_service.py`
- `src/repositories/reminder_repo.py`
- `src/worker/reminder_worker.py`
- `reminders`
- `reminder_notifications`

Ключевые возможности:

- создание, редактирование, выполнение, отмена, удаление;
- date/time parsing;
- UTC storage и local timezone display;
- отдельные delivery rows для предварительных и финальных уведомлений;
- worker обрабатывает `reminder_notifications`, а не только `reminders.notified_at`;
- repeat rules; monthly repeats keep their anchor day (`repeat_day_of_month`, migration 020), so the 31st is not pulled to the 28th forever;
- «Done» on a repeating reminder schedules the next occurrence; a permanent delivery failure does not end a series;
- optional domain links: `list_id`, `note_id`, `medication_id`, `driver_document_id`;
- worker-cycle без tight loop; retries with savepoints, give-up after 24 h, `RetryAfter` pause, HTML→plain-text retry on formatting errors, real failure reason in `last_error`;
- on start the worker revives repeating series that died without an active next occurrence (`revive_dead_series`);
- timezone change keeps the local clock time of active reminders (`SettingsService.apply_timezone` → `keep_local_time_after_timezone_change`);
- the wizard saves the reminder when the time is chosen; `src/utils/date_parser.extract_reminder_datetime` understands date and time inside the text («завтра в 10 позвонить маме»);
- notification buttons for ordinary reminders: `rem_ack:{id}` (done) and `rem_snooze:{id}:{15|60|1440}` (a new one-time reminder later).

### Medications

Файлы:

- `src/bot/handlers/medications.py`
- `src/services/medication_service.py`
- `src/repositories/medication_repo.py`

Ключевые возможности:

- карточки препаратов;
- дозировка, инструкции, важность;
- daily reminders 1-3 раза в день;
- action window для `принял/пропустил`; buttons under a notification carry the slot (`med_taken:{id}:{unix_ts}`), so a late press marks that dose;
- correcting a mark: pressing the other button on an already marked dose flips the intake status (`MedicationService._correct_mark`);
- snooze;
- архивирование (cancels the medication's reminders together with their pending deliveries);
- saving right after the name in the creation wizard (`med_saved_id` in `user_data`);
- break between courses: `medications.paused_until`, `paused_schedule` (local «HH:MM» times), `pause_notice_reminder_id`, `pause_notice_days` (migration 024). `pause_course` cancels reminders and creates a heads-up reminder N days before; the worker calls `resume_due_courses` every cycle and brings the schedule back on the local date. Marking, snoozing and new schedules are refused during a break;
- weekly summary: `MedicationService.weekly_summary` + `format_weekly_summary`; the worker sends it on Sunday 19:00 user time once per ISO week (`bot_activity_events` marker `weekly_med_summary:YYYY-Www`); `users.weekly_med_summary` (migration 025) switches it off.

### Driver

Файлы:

- `src/bot/handlers/driver.py`
- `src/bot/states/driver.py`
- `src/services/driver_service.py`
- `src/services/vehicle_presets.py`

Ключевые возможности:

- автомобили и presets;
- заправки и fuel stats;
- ручные расходы;
- документы и напоминания по ним;
- service plan;
- ownership checks;
- DB constraints для положительных сумм/литров и корректного пробега.

Подробности: [Driver Guide](DRIVER.md).

### Settings, Activity, Subscriptions

Файлы:

- `src/bot/handlers/settings.py`
- `src/services/settings_service.py`
- `src/services/activity_service.py`
- `src/services/subscription_service.py`
- `src/services/release_info.py`

Ключевые возможности:

- timezone;
- статистика пользователя и admin activity summary;
- testing notice;
- release/version info;
- startup announcement policy;
- базовая модель тарифов.

### Admin Tools: Error Journal, Feedback, Announcements

Files:

- `src/services/error_journal.py` — logging handler on the root logger (and `uvicorn.error`) in bot, worker and api. ERROR records are queued in memory and written by a background task to `error_events` (migration 022), grouped by «type + code place» with a counter; section is detected from the traceback path, `callback_data` or logger name. A resolved kind reopens when it happens again. Records older than 90 days are removed.
- `src/services/feedback_service.py`, `src/bot/handlers/feedback.py` — `/feedback` wizard, `user_feedback` table (migration 023), delivery to `ADMIN_TELEGRAM_IDS` with «Ответить»/«Прочитано», admin screens in «О боте» (journal, inbox). Limit: 10 messages per user per hour.
- `src/services/announcements.py`, `src/bot/handlers/broadcast.py` — admin-only announcement: preview, «only me», checkbox selection or «everyone who has not got it», confirmation, delivery marker `announcement_sent:<id>`. Nothing is broadcast on deploy.
- `src/services/instance_lock.py` — PostgreSQL advisory lock held by the bot process for its whole life; a second copy waits instead of polling Telegram.

All admin screens check rights on every press; buttons are shown only to admins.

### Plan For The Day

`src/services/digest_service.py`, `src/bot/handlers/digest.py`: opt-in (`users.daily_digest`, migration 026). The worker checks every 10 minutes and sends at 08:00 user time, once per local date (`bot_activity_events` marker `daily_digest:YYYY-MM-DD`): active non-medication reminders of the day and daily times of active, not paused medications. Nothing is sent on an empty day.

## API

Health:

```text
GET /health
GET /health/ready
GET /health/live
```

Web:

```text
GET /
GET /web
GET /miniapp
GET /app/info
GET /web/assets/{asset_name}
```

User API:

```text
GET    /me
GET    /me/summary
GET    /me/notes
POST   /me/notes
GET    /me/notes/{note_id}
PATCH  /me/notes/{note_id}
DELETE /me/notes/{note_id}
GET    /me/lists
POST   /me/lists
GET    /me/lists/{list_id}
PATCH  /me/lists/{list_id}
DELETE /me/lists/{list_id}
POST   /me/lists/{list_id}/items
PATCH  /me/lists/items/{item_id}
DELETE /me/lists/items/{item_id}
POST   /me/lists/{list_id}/checklist-runs
GET    /me/checklist-runs/{run_id}
POST   /me/checklist-runs/{run_id}/items/{item_id}/toggle
POST   /me/checklist-runs/{run_id}/check-all
POST   /me/checklist-runs/{run_id}/finish
POST   /me/checklist-runs/{run_id}/cancel
POST   /me/lists/{list_id}/share
GET    /me/lists/{list_id}/members
PATCH  /me/lists/{list_id}/members/{member_id}
DELETE /me/lists/{list_id}/members/{member_id}
GET    /me/reminders
POST   /me/reminders
PATCH  /me/reminders/{reminder_id}
POST   /me/reminders/{reminder_id}/done
POST   /me/reminders/{reminder_id}/cancel
DELETE /me/reminders/{reminder_id}
GET    /me/medications
POST   /me/medications
PATCH  /me/medications/{medication_id}
POST   /me/medications/{medication_id}/taken
POST   /me/medications/{medication_id}/skipped
POST   /me/medications/{medication_id}/pause      {"until": "YYYY-MM-DD", "notice_days": 7}
POST   /me/medications/{medication_id}/resume
DELETE /me/medications/{medication_id}
POST   /me/feedback                               {"kind": "bug|idea|other", "text": "..."}
GET    /me/driver
GET    /me/driver/vehicle-presets
POST   /me/driver/vehicles
PATCH  /me/driver/vehicles/{vehicle_id}
POST   /me/driver/vehicles/{vehicle_id}/service-done
DELETE /me/driver/vehicles/{vehicle_id}
GET    /me/driver/vehicles/{vehicle_id}/fuel
POST   /me/driver/vehicles/{vehicle_id}/fuel
PATCH  /me/driver/fuel/{entry_id}
DELETE /me/driver/fuel/{entry_id}
GET    /me/driver/expenses
POST   /me/driver/expenses
PATCH  /me/driver/expenses/{expense_id}
DELETE /me/driver/expenses/{expense_id}
GET    /me/driver/documents
POST   /me/driver/documents
PATCH  /me/driver/documents/{document_id}
DELETE /me/driver/documents/{document_id}
```

Admin API:

```text
GET /admin/users
GET /admin/users/{user_id}
GET /admin/users/{user_id}/records
GET /admin/activity
GET /admin/funnels
GET /admin/stats
GET /admin/reminders/due
GET /admin/service-status
GET /admin/errors                  ?days=&section=&service=&include_resolved=
GET /admin/errors/{event_id}
POST /admin/errors/{event_id}/resolve
POST /admin/errors/resolve-all
GET /admin/feedback                ?status=new|read|answered
POST /admin/feedback/{feedback_id}/status
POST /admin/feedback/{feedback_id}/reply    {"text": "..."}  (delivered by the bot)
```

Auth:

- Admin API uses `X-Admin-Token`.
- User API uses Telegram WebApp `initData`, `X-Web-Login-Token`, or local test login with `X-Admin-Token` + `X-Web-Test-Telegram-Id` when enabled.

## Database

Database: PostgreSQL with SQLAlchemy async.

Migrations:

```text
001_initial_migration.py
002_current_schema.py
003_driver_schema.py
004_driver_quality_constraints.py
005_domain_sources.py
006_bot_activity_events.py
007_web_login_tokens.py
008_driver_expenses_documents.py
009_vehicle_presets.py
010_driver_document_reminders.py
011_checklist_runs.py
012_medication_intake_snapshots.py
013_service_heartbeats.py
014_driver_journal_entries.py
015_checklist_driver_vehicle.py
016_note_categories.py
017_note_reminders.py
018_pinned_notes.py
019_reminder_notifications.py
020_reminder_repeat_day_of_month.py
021_cancel_orphan_notifications.py
022_error_events.py
023_user_feedback.py
024_medication_course_pause.py
025_weekly_medication_summary.py
026_daily_digest.py
```

Use:

```powershell
python -B -m src.main init-db
```

Do not use `Base.metadata.create_all` for normal new deployments. The compatibility path in `init-db` exists for older local databases that were created before Alembic became the main migration path.

## Local Development

Typical flow:

```powershell
Copy-Item .env.example .env
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main bot
```

Convenience script:

```powershell
.\start-local.ps1
```

## Testing

Main check:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

Additional startup checks:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
python -B -m src.main production-check
```

Test groups:

- API and user API;
- callback registration;
- services/repositories;
- reminders and worker-cycle;
- medications;
- driver service and inputs;
- startup notifications;
- web assets;
- error journal, feedback, announcements;
- medication breaks, mark correction, weekly summary;
- real-usage regressions (`test_user_problems.py`) and wizard exits.

Tests needing PostgreSQL-only features run on SQLite in-memory; the full suite runs in GitHub Actions on every pull request (failed tests are printed as annotations).

## Deployment Model

Production topology:

- one PostgreSQL container;
- one `init-db` one-shot container per deploy;
- one bot polling container;
- one worker container;
- one API container.

Do not scale `bot` polling with one Telegram token: the bot holds a PostgreSQL advisory lock, so a second copy waits and logs why instead of stealing updates. Run one worker.

Full deployment instructions: [Deployment](DEPLOYMENT.md).

## Security Notes

- Do not commit `.env`, `.env.prod`, tokens, passwords, SSH keys, database dumps, logs, or backups.
- Keep PostgreSQL bound to `127.0.0.1`.
- Keep API bound to `127.0.0.1` in production unless it is behind HTTPS/proxy/firewall.
- Keep `API_DOCS_ENABLED=false` in production.
- Keep `CORS_ORIGINS` strict in production.
- Use only one `COMPOSE_PROJECT_NAME` per bot on a shared VPS.
- Activity analytics must not store raw message text.
