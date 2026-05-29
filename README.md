# Telegram Productivity Bot

[Русский](#ru) | [English](#en)

<a id="ru"></a>

## Русский

Модульный Telegram-бот для личной организации: списки, заметки, напоминания, прием лекарств, автомобильный журнал, web-версия, admin UI и основа для подписок.

README намеренно не содержит токенов, адресов серверов, приватных путей, имен production-ботов и других чувствительных данных.

### Документация

- [Руководство пользователя](docs/USER_GUIDE.md)
- [Техническое руководство](docs/TECHNICAL.md)
- [Водительский раздел](docs/DRIVER.md)
- [Деплой](docs/DEPLOYMENT.md)
- [Git workflow](docs/GIT.md)
- [Web/App roadmap](docs/WEB_APP_ROADMAP.md)
- [Индекс документации](docs/README.md)

Старые отчеты этапов и provider-specific заметки лежат в `docs/archive` и не являются инструкциями запуска.

### Что Умеет Бот

- Списки: личные и общие списки, пункты, bulk add, голосовое создание/пополнение списка, интерактивное прохождение чек-листа, роли `owner/editor/viewer`, токены копии и приглашения.
- Заметки: автономные текстовые записи без чек-листов и отметок, просмотр, редактирование и архивирование.
- Напоминания: быстрые даты/время, ручные фразы, повторы, редактирование, выполнение, отмена.
- Лекарства: карточки препаратов, дозировка, инструкция, важность, напоминания 1-3 раза в день, отметки приема.
- Водитель: авто, presets, пробег, ТО, заправки, расходы, документы, напоминания по документам, статистика.
- Настройки: timezone, статистика, подписка, web-ключ, версия, changelog, служебный статус.
- Web: `/web` для пользовательских сценариев и `/admin/ui` для администрирования.

### Архитектура

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

Основные каталоги:

```text
src/api          FastAPI routes, web, admin UI
src/bot          Telegram handlers, keyboards, states
src/db           SQLAlchemy models/session/base
src/repositories Data access layer
src/services     Business logic
src/worker       Reminder worker
tests            Regression tests
alembic          Database migrations
docs             Current documentation
```

### Стек

Python 3.11+, python-telegram-bot, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, Pydantic v2, Docker, pytest.

### Быстрый Старт

1. Создать `.env`:

```powershell
Copy-Item .env.example .env
```

2. Заполнить обязательные значения:

```env
BOT_TOKEN=...
BOT_USERNAME=...
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DB=rememberme
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@localhost:5432/rememberme
WEB_PUBLIC_URL=http://127.0.0.1:8000
```

`5432` - стандартный локальный порт PostgreSQL. Если он уже занят, используйте `POSTGRES_PORT=5433` и такой же порт в `DATABASE_URL`.

Голосовое создание списков опционально. Для него включите:

```env
VOICE_TRANSCRIPTION_ENABLED=true
OPENAI_API_KEY=...
```

3. Запустить локально:

```powershell
.\start-local.ps1
```

Ручной вариант:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

Полный Docker Compose:

```powershell
docker-compose up -d
```

### Режимы Запуска

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

Dry-run без Telegram polling и отправки сообщений:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

### Web И Admin

```text
http://127.0.0.1:8000/web
http://127.0.0.1:8000/admin/ui
```

Web-вход для пользователя: в Telegram открыть `Настройки -> Web-версия`, получить персональный ключ и вставить его на `/web`. Если задан `WEB_PUBLIC_URL`, бот выдаст прямую ссылку `/web?token=...`.

Admin UI использует `X-Admin-Token`. Токен вводится в браузере и не хранится на сервере.

### Проверки

```powershell
python -B -m pytest -p no:cacheprovider tests
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
docker-compose config --quiet
```

### Безопасность

- не коммитьте `.env`, `.env.prod`, токены, пароли, SSH-ключи, дампы БД, логи и backup;
- PostgreSQL держите на `127.0.0.1`;
- production API держите на `127.0.0.1`, если нет HTTPS/proxy/firewall;
- для production используйте `API_DOCS_ENABLED=false` и строгий `CORS_ORIGINS`;
- polling bot запускайте в одном экземпляре на один Telegram token;
- worker запускайте в одном экземпляре, чтобы не дублировать уведомления;
- перед рискованными миграциями делайте backup БД.

<a id="en"></a>

## English

Modular Telegram productivity bot for personal organization: lists, notes, reminders, medication tracking, driver journal, web version, admin UI, and a foundation for subscriptions.

This README intentionally avoids tokens, server addresses, private paths, production bot names, and other sensitive details.

### Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Technical Guide](docs/TECHNICAL.md)
- [Driver Guide](docs/DRIVER.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Git workflow](docs/GIT.md)
- [Web/App roadmap](docs/WEB_APP_ROADMAP.md)
- [Documentation index](docs/README.md)

Old stage reports and provider-specific notes are kept in `docs/archive` and are not launch instructions.

### Features

- Lists: personal and shared lists, items, bulk add, voice-to-list creation/appending, interactive checklist runs, `owner/editor/viewer` roles, copy and collaboration tokens.
- Notes: standalone text records without checklist state, with viewing, editing, and archiving.
- Reminders: quick date/time presets, natural phrases, repeats, editing, done/cancel/delete actions.
- Medications: medication cards, dosage, instructions, importance, 1-3 daily reminders, intake tracking.
- Driver: vehicles, presets, mileage, service plan, fuel, expenses, documents, document reminders, statistics.
- Settings: timezone, stats, subscription, web key, version, changelog, technical status.
- Web: `/web` for user flows and `/admin/ui` for administration.

### Architecture

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

Main directories:

```text
src/api          FastAPI routes, web, admin UI
src/bot          Telegram handlers, keyboards, states
src/db           SQLAlchemy models/session/base
src/repositories Data access layer
src/services     Business logic
src/worker       Reminder worker
tests            Regression tests
alembic          Database migrations
docs             Current documentation
```

### Stack

Python 3.11+, python-telegram-bot, FastAPI, SQLAlchemy async, PostgreSQL, Alembic, Pydantic v2, Docker, pytest.

### Quick Start

1. Create `.env`:

```powershell
Copy-Item .env.example .env
```

2. Fill required values:

```env
BOT_TOKEN=...
BOT_USERNAME=...
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DB=rememberme
POSTGRES_PORT=5432
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@localhost:5432/rememberme
WEB_PUBLIC_URL=http://127.0.0.1:8000
```

`5432` is the default local PostgreSQL port. If it is already occupied, use `POSTGRES_PORT=5433` and the same port in `DATABASE_URL`.

Voice-to-list transcription is optional. Enable it with:

```env
VOICE_TRANSCRIPTION_ENABLED=true
OPENAI_API_KEY=...
```

3. Start locally:

```powershell
.\start-local.ps1
```

Manual flow:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

Full Docker Compose:

```powershell
docker-compose up -d
```

### Runtime Modes

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

Dry-run without Telegram polling or message sending:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

### Web And Admin

```text
http://127.0.0.1:8000/web
http://127.0.0.1:8000/admin/ui
```

User web login: open `Settings -> Web version` in Telegram, get a personal key, and paste it on `/web`. If `WEB_PUBLIC_URL` is configured, the bot sends a direct `/web?token=...` link.

Admin UI uses `X-Admin-Token`. The token is entered in the browser and is not stored on the server.

### Checks

```powershell
python -B -m pytest -p no:cacheprovider tests
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
docker-compose config --quiet
```

### Security

- do not commit `.env`, `.env.prod`, tokens, passwords, SSH keys, database dumps, logs, or backups;
- keep PostgreSQL bound to `127.0.0.1`;
- keep production API bound to `127.0.0.1` unless it is behind HTTPS/proxy/firewall;
- use `API_DOCS_ENABLED=false` and strict `CORS_ORIGINS` in production;
- run one polling bot instance per Telegram token;
- run one worker instance to avoid duplicate notifications;
- back up the database before risky migrations.
