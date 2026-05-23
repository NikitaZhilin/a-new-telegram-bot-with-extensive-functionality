# 📋 Этап 5: Worker Доставки Напоминаний

**Дата:** 2026-02-19  
**Статус:** ✅ **ЗАВЕРШЕНО**

---

## 🎯 Требования

| Требование | Реализация |
|------------|------------|
| Идемпотентность | ✅ Поле `notified_at` + атомарное обновление |
| Отсутствие дублей при масштабировании | ✅ `SELECT ... FOR UPDATE SKIP LOCKED` |
| Транзакционность | ✅ PostgreSQL транзакции |
| Статусы Reminder | ✅ `active/done/canceled/missed` |
| Повторяемость | ✅ `daily/weekly/monthly` |

---

## 📁 Файлы

### Worker

| Файл | Описание |
|------|----------|
| `src/worker/reminder_worker.py` | ⭐ **Основной сервис worker** |
| `src/worker/__init__.py` | Экспорт |
| `src/worker/scheduler.py` | Legacy (deprecated) |

### Репозитории (DAL)

| Файл | Описание |
|------|----------|
| `src/repositories/reminder_repo.py` | ⭐ **ReminderRepository с атомарными операциями** |
| `src/repositories/user_repo.py` | UserRepository |
| `src/repositories/note_repo.py` | NoteRepository |
| `src/repositories/list_repo.py` | ListRepository |
| `src/repositories/base.py` | BaseRepository (CRUD) |
| `src/repositories/__init__.py` | Экспорт |

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────┐
│              ReminderWorkerService                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  _process_cycle()                                 │   │
│  │  1. Get now (UTC)                                 │   │
│  │  2. SELECT ... FOR UPDATE SKIP LOCKED             │   │
│  │  3. For each reminder:                            │   │
│  │     - _send_notification()                        │   │
│  │     - mark_as_notified()                          │   │
│  │     - _handle_recurring()                         │   │
│  │  4. COMMIT                                        │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│            ReminderRepository                            │
│                                                          │
│  • get_due_reminders_locked()  ← SKIP LOCKED            │
│  • mark_as_notified()          ← idempotency            │
│  • create_next_occurrence()    ← recurring              │
│  • mark_status()                                        │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL                                  │
│                                                          │
│  reminders table:                                        │
│  • id, user_id, text, remind_at_utc                     │
│  • status, repeat_rule, notified_at                     │
│  • INDEX: status, remind_at_utc, (user_id, status)      │
└─────────────────────────────────────────────────────────┘
```

---

## 🔐 Идемпотентность и Масштабирование

### Проблема
При запуске нескольких экземпляров worker один и тот же reminder может быть обработан несколько раз.

### Решение

#### 1. SELECT ... FOR UPDATE SKIP LOCKED
```python
query = (
    select(Reminder)
    .where(
        Reminder.status == ReminderStatus.ACTIVE,
        Reminder.remind_at_utc <= now,
        Reminder.notified_at.is_(None),  # Ключевое условие!
    )
    .with_for_update(skip_locked=True)  # Пропускать заблокированные
)
```

**Как работает:**
- Worker 1 выбирает 100 напоминаний → блокирует их
- Worker 2 пытается выбрать → получает только незаблокированные
- Ни одно напоминание не обрабатывается дважды

#### 2. Поле notified_at (Idempotency Key)
```python
# Атомарное обновление
await repo.mark_as_notified(reminder.id, now)
await session.commit()  # Фиксация транзакции
```

**Гарантии:**
- Если worker упал после отправки, но до commit → транзакция откатится
- При следующем запуске `notified_at IS NULL` → напоминание будет обработано снова
- После commit `notified_at` установлен → повторная обработка невозможна

---

## 📊 Статусы Reminder

```python
class ReminderStatus(str, Enum):
    ACTIVE = "active"      # Активное напоминание
    DONE = "done"          # Выполнено пользователем
    CANCELED = "canceled"  # Отменено пользователем
    MISSED = "missed"      # Пропущено (не доставлено)
```

---

## 🔁 Повторяемость

```python
class RepeatRule(str, Enum):
    NONE = "none"      # Без повтора
    DAILY = "daily"    # Ежедневно
    WEEKLY = "weekly"  # Еженедельно
    MONTHLY = "monthly"# Ежемесячно
```

### Логика обработки

```python
# 1. Отправить уведомление
await self._send_notification(reminder)

