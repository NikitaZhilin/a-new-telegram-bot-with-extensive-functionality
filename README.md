# RememberMe Bot

Telegram bot for todo/shopping lists, medication intake reminders, reminders, and basic user settings.

## Requirements

- Python 3.11+
- Docker Desktop or a local PostgreSQL server
- Telegram bot token from BotFather

## Git

For first publish and clone workflow, see [GIT_SETUP.md](GIT_SETUP.md).
For VPS deployment, see [DEPLOY_VPS.md](DEPLOY_VPS.md).

## Environment

Copy `.env.example` to `.env` and fill in local values:

```powershell
Copy-Item .env.example .env
```

If another PostgreSQL already uses `5432`, use `5433`:

```env
POSTGRES_PORT=5433
POSTGRES_BIND_HOST=127.0.0.1
DATABASE_URL=postgresql+asyncpg://postgres:your-secure-password-here@localhost:5433/rememberme
```

Do not commit `.env`; it is ignored by `.gitignore`.

For public testing, users can simply open:

```text
https://t.me/tg_napominalka2_bot
```

Each Telegram account gets its own isolated user records. Admin visibility is handled through the admin API and admin Telegram IDs:

```env
BOT_USERNAME=tg_napominalka2_bot
ADMIN_TELEGRAM_IDS=123456789
DEFAULT_SUBSCRIPTION_PLAN=free
```

`ADMIN_TELEGRAM_IDS` is a comma-separated list of Telegram user IDs. Do not put bot tokens or payment secrets into source code.

Subscriptions are currently in debug mode: every new user receives `DEFAULT_SUBSCRIPTION_PLAN`, core features remain available, and `⚙️ Настройки -> 💳 Подписка` shows the effective plan. This prepares the bot for paid feature gates without connecting real payments yet.

Local API docs and permissive CORS are enabled by default for development:

```env
API_DOCS_ENABLED=true
CORS_ORIGINS=*
```

For a public deployment, prefer a restricted API surface:

```env
API_DOCS_ENABLED=false
CORS_ORIGINS=https://your-admin.example.com
API_BIND_HOST=127.0.0.1
```

## PostgreSQL

Start only the database:

```powershell
$env:POSTGRES_PORT="5433"
docker-compose up -d postgres
```

Check it:

```powershell
docker ps --filter name=rememberme-postgres
```

Initialize tables:

```powershell
python -B -m src.main init-db
```

For managed/staged deployments, use Alembic migrations instead of ad-hoc schema creation:

```powershell
alembic upgrade head
```

If your `.env` still points to `5432`, update `DATABASE_URL` before running `init-db`.

## Safe Startup Checks

These commands do not call Telegram API, do not start polling, and do not send messages:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

Run tests:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

## Run Locally

Recommended automated startup:

```powershell
.\start-local.ps1
```

This loads `.env`, starts PostgreSQL through Docker Compose, waits until the database is healthy, initializes the schema, runs a safe dry-run, and then starts API, bot polling, and the reminder worker together.

Useful variants:

```powershell
.\start-local.ps1 -DryRunOnly
.\start-local.ps1 -RunTests
.\start-local.ps1 -Mode bot
.\start-local.ps1 -Mode worker
.\start-local.ps1 -SkipDocker
```

For a double-click launch on Windows, run:

```powershell
.\run-bot.cmd
```

## Background And Autostart

After code changes, restart the local bot in the background:

```powershell
.\restart-background.ps1
```

This stops the previous background process by PID, starts `start-local.ps1` in a hidden PowerShell window, and writes logs to:

```text
logs\rememberme-background.out.log
logs\rememberme-background.err.log
```

Manual background controls:

```powershell
.\start-background.ps1
.\stop-background.ps1
.\restart-background.ps1 -RunTests
```

Install Windows Task Scheduler autostart for the current user logon:

```powershell
.\install-autostart-task.ps1
```

Install autostart at system startup instead:

```powershell
.\install-autostart-task.ps1 -AtStartup
```

Remove the scheduled task:

```powershell
.\uninstall-autostart-task.ps1
```

The scheduled task uses `.env`; tokens and secrets should stay there, not in code or task arguments.

API:

```powershell
python -B -m src.main api
```

Bot polling:

```powershell
python -B -m src.main bot
```

Worker:

```powershell
python -B -m src.main worker
```

Use `bot` only with a real `BOT_TOKEN`. The bot process will contact Telegram and start polling.

## Manual Bot Smoke Test

1. Send `/start`.
2. Open `📋 Списки`.
3. Create a list, add one item, add multiple items, open an item, toggle it, edit it, delete it, rename the list, then delete the list.
4. In a list, press `📤 Поделиться`. From another Telegram account, either import a copy with `/import_list TOKEN` or join the same shared list with `/join_list TOKEN`.
5. Open `💊 Лекарства`.
6. Add a medication, choose dosage/instructions/importance, set 1-3 daily reminder times manually, then test `✅ Принял`, `⏭ Пропустил`, and `↩️ Отложить 15 мин`.
7. Open `⏰ Напоминания`.
8. Create a reminder with a preset time, open it, mark done/cancel/delete, and switch active/history filters.
9. Open `⚙️ Настройки`.
10. Change timezone with a preset and with manual input.
11. Open `💳 Подписка` and check that the current plan is shown.
12. Use `👥 Поделиться ботом` to get a bot invite link if `BOT_USERNAME` is configured.
13. Use `🏠 В меню`, `⬅️ Назад`, and `❌ Отмена` during flows.

## Sharing And Multi-User Notes

- Personal lists, reminders, and medications are isolated by Telegram user.
- Admin users can support/debug users through the admin API, but normal bot users do not see each other's records unless a list is explicitly shared.
- List sharing supports two modes: private copy with `/import_list TOKEN`, or true shared access with `/join_list TOKEN`.
- Shared list roles are `editor` and `viewer`. Editors can add/edit/toggle/delete items. Viewers can only read. Only the owner can rename, delete, or create invite links.
- Owners can open `👥 Участники` from a list to view members, change `editor/viewer` roles, or revoke access.
- Share tokens are time-limited and usage-limited. If `BOT_USERNAME` is set, the bot also shows a Telegram deep link.
- For manual testing, use two Telegram accounts and send `/join_list TOKEN` or `/import_list TOKEN` from the second account.

## Current Limits

- Reminder edit from the detail screen is intentionally hidden for now.
- Notes are currently removed from the user-facing bot menu.
- Medication reminders are a tracking aid only. The bot does not recommend dosages, courses, or substitutions.
- Medication courses, formal start/end dates, multiple daily times as one course, and doctor/export reports are not fully modeled yet.
- Shared list member management exists for current members. There is no separate audit log of member actions yet.
- Subscription plans are modeled for monetization, but real Telegram payments/payment-provider integration is not connected yet.
