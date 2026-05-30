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
- repeat rules;
- optional domain links: `list_id`, `note_id`, `medication_id`, `driver_document_id`;
- worker-cycle без tight loop.

### Medications

Файлы:

- `src/bot/handlers/medications.py`
- `src/services/medication_service.py`
- `src/repositories/medication_repo.py`

Ключевые возможности:

- карточки препаратов;
- дозировка, инструкции, важность;
- daily reminders 1-3 раза в день;
- action window для `принял/пропустил`;
- snooze;
- архивирование.

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
DELETE /me/medications/{medication_id}
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
- web assets.

## Deployment Model

Production topology:

- one PostgreSQL container;
- one `init-db` one-shot container per deploy;
- one bot polling container;
- one worker container;
- one API container.

Do not scale `bot` polling with one Telegram token. Do not run multiple workers unless idempotency and locking are added.

Full deployment instructions: [Deployment](DEPLOYMENT.md).

## Security Notes

- Do not commit `.env`, `.env.prod`, tokens, passwords, SSH keys, database dumps, logs, or backups.
- Keep PostgreSQL bound to `127.0.0.1`.
- Keep API bound to `127.0.0.1` in production unless it is behind HTTPS/proxy/firewall.
- Keep `API_DOCS_ENABLED=false` in production.
- Keep `CORS_ORIGINS` strict in production.
- Use only one `COMPOSE_PROJECT_NAME` per bot on a shared VPS.
- Activity analytics must not store raw message text.
