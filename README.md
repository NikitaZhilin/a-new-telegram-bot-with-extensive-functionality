# Telegram Productivity Bot

[Русский](#ru) | [English](#en)

<a id="ru"></a>

## Русский

Telegram Productivity Bot - модульный Telegram-бот для личной организации: списки, напоминания, прием лекарств, автомобильный журнал, настройки пользователя и основа для платных возможностей.

README намеренно не содержит токенов, адресов серверов, приватных путей, имен production-ботов и других данных, которые могут раскрывать конкретное размещение проекта.

### Возможности

**Списки**

- личные списки дел и покупок;
- добавление пунктов по одному или пачкой;
- отметка выполненного, редактирование и удаление пунктов;
- переименование и удаление списков с подтверждением;
- пагинация;
- напоминание, привязанное к списку;
- совместные списки с ролями `owner`, `editor`, `viewer`;
- импорт копии списка и подключение к общему списку по токену.

**Напоминания**

- создание напоминаний через кнопки и текстовый ввод;
- быстрый выбор даты и времени;
- ручной ввод фраз вроде “завтра 10” или “через 2 часа”;
- повторы: ежедневно, еженедельно, ежемесячно;
- активные и завершенные напоминания;
- выполнение, отмена и удаление;
- хранение времени в UTC и отображение в часовом поясе пользователя.

**Прием лекарств**

- карточки препаратов;
- дозировка и инструкции через кнопки или текст;
- важность: БАД, обычное, важное, критичное;
- напоминания 1, 2 или 3 раза в день с ручным временем;
- отметки “принял”, “пропустил”, “отложить”;
- скрытие кнопки приема до следующего актуального окна.

Бот только помогает вести учет и не заменяет медицинские рекомендации.

**Для водителя**

- профиль авто;
- пошаговое добавление и редактирование авто;
- текущий пробег;
- интервал ТО по пробегу и по месяцам;
- отметка выполненного ТО;
- расчет следующего ТО по пробегу и дате;
- журнал заправок;
- пошаговое добавление и редактирование заправок;
- история заправок по авто;
- удаление авто и заправок с подтверждением;
- расчет цены за литр, расхода и стоимости километра;
- учет неполных заправок между полными баками;
- экран расходов и статистики на основе журнала топлива;
- шаблонные разделы для документов, жидкостей, запчастей, мойки и шин;
- быстрые шаблоны списков и авто-напоминаний.

**Настройки и многопользовательский режим**

- каждый пользователь видит только свои данные;
- общие данные появляются только через явное приглашение;
- настройка часового пояса;
- приватная аналитика действий без хранения текста сообщений;
- предупреждение о тестовом режиме и возможной потере данных;
- экран текущего плана;
- базовый слой для будущей монетизации.

**API и администрирование**

- Admin API с `X-Admin-Token`;
- простая web-админка `/admin/ui` для активности и воронок;
- web-сайт `/web` для списков, напоминаний, лекарств, водительского журнала и админ-сводки;
- user-scoped API `/me/...` для web-клиента, защищенный Telegram WebApp `initData`, персональным web-ключом из бота или тестовым входом через `ADMIN_TOKEN`;
- GitHub Actions workflow для тестов и деплоя на VPS.

### Архитектура

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

Основные каталоги:

```text
src/
  api/            FastAPI admin API
  bot/            Telegram handlers, keyboards, states
  db/             SQLAlchemy base, session, models
  repositories/   Data access layer
  services/       Business logic
  utils/          Date/text helpers
  worker/         Reminder worker
tests/            Regression tests
alembic/          Database migrations
```

### Стек

- Python 3.11+
- python-telegram-bot
- FastAPI
- SQLAlchemy async
- PostgreSQL
- Alembic
- Pydantic v2
- Docker
- pytest

### Настройка

1. Скопируйте пример окружения:

```powershell
Copy-Item .env.example .env
```

2. Заполните `.env` своими значениями:

```env
BOT_TOKEN=...
BOT_USERNAME=...
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
WEB_PUBLIC_URL=http://127.0.0.1:8000
WEB_LOGIN_TOKEN_TTL_DAYS=30
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5433/DB
```

3. Для уведомления о релизе после рестарта можно задать:

```env
APP_VERSION=0.8.0-beta
APP_RELEASE_CHANNEL=beta
APP_GITHUB_URL=https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality
APP_CHANGELOG_URL=https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality/releases
STARTUP_UPDATE_MESSAGE=Обновлена стабильность сервиса и web-версии.
# Для SSH/CI с риском проблем кодировки используйте base64-вариант.
# Если заполнен, он имеет приоритет над STARTUP_UPDATE_MESSAGE.
STARTUP_UPDATE_MESSAGE_B64=
STARTUP_TECHNICAL_MESSAGE=
STARTUP_TECHNICAL_MESSAGE_B64=
STARTUP_ANNOUNCE_MODE=off
STARTUP_ANNOUNCE_IMPORTANCE=minor
STARTUP_ADMIN_ANNOUNCE_MODE=once_per_version
```

По умолчанию бот не рассылает сообщение об обновлении после каждого рестарта. Версия, последний запуск, история версий и пользовательский changelog доступны в Telegram: `Настройки -> О боте`, а также в web-сводке. Технические изменения отделены от пользовательских и показываются в admin-only статусе. Для крупного релиза включите `STARTUP_ANNOUNCE_MODE=major` и `STARTUP_ANNOUNCE_IMPORTANCE=major` или `critical`. Для служебного уведомления только администраторам используйте `STARTUP_ADMIN_ANNOUNCE_MODE=once_per_version` или `always`.

### Запуск

Рекомендуемый локальный сценарий:

```powershell
.\start-local.ps1
```

Docker Compose поднимает PostgreSQL, одноразовый `init-db`, API, bot и worker:

```powershell
docker-compose up -d
```

Если на сервере нет `docker compose`/`docker-compose`, используйте изолированный fallback:

```bash
bash deploy-vps-manual.sh
```

Ручной сценарий:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

`init-db` запускает Alembic migrations до `head`. Для старых локальных баз,
которые были созданы прежним `create_all`, команда безопасно доводит схему и
ставит Alembic stamp, чтобы следующие запуски шли обычным миграционным путём.

Отдельные режимы:

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

Безопасные проверки без Telegram polling и отправки сообщений:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

Web-сайт:

```text
http://127.0.0.1:8000/web
```

Основной вход для обычного браузера: в Telegram откройте `Настройки` -> `Web-версия`, получите персональный ключ и вставьте его на странице `/web`. Если задан `WEB_PUBLIC_URL`, бот также выдаст прямую ссылку вида `/web?token=...`.

В Telegram WebApp сайт использует `initData`. Для закрытой локальной отладки остается доступен вход через `ADMIN_TOKEN` и Telegram ID пользователя, если `WEB_TEST_LOGIN_ENABLED=true`.

Админская web-страница:

```text
http://127.0.0.1:8000/admin/ui
```

Страница не хранит токен на сервере. `X-Admin-Token` вводится в браузере и используется только для запросов к Admin API.

User API для web-сайта:

```text
GET /me
GET /me/summary
GET /me/lists
POST /me/lists
GET /me/lists/{id}
PATCH /me/lists/{id}
DELETE /me/lists/{id}
POST /me/lists/{id}/items
PATCH /me/lists/items/{id}
DELETE /me/lists/items/{id}
GET /me/reminders
POST /me/reminders
POST /me/reminders/{id}/done
DELETE /me/reminders/{id}
GET /me/medications
POST /me/medications
PATCH /me/medications/{id}
POST /me/medications/{id}/taken
POST /me/medications/{id}/skipped
DELETE /me/medications/{id}
GET /me/driver
POST /me/driver/vehicles
DELETE /me/driver/vehicles/{id}
GET /me/driver/vehicles/{id}/fuel
POST /me/driver/vehicles/{id}/fuel
DELETE /me/driver/fuel/{id}
```

Эти endpoints требуют один из вариантов авторизации: `X-Telegram-Init-Data` с валидным Telegram WebApp `initData`, `X-Web-Login-Token` с ключом из Telegram-бота, либо `X-Admin-Token` + `X-Web-Test-Telegram-Id` для закрытого тестирования при `WEB_TEST_LOGIN_ENABLED=true`.

Тесты:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

### Безопасность

- не коммитьте `.env`;
- не храните токены, пароли и приватные адреса в README;
- не открывайте PostgreSQL наружу;
- не публикуйте Admin API без HTTPS, firewall и строгого CORS;
- используйте SSH-ключи для серверного доступа;
- делайте backup базы перед рискованными миграциями;
- запускайте polling bot только в одном экземпляре на один Telegram token;
- запускайте worker в одном экземпляре, чтобы не дублировать уведомления;
- для production держите `API_BIND_HOST=127.0.0.1`, `API_DOCS_ENABLED=false`, `CORS_ORIGINS=`.

### Развитие

- платежная интеграция и тарифные ограничения;
- улучшение web-кабинета: фильтры, редактирование карточек без `prompt`, экспорт и мобильная верстка под Telegram WebApp;
- расширенная история приема лекарств;
- экспорт автомобильных расходов;
- уведомления и audit log для совместных списков;
- локализация интерфейса бота.

План развития web/app: [docs/WEB_APP_ROADMAP.md](docs/WEB_APP_ROADMAP.md).

<a id="en"></a>

## English

Telegram Productivity Bot is a modular Telegram bot for personal organization: lists, reminders, medication tracking, a vehicle journal, user settings, and a foundation for paid features.

This README intentionally avoids tokens, server addresses, private paths, production bot names, and other deployment-specific details.

### Features

**Lists**

- personal todo and shopping lists;
- single-item and bulk item creation;
- item toggling, editing, and deletion;
- list rename and deletion with confirmation;
- pagination;
- list-linked reminders;
- shared lists with `owner`, `editor`, and `viewer` roles;
- copy import and shared-list join by token.

**Reminders**

- button and text-driven creation flow;
- quick date and time presets;
- natural phrases such as “tomorrow 10” or “in 2 hours”;
- repeat rules: daily, weekly, monthly;
- active and completed reminder lists;
- done, cancel, and delete actions;
- UTC storage with user-timezone display.

**Medication Tracking**

- medication cards;
- dosage and instructions through buttons or text;
- importance levels: supplement, normal, important, critical;
- daily reminders 1, 2, or 3 times per day with custom times;
- taken, skipped, and snooze actions;
- intake buttons are hidden until the next relevant intake window.

The bot is a tracking aid only and does not replace medical advice.

**Driver Assistant**

- vehicle profiles;
- step-by-step vehicle creation and editing;
- current mileage;
- service interval by mileage and months;
- mark service as completed;
- next service calculation by mileage and date;
- fuel journal;
- step-by-step fuel entry creation and editing;
- vehicle-specific fuel history;
- vehicle and fuel entry deletion with confirmation;
- price per liter, fuel consumption, and cost per kilometer;
- partial refuels are included between full-tank measurements;
- cost and statistics screens based on the fuel journal;
- template sections for documents, fluids, parts, wash, and tires;
- quick list and vehicle reminder templates.

**Settings and Multi-User Mode**

- users are isolated by default;
- shared data exists only after explicit invitation;
- timezone settings;
- privacy-safe action analytics without storing message text;
- testing-mode notice about possible data loss;
- current plan screen;
- base layer for future monetization.

**API and Administration**

- Admin API with `X-Admin-Token`;
- simple `/admin/ui` web admin for activity and funnels;
- `/web` web site for lists, reminders, medications, vehicle journal, and admin overview;
- user-scoped `/me/...` API for the web client, protected by Telegram WebApp `initData`, a bot-issued personal web key, or test login with `ADMIN_TOKEN`;
- GitHub Actions workflow for tests and VPS deployment.

### Architecture

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

Main directories:

```text
src/
  api/            FastAPI admin API
  bot/            Telegram handlers, keyboards, states
  db/             SQLAlchemy base, session, models
  repositories/   Data access layer
  services/       Business logic
  utils/          Date/text helpers
  worker/         Reminder worker
tests/            Regression tests
alembic/          Database migrations
```

### Stack

- Python 3.11+
- python-telegram-bot
- FastAPI
- SQLAlchemy async
- PostgreSQL
- Alembic
- Pydantic v2
- Docker
- pytest

### Setup

1. Copy the environment example:

```powershell
Copy-Item .env.example .env
```

2. Fill `.env` with your own values:

```env
BOT_TOKEN=...
BOT_USERNAME=...
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
WEB_PUBLIC_URL=http://127.0.0.1:8000
WEB_LOGIN_TOKEN_TTL_DAYS=30
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5433/DB
```

3. Optional restart notification values:

```env
APP_VERSION=0.8.0-beta
APP_RELEASE_CHANNEL=beta
APP_GITHUB_URL=https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality
APP_CHANGELOG_URL=https://github.com/NikitaZhilin/a-new-telegram-bot-with-extensive-functionality/releases
STARTUP_UPDATE_MESSAGE=Обновлена стабильность сервиса и web-версии.
# Use this ASCII-safe base64 variant for SSH/CI if Cyrillic text is corrupted.
# When set, it overrides STARTUP_UPDATE_MESSAGE.
STARTUP_UPDATE_MESSAGE_B64=
STARTUP_TECHNICAL_MESSAGE=
STARTUP_TECHNICAL_MESSAGE_B64=
STARTUP_ANNOUNCE_MODE=off
STARTUP_ANNOUNCE_IMPORTANCE=minor
STARTUP_ADMIN_ANNOUNCE_MODE=once_per_version
```

By default, the bot does not broadcast an update message after every restart. Version, last startup time, release history, and user-facing changelog are available in Telegram under `Settings -> About bot` and in the web dashboard. Technical changes are separated from user-facing notes and shown in the admin-only status screen. For a major release, set `STARTUP_ANNOUNCE_MODE=major` and `STARTUP_ANNOUNCE_IMPORTANCE=major` or `critical`. For admin-only deployment notices, use `STARTUP_ADMIN_ANNOUNCE_MODE=once_per_version` or `always`.

### Running

Recommended local flow:

```powershell
.\start-local.ps1
```

Docker Compose starts PostgreSQL, one-shot `init-db`, API, bot, and worker:

```powershell
docker-compose up -d
```

If the server has no `docker compose`/`docker-compose`, use the isolated fallback:

```bash
bash deploy-vps-manual.sh
```

Manual flow:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

`init-db` runs Alembic migrations up to `head`. For older local databases
created by the previous `create_all` bootstrap, it safely normalizes the schema
and stamps the current Alembic revision so future starts use the regular
migration path.

Individual modes:

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

Safe checks without Telegram polling or message sending:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

Web site:

```text
http://127.0.0.1:8000/web
```

Primary browser login: open `Settings` -> `Web version` in Telegram, get a personal key, and paste it on `/web`. If `WEB_PUBLIC_URL` is configured, the bot also sends a direct `/web?token=...` login link.

Inside Telegram WebApp, the site uses `initData`. For closed local debugging, `ADMIN_TOKEN` plus a Telegram user ID is still available when `WEB_TEST_LOGIN_ENABLED=true`.

Admin web page:

```text
http://127.0.0.1:8000/admin/ui
```

The page does not store the token on the server. `X-Admin-Token` is entered in the browser and used only for Admin API requests.

User API for the web site:

```text
GET /me
GET /me/summary
GET /me/lists
POST /me/lists
GET /me/lists/{id}
PATCH /me/lists/{id}
DELETE /me/lists/{id}
POST /me/lists/{id}/items
PATCH /me/lists/items/{id}
DELETE /me/lists/items/{id}
GET /me/reminders
POST /me/reminders
POST /me/reminders/{id}/done
DELETE /me/reminders/{id}
GET /me/medications
POST /me/medications
PATCH /me/medications/{id}
POST /me/medications/{id}/taken
POST /me/medications/{id}/skipped
DELETE /me/medications/{id}
GET /me/driver
POST /me/driver/vehicles
DELETE /me/driver/vehicles/{id}
GET /me/driver/vehicles/{id}/fuel
POST /me/driver/vehicles/{id}/fuel
DELETE /me/driver/fuel/{id}
```

These endpoints require one of the supported auth methods: `X-Telegram-Init-Data` with valid Telegram WebApp `initData`, `X-Web-Login-Token` with a key issued by the Telegram bot, or `X-Admin-Token` + `X-Web-Test-Telegram-Id` for closed testing when `WEB_TEST_LOGIN_ENABLED=true`.

Tests:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

### Security

- do not commit `.env`;
- do not store tokens, passwords, or private infrastructure details in README files;
- do not expose PostgreSQL publicly;
- do not expose the Admin API without HTTPS, firewall, and strict CORS;
- use SSH keys for server access;
- back up the database before risky migrations;
- run only one polling bot instance per Telegram token;
- run only one worker instance to avoid duplicate notifications;
- for production keep `API_BIND_HOST=127.0.0.1`, `API_DOCS_ENABLED=false`, `CORS_ORIGINS=`.

### Roadmap

- payment integration and real plan limits;
- web cabinet improvements: filters, inline card editing without `prompt`, export, and Telegram WebApp mobile layout polish;
- extended medication intake history;
- vehicle expense export;
- notifications and audit log for shared lists;
- bot UI localization.

Web/app roadmap: [docs/WEB_APP_ROADMAP.md](docs/WEB_APP_ROADMAP.md).