# 2. Пометить как доставленное
await repo.mark_as_notified(reminder.id, now)

# 3. Если повторяющееся → создать следующее
if reminder.repeat_rule != RepeatRule.NONE:
    next_time = calculate_next_occurrence(
        reminder.remind_at_utc,
        reminder.repeat_rule
    )
    await repo.create_next_occurrence(reminder, next_time)
```

### Расчёт следующего времени

```python
def calculate_next_occurrence(
    remind_at: datetime,
    repeat_rule: RepeatRule
) -> datetime:
    if repeat_rule == RepeatRule.DAILY:
        return remind_at + timedelta(days=1)
    elif repeat_rule == RepeatRule.WEEKLY:
        return remind_at + timedelta(weeks=1)
    elif repeat_rule == RepeatRule.MONTHLY:
        # Умное добавление месяца
        year = remind_at.year + (remind_at.month // 12)
        month = (remind_at.month % 12) + 1
        day = min(remind_at.day, 28)  # Безопасный день
        return remind_at.replace(year=year, month=month, day=day)
```

---

## 🚀 Запуск

### Команды

```bash
cd new_architecture

# Запуск worker
python -m src.main worker

# Или через entry point
rememberme-bot-worker
```

### Конфигурация

```bash
# .env
WORKER_INTERVAL=60  # Интервал опроса (секунды)
```

### В main.py

```python
async def run_worker() -> None:
    from src.worker import ReminderWorkerService
    from telegram import Bot
    
    bot = Bot(token=settings.BOT_TOKEN)
    
    try:
        await bot.initialize()
        
        worker = ReminderWorkerService(
            bot=bot,
            batch_size=100,        # Макс. напоминаний за цикл
            poll_interval=60,      # Секунды между циклами
        )
        
        await worker.start()
    finally:
        await bot.shutdown()
```

---

## 💡 Примеры использования

### ReminderRepository

```python
from src.db.session import async_session_maker
from src.repositories.reminder_repo import ReminderRepository

async with async_session_maker() as session:
    repo = ReminderRepository(session)
    
    # Получить due напоминания (с блокировкой)
    now = datetime.now(timezone.utc)
    reminders = await repo.get_due_reminders_locked(now, limit=100)
    
    # Пометить как доставленное
    await repo.mark_as_notified(reminder_id, now)
    
    # Создать следующее для повторяющегося
    next_time = calculate_next_occurrence(remind_at, RepeatRule.DAILY)
    await repo.create_next_occurrence(reminder, next_time)
    
    # Изменить статус
    await repo.mark_status(reminder_id, ReminderStatus.DONE)
    
    await session.commit()
```

### ReminderWorkerService

```python
from telegram import Bot
from src.worker import ReminderWorkerService

bot = Bot(token="YOUR_BOT_TOKEN")
await bot.initialize()

worker = ReminderWorkerService(
    bot=bot,
    batch_size=100,
    poll_interval=60,
)

# Запуск (блокирующий)
await worker.start()

# Или остановка
worker.stop()
```

---

## 📝 Формат сообщения

```
⏰ <b>Заголовок напоминания</b>

Текст напоминания...

🔁 Повтор: daily
🕒 Время: 19.02.2026 15:30 UTC
```

---

## 🔍 Логирование

```json
{
  "level": "info",
  "event": "Processing 5 due reminder(s)",
  "timestamp": "2026-02-19T12:00:00.000Z",
  "count": 5
}
```

```json
{
  "level": "info",
  "event": "Sent reminder 123 to user 456",
  "timestamp": "2026-02-19T12:00:01.000Z",
  "reminder_id": 123,
  "user_id": 456,
  "chat_id": 789012345
}
```

---

## ✅ Чеклист

| Компонент | Статус |
|-----------|--------|
| ReminderRepository с `SKIP LOCKED` | ✅ |
| Идемпотентность через `notified_at` | ✅ |
| Обработка повторяющихся напоминаний | ✅ |
| Расчёт следующего времени (daily/weekly/monthly) | ✅ |
| Атомарность транзакций | ✅ |
| Безопасное масштабирование (N workers) | ✅ |
| Форматирование сообщений Telegram | ✅ |
| Обработка ошибок (не падает при TelegramError) | ✅ |
| Структурированное логирование | ✅ |
| Все репозитории (User, Note, List, Reminder) | ✅ |

---

## 📚 Следующие шаги

**Этап 6:** Реализация сервисов (NoteService, ListService, ReminderService) + бизнес-логика
