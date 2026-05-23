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
- быстрые шаблоны списков и авто-напоминаний.

**Настройки и многопользовательский режим**

- каждый пользователь видит только свои данные;
- общие данные появляются только через явное приглашение;
- настройка часового пояса;
- экран текущего плана;
- базовый слой для будущей монетизации.

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
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5433/DB
```

3. Для уведомления о релизе после рестарта можно задать:

```env
APP_VERSION=0.4.0
STARTUP_UPDATE_MESSAGE=Добавлен автомобильный журнал: авто, ТО, история заправок и расчет расхода.
```

### Запуск

Локальный сценарий:

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

Безопасные проверки без Telegram polling и отправки сообщений:

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

### Безопасность

- не коммитьте `.env`;
- не храните токены, пароли и приватные адреса в README;
- не открывайте PostgreSQL наружу;
- не публикуйте Admin API без HTTPS, firewall и строгого CORS;
- используйте SSH-ключи для серверного доступа;
- делайте backup базы перед рискованными миграциями;
- запускайте worker в одном экземпляре, чтобы не дублировать уведомления.

### Развитие

- платежная интеграция и тарифные ограничения;
- web-панель администратора;
- расширенная история приема лекарств;
- экспорт автомобильных расходов;
- уведомления и audit log для совместных списков;
- CI/CD с автоматическим тестом и деплоем;
- локализация интерфейса бота.

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
- quick list and vehicle reminder templates.

**Settings and Multi-User Mode**

- users are isolated by default;
- shared data exists only after explicit invitation;
- timezone settings;
- current plan screen;
- base layer for future monetization.

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
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
POSTGRES_PORT=5433
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5433/DB
```

3. Optional restart notification values:

```env
APP_VERSION=0.4.0
STARTUP_UPDATE_MESSAGE=Driver journal added: vehicles, service plan, fuel history, and consumption tracking.
```

### Running

Local flow:

```powershell
docker-compose up -d postgres
python -B -m src.main init-db
python -B -m src.main bot
```

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
- run only one worker instance to avoid duplicate notifications.

### Roadmap

- payment integration and real plan limits;
- admin web panel;
- extended medication intake history;
- vehicle expense export;
- notifications and audit log for shared lists;
- CI/CD with automated tests and deployment;
- bot UI localization.
