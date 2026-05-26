> ARCHIVE NOTICE: This file is historical context only. It is not a current setup, launch, deployment, or security instruction. Use ../README.md, ../USER_GUIDE.md, ../TECHNICAL.md, and ../DEPLOYMENT.md instead.
# 🗄️ Этап 4: SQLAlchemy Async Модели + Alembic Миграции

**Дата:** 2026-02-19  
**Статус:** ✅ **ЗАВЕРШЕНО**

---

## 📁 Файлы

### Модели (SQLAlchemy 2.x style)

| Файл | Описание |
|------|----------|
| `src/db/models.py` | **Все модели в одном файле** (User, Note, List, ListItem, Reminder) |
| `src/db/models/__init__.py` | Экспорт моделей |
| `src/db/base.py` | Declarative base |
| `src/db/session.py` | Async engine + session factory |
| `src/db/__init__.py` | Экспорт пакета db |

### Alembic миграции

| Файл | Описание |
|------|----------|
| `alembic/env.py` | Async environment для Alembic |
| `alembic/versions/001_initial_migration.py` | Первая миграция (создание всех таблиц) |
| `alembic.ini` | Конфигурация Alembic |

---

## 📊 Схема БД

### Таблица: `users`
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PRIMARY KEY |
| telegram_id | BigInteger | UNIQUE, NOT NULL, INDEX |
| username | String(255) | NULL |
| first_name | String(255) | NULL |
| last_name | String(255) | NULL |
| timezone | String(50) | NOT NULL, DEFAULT 'UTC' |
| created_at | DateTime(timezone) | NOT NULL, DEFAULT now() |
| updated_at | DateTime(timezone) | NOT NULL, DEFAULT now(), ON UPDATE now() |

### Таблица: `notes`
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PRIMARY KEY |
| user_id | Integer | FK → users.id, INDEX |
| title | String(255) | NOT NULL |
| text | Text | NULL |
| is_archived | Boolean | DEFAULT false, INDEX |
| created_at | DateTime(timezone) | NOT NULL |
| updated_at | DateTime(timezone) | NOT NULL |

### Таблица: `lists`
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PRIMARY KEY |
| user_id | Integer | FK → users.id, INDEX |
| title | String(255) | NOT NULL |
| created_at | DateTime(timezone) | NOT NULL |
| updated_at | DateTime(timezone) | NOT NULL |

### Таблица: `list_items`
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PRIMARY KEY |
| list_id | Integer | FK → lists.id, INDEX |
| text | String(500) | NOT NULL |
| is_completed | Boolean | DEFAULT false, INDEX |
| position | Integer | NULL (для сортировки) |
| created_at | DateTime(timezone) | NOT NULL |

### Таблица: `reminders` ⏰
| Column | Type | Constraints |
|--------|------|-------------|
| id | Integer | PRIMARY KEY |
| user_id | Integer | FK → users.id, INDEX |
| title | String(255) | NULL |
| text | Text | NOT NULL |
| **remind_at_utc** | **DateTime(timezone)** | **NOT NULL, INDEX** (UTC!) |
| repeat_rule | Enum | NONE/DAILY/WEEKLY/MONTHLY |
| status | Enum | ACTIVE/DONE/CANCELED/MISSED, INDEX |
| notified_at | DateTime(timezone) | NULL |
| created_at | DateTime(timezone) | NOT NULL |
| updated_at | DateTime(timezone) | NOT NULL |

**Составные индексы:**
- `ix_reminders_user_status` → (user_id, status)
- `ix_reminders_remind_at_status` → (remind_at_utc, status)

---

## 🚀 Команды Alembic

### Установка зависимостей
```bash
cd new_architecture
pip install -e .
```

### Запуск миграций
```bash
# Применить все миграции
alembic upgrade head

# Применить одну миграцию вперёд
alembic upgrade +1

# Откатить одну миграцию назад
alembic downgrade -1

# Откатить все миграции
alembic downgrade base

# Проверить текущую ревизию
alembic current

# Показать историю миграций
alembic history

# Показать pending миграции
alembic history --verbose
```

### Создание новых миграций
```bash
# Автосоздание миграции (сравнение с моделями)
alembic revision --autogenerate -m "Description of changes"

# Пустая миграция
alembic revision -m "Add new column"
```

---

## 🔧 Настройка подключения

### .env
```bash
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/rememberme
DB_ECHO=false

# Для прода (пример)
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
```

### alembic.ini
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/rememberme
```

---

## 💡 Примеры использования

### Создание сессии
```python
from src.db.session import async_session_maker
from src.db.models import User

async with async_session_maker() as session:
    # Query
    user = await session.get(User, 1)
    
    # Insert
    new_user = User(telegram_id=123456789, username="john")
    session.add(new_user)
    await session.commit()
```

### Через dependency (FastAPI)
```python
from src.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

async def create_note(db: AsyncSession = Depends(get_db)):
    # session auto-commits on success
    # session auto-rollbacks on exception
    pass
```

### Время в UTC
```python
from datetime import datetime, timezone

# Правильно: UTC timezone-aware datetime
reminder_time = datetime(2026, 2, 20, 15, 30, tzinfo=timezone.utc)

# Или из timestamp
reminder_time = datetime.fromtimestamp(1740067800, tz=timezone.utc)
```

---

## ✅ Особенности реализации

### SQLAlchemy 2.x Style
- ✅ Type hints: `Mapped[int]`, `mapped_column()`
- ✅ `relationship()` с `lazy="selectin"` для eager loading
- ✅ `func.now()` для server_default
- ✅ `DateTime(timezone=True)` для timezone-aware datetime

### Все времена в UTC
- ✅ `remind_at_utc` — DateTime с timezone
- ✅ `created_at`, `updated_at` — DateTime с timezone
- ✅ `server_default=func.now()` — PostgreSQL вернёт текущее время

### Enum типы
```python
class ReminderStatus(str, Enum):
    ACTIVE = "active"
    DONE = "done"
    CANCELED = "canceled"
    MISSED = "missed"

class RepeatRule(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
```

### Индексы
- ✅ Все FK индексированы
- ✅ `telegram_id` — unique index
- ✅ `remind_at_utc` — index для быстрого поиска напоминаний
- ✅ `status` — index для фильтрации
- ✅ Составные индексы для частых запросов

---

## 📝 Следующие шаги

**Этап 5:** Реализация репозиториев (UserRepo, NoteRepo, ListRepo, ReminderRepo)
