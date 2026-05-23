# RememberMe Bot

[Русский](#ru) | [English](#en)

<a id="ru"></a>

## Русский

RememberMe Bot - Telegram-бот для личной организации: списки дел и покупок, общие списки, напоминания, контроль приема лекарств, пользовательские настройки и задел под платные функции.

Проект построен на новой архитектуре с разделением слоев:

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

### Что умеет бот

#### Списки дел и покупок

- Создание личных списков.
- Просмотр списков с пагинацией.
- Добавление одного пункта или нескольких пунктов пачкой.
- Отметка пункта выполненным или невыполненным.
- Редактирование и удаление пунктов.
- Переименование и удаление списка.
- Подтверждение опасных действий.
- Возврат назад и переход в главное меню без потери сценария.
- Обновление существующего сообщения бота после действий, чтобы чат не превращался в длинную ленту технических сообщений.

#### Общие списки

- Каждый пользователь по умолчанию видит только свои данные.
- Списком можно поделиться с другим пользователем.
- Есть два сценария:
  - копия списка через `/import_list TOKEN`;
  - совместный список через `/join_list TOKEN`.
- Для совместных списков есть роли:
  - `owner` - владелец;
  - `editor` - может менять пункты;
  - `viewer` - может только смотреть.
- Владелец может смотреть участников, менять роли и отзывать доступ.
- Токены доступа ограничены по сроку и числу использований.

#### Напоминания

- Создание напоминаний через Telegram-сценарий.
- Быстрый выбор даты: сегодня, завтра, послезавтра, через неделю.
- Быстрый выбор времени: через 10 минут, 30 минут, 1 час, 2 часа, фиксированные часы.
- Ручной ввод даты, времени и фраз.
- Повторы: нет, ежедневно, еженедельно, ежемесячно.
- Список активных и завершенных напоминаний.
- Отметка выполненным, отмена и удаление.
- Привязка напоминания к списку, чтобы уведомление могло вести к нужному списку.
- Хранение времени в UTC с отображением в часовом поясе пользователя.

#### Прием лекарств

- Создание карточки препарата.
- Дозировка: готовые варианты и ручной ввод.
- Инструкции: до еды, во время еды, после еды, запить водой, не смешивать, ручной вариант или пропуск.
- Важность препарата:
  - БАД;
  - обычное;
  - важное;
  - критичное.
- Напоминания 1, 2 или 3 раза в день с ручной настройкой времени.
- Действия по приему:
  - принял;
  - пропустил;
  - отложить на 15 минут.
- После отметки приема кнопка "Принял" скрывается до следующего актуального окна приема.
- Для нескольких приемов в день бот учитывает временные окна, чтобы следующий прием снова стал доступен ближе к своему времени.

Важно: бот помогает отслеживать прием, но не является медицинской рекомендацией и не заменяет врача.

#### Настройки

- Выбор часового пояса из готовых вариантов.
- Ручной ввод часового пояса.
- Пользовательская статистика.
- Просмотр текущего плана подписки.
- Ссылка для приглашения другого пользователя к боту, если задан `BOT_USERNAME`.

#### Мультипользовательский режим

- Пользователи изолированы друг от друга.
- Личные списки, напоминания и лекарства не видны другим пользователям.
- Совместный доступ появляется только после явного шаринга.
- Администратор может использовать API для поддержки и отладки пользователей.

#### Монетизация

В проекте уже есть базовый слой для будущей монетизации:

- модель подписок пользователя;
- `DEFAULT_SUBSCRIPTION_PLAN`;
- экран текущего плана;
- сервис доступа к функциям.

Реальная платежная интеграция пока не подключена. Это оставлено как следующий этап развития.

### API и worker

#### FastAPI Admin API

API предназначен для администрирования и поддержки:

- health-check;
- список пользователей;
- карточка пользователя;
- статистика проекта;
- обзор пользовательских записей;
- просмотр ближайших напоминаний.

API защищается заголовком `X-Admin-Token`.

В production рекомендуется:

```env
API_DOCS_ENABLED=false
API_BIND_HOST=127.0.0.1
CORS_ORIGINS=
```

#### Reminder Worker

Worker отдельно от бота:

- проверяет due reminders;
- отправляет уведомления в Telegram;
- создает следующие срабатывания для повторяющихся напоминаний;
- различает временные и постоянные ошибки Telegram;
- не должен запускаться в нескольких экземплярах одновременно.

### Технологический стек

- Python 3.11+
- python-telegram-bot
- FastAPI
- SQLAlchemy async
- asyncpg
- PostgreSQL
- Alembic
- Pydantic v2 / pydantic-settings
- Docker
- pytest
- structlog

### Структура проекта

```text
src/
  api/            FastAPI application and admin routes
  bot/            Telegram handlers, keyboards, states, middlewares
  db/             SQLAlchemy base, session, models
  repositories/   Data access layer
  services/       Business logic
  utils/          Text/date/format helpers
  worker/         Reminder worker and scheduler
tests/            Regression and service tests
alembic/          Database migrations
```

### Быстрый старт локально

1. Скопировать `.env.example`:

```powershell
Copy-Item .env.example .env
```

2. Заполнить `.env`:

```env
BOT_TOKEN=...
BOT_USERNAME=tg_napominalka2_bot
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DB=rememberme
POSTGRES_PORT=5433
POSTGRES_BIND_HOST=127.0.0.1
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5433/rememberme
```

3. Запустить локально:

```powershell
.\start-local.ps1
```

Полезные варианты:

```powershell
.\start-local.ps1 -DryRunOnly
.\start-local.ps1 -RunTests
.\start-local.ps1 -Mode bot
.\start-local.ps1 -Mode worker
.\start-local.ps1 -SkipDocker
```

### Ручной запуск

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

Отдельные режимы:

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

### Безопасные проверки

Dry-run режимы не запускают polling, webhook и отправку сообщений:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

Тесты:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

### Фоновый запуск на Windows

```powershell
.\start-background.ps1
.\stop-background.ps1
.\restart-background.ps1
```

Автозапуск через Windows Task Scheduler:

```powershell
.\install-autostart-task.ps1
```

Удалить задачу:

```powershell
.\uninstall-autostart-task.ps1
```

### Деплой на VPS

Подробная инструкция: [DEPLOY_VPS.md](DEPLOY_VPS.md).

Рекомендуемая схема:

```text
/opt/bots/rememberme
```

Проект должен жить отдельно от VPN, MTProto, nginx, firewall и других системных сервисов.

Контейнеры бота изолированы именами:

```text
rememberme_bot-postgres
rememberme_bot-api
rememberme_bot-bot
rememberme_bot-worker
```

PostgreSQL и API по умолчанию привязаны к `127.0.0.1`, а не к публичному интерфейсу.

### Git

Инструкция по первому push/clone: [GIT_SETUP.md](GIT_SETUP.md).

Обычный цикл разработки:

```powershell
git status
git add .
git commit -m "Describe changes"
git push
```

### Безопасность

- Не коммитить `.env`.
- Не хранить токены в коде или README.
- Не открывать PostgreSQL наружу.
- Не открывать Admin API публично без HTTPS, firewall и строгого CORS.
- После передачи root-пароля в чат сменить пароль или отключить password-login.
- Для VPS использовать SSH-ключи.
- Перед рискованными изменениями делать backup PostgreSQL volume.

### Преимущества проекта

- Чистое разделение на `bot`, `api`, `db`, `repositories`, `services`, `worker`.
- Функции развиваются вертикальными сценариями, а не хаотичными обработчиками.
- Бизнес-логика вынесена в services/repositories.
- Есть ownership-check и мультипользовательская изоляция.
- Есть dry-run режимы для проверки lifecycle без Telegram API.
- Есть тесты на критичные сценарии.
- Можно запускать локально, в фоне на Windows или на VPS.
- Архитектура готова к добавлению новых доменов: привычки, финансы, семейные задачи, курсы лекарств, платные тарифы.

### Возможности развития

- Полноценные курсы лекарств: дата начала, дата окончания, паузы, несколько приемов как единый курс.
- История приема лекарств с экспортом врачу.
- Гибкие статусы приема: принял поздно, пропустил, отменил, перенес.
- Платежи и реальные тарифные ограничения.
- Web admin panel поверх текущего API.
- Уведомления для общих списков и семейных сценариев.
- Audit log для совместных списков.
- Backup/restore сценарии для VPS.
- CI/CD: автоматический тест и деплой после push.
- Локализация интерфейса бота на несколько языков.

### Текущие ограничения

- Notes-модуль есть в коде, но скрыт из пользовательского меню.
- Напоминания редактируются ограниченно.
- Medication tracking не заменяет медицинские назначения.
- Платежная интеграция пока не подключена.
- API рассчитан на администрирование, не на публичный пользовательский web-клиент.

<a id="en"></a>

## English

RememberMe Bot is a Telegram bot for personal organization: todo and shopping lists, shared lists, reminders, medication intake tracking, user settings, and a foundation for paid features.

The project follows a layered architecture:

```text
bot -> services -> repositories -> db
api -> services -> repositories -> db
worker -> services/repositories -> db -> Telegram
```

### Features

#### Todo and shopping lists

- Create personal lists.
- Browse lists with pagination.
- Add one item or bulk-add multiple items.
- Toggle items as done or not done.
- Edit and delete items.
- Rename and delete lists.
- Confirm destructive actions.
- Navigate back and return to the main menu.
- Update existing bot messages after actions instead of flooding the chat.

#### Shared lists

- Every user sees only their own data by default.
- A list can be shared with another user.
- Two sharing modes are supported:
  - private copy via `/import_list TOKEN`;
  - real shared access via `/join_list TOKEN`.
- Shared list roles:
  - `owner` - list owner;
  - `editor` - can change items;
  - `viewer` - read-only access.
- Owners can view members, change roles, and revoke access.
- Share tokens are time-limited and usage-limited.

#### Reminders

- Create reminders through a Telegram flow.
- Quick date presets: today, tomorrow, the day after tomorrow, next week.
- Quick time presets: in 10 minutes, 30 minutes, 1 hour, 2 hours, fixed clock times.
- Manual date, time, and phrase parsing.
- Repeat rules: none, daily, weekly, monthly.
- Active and completed reminder lists.
- Mark as done, cancel, and delete.
- Link a reminder to a list, so the notification can lead back to the relevant list.
- Store time in UTC and display it in the user's timezone.

#### Medication intake

- Create medication cards.
- Dosage presets and custom dosage text.
- Instructions: before food, during food, after food, with water, do not mix, custom text, or skip.
- Medication importance:
  - supplement;
  - normal;
  - important;
  - critical.
- Daily reminders 1, 2, or 3 times per day with manually configured times.
- Intake actions:
  - taken;
  - skipped;
  - snooze for 15 minutes.
- After a medication is marked as taken, the "taken" action is hidden until the next relevant intake window.
- For multiple daily intakes, the bot uses time windows so the next intake becomes available near its scheduled time.

Important: this bot is a tracking aid only. It is not medical advice and does not replace a doctor.

#### Settings

- Choose timezone from presets.
- Enter timezone manually.
- User statistics.
- Current subscription plan screen.
- Bot invite link if `BOT_USERNAME` is configured.

#### Multi-user mode

- Users are isolated from each other.
- Personal lists, reminders, and medications are not visible to other users.
- Shared access exists only after explicit sharing.
- Admin users can use the API for support and debugging.

#### Monetization foundation

The project already contains a basic monetization layer:

- user subscription model;
- `DEFAULT_SUBSCRIPTION_PLAN`;
- current plan screen;
- feature access service.

Real payment integration is not connected yet. It is planned as a future stage.

### API and worker

#### FastAPI Admin API

The API is intended for administration and support:

- health check;
- user list;
- user details;
- project statistics;
- user records overview;
- due reminders overview.

The API is protected with the `X-Admin-Token` header.

Recommended production settings:

```env
API_DOCS_ENABLED=false
API_BIND_HOST=127.0.0.1
CORS_ORIGINS=
```

#### Reminder Worker

The worker runs separately from the bot:

- checks due reminders;
- sends Telegram notifications;
- creates next occurrences for repeating reminders;
- separates temporary and permanent Telegram errors;
- should not be scaled to multiple instances.

### Tech stack

- Python 3.11+
- python-telegram-bot
- FastAPI
- SQLAlchemy async
- asyncpg
- PostgreSQL
- Alembic
- Pydantic v2 / pydantic-settings
- Docker
- pytest
- structlog

### Project structure

```text
src/
  api/            FastAPI application and admin routes
  bot/            Telegram handlers, keyboards, states, middlewares
  db/             SQLAlchemy base, session, models
  repositories/   Data access layer
  services/       Business logic
  utils/          Text/date/format helpers
  worker/         Reminder worker and scheduler
tests/            Regression and service tests
alembic/          Database migrations
```

### Local quick start

1. Copy `.env.example`:

```powershell
Copy-Item .env.example .env
```

2. Fill `.env`:

```env
BOT_TOKEN=...
BOT_USERNAME=tg_napominalka2_bot
ADMIN_TOKEN=...
ADMIN_TELEGRAM_IDS=...
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
POSTGRES_DB=rememberme
POSTGRES_PORT=5433
POSTGRES_BIND_HOST=127.0.0.1
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5433/rememberme
```

3. Start locally:

```powershell
.\start-local.ps1
```

Useful variants:

```powershell
.\start-local.ps1 -DryRunOnly
.\start-local.ps1 -RunTests
.\start-local.ps1 -Mode bot
.\start-local.ps1 -Mode worker
.\start-local.ps1 -SkipDocker
```

### Manual startup

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

Separate modes:

```powershell
python -B -m src.main api
python -B -m src.main bot
python -B -m src.main worker
python -B -m src.main all
python -B -m src.main init-db
```

### Safe startup checks

Dry-run modes do not start polling, webhooks, or message sending:

```powershell
python -B -m src.main api --dry-run
python -B -m src.main bot --dry-run
python -B -m src.main worker --dry-run
python -B -m src.main all --dry-run
```

Tests:

```powershell
python -B -m pytest -p no:cacheprovider tests
```

### Windows background run

```powershell
.\start-background.ps1
.\stop-background.ps1
.\restart-background.ps1
```

Windows Task Scheduler autostart:

```powershell
.\install-autostart-task.ps1
```

Remove the task:

```powershell
.\uninstall-autostart-task.ps1
```

### VPS deployment

Full guide: [DEPLOY_VPS.md](DEPLOY_VPS.md).

Recommended layout:

```text
/opt/bots/rememberme
```

The bot should be isolated from VPN, MTProto, nginx, firewall, and other system services.

Isolated bot containers:

```text
rememberme_bot-postgres
rememberme_bot-api
rememberme_bot-bot
rememberme_bot-worker
```

PostgreSQL and API are bound to `127.0.0.1` by default.

### Git

First publish/clone guide: [GIT_SETUP.md](GIT_SETUP.md).

Regular development cycle:

```powershell
git status
git add .
git commit -m "Describe changes"
git push
```

### Security

- Do not commit `.env`.
- Do not store tokens in code or README files.
- Do not expose PostgreSQL publicly.
- Do not expose the Admin API publicly without HTTPS, firewall, and strict CORS.
- If a root password was shared in chat, rotate it or disable password login.
- Use SSH keys for VPS access.
- Back up the PostgreSQL volume before risky changes.

### Advantages

- Clean separation into `bot`, `api`, `db`, `repositories`, `services`, and `worker`.
- Features are developed as vertical user scenarios instead of scattered handlers.
- Business logic lives in services/repositories.
- Ownership checks and multi-user isolation are part of the design.
- Dry-run modes validate the lifecycle without Telegram API calls.
- Critical flows have regression tests.
- The project can run locally, in the background on Windows, or on a VPS.
- The architecture is ready for new domains: habits, finance, family tasks, medication courses, and paid plans.

### Development opportunities

- Full medication courses: start date, end date, pauses, and multiple daily intakes as one course.
- Medication history with export for a doctor.
- Flexible intake statuses: taken late, skipped, canceled, postponed.
- Payments and real feature limits.
- Web admin panel on top of the current API.
- Notifications for shared lists and family workflows.
- Audit log for shared lists.
- Backup/restore workflows for VPS.
- CI/CD: automated test and deploy after push.
- Bot UI localization into multiple languages.

### Current limitations

- The Notes module exists in code but is hidden from the user-facing menu.
- Reminder editing is intentionally limited.
- Medication tracking does not replace medical prescriptions.
- Payment integration is not connected yet.
- The API is designed for administration, not as a public user-facing web client.
