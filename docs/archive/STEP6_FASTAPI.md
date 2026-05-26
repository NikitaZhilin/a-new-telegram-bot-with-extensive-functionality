> ARCHIVE NOTICE: This file is historical context only. It is not a current setup, launch, deployment, or security instruction. Use ../README.md, ../USER_GUIDE.md, ../TECHNICAL.md, and ../DEPLOYMENT.md instead.
# 📋 Этап 6: FastAPI REST API

**Дата:** 2026-02-19  
**Статус:** ✅ **ЗАВЕРШЕНО**

---

## 🎯 Требования

| Требование | Реализация |
|------------|------------|
| GET /health | ✅ Базовый health check |
| GET /admin/users | ✅ Список пользователей (paginated) |
| GET /admin/stats | ✅ Статистика системы |
| Auth по X-Admin-Token | ✅ Header аутентификация |

---

## 📁 Файлы

```
src/api/
├── __init__.py              # Экспорт
├── app.py                   # ⭐ FastAPI приложение
├── auth.py                  # ⭐ Аутентификация (X-Admin-Token)
│
└── routes/
    ├── __init__.py          # Экспорт
    ├── health.py            # ⭐ Health endpoints
    └── admin.py             # ⭐ Admin endpoints
```

---

## 🚀 Endpoints

### Health (без аутентификации)

| Endpoint | Описание |
|----------|----------|
| `GET /health` | Базовый health check |
| `GET /health/ready` | Readiness probe (с проверкой БД) |
| `GET /health/live` | Liveness probe |

### Admin (требуется X-Admin-Token)

| Endpoint | Описание |
|----------|----------|
| `GET /admin/users` | Список пользователей (paginated) |
| `GET /admin/users/{user_id}` | Информация о пользователе |
| `GET /admin/stats` | Статистика системы |
| `GET /admin/reminders/due` | Напоминания, которые скоро сработают |

---

## 🔐 Аутентификация

### Запрос с токеном

```bash
curl -X GET http://localhost:8000/admin/stats \
  -H "X-Admin-Token: your-secret-token"
```

### Реализация (src/api/auth.py)

```python
async def verify_admin_token(
    x_admin_token: str = Header(..., alias="X-Admin-Token")
) -> bool:
    # Constant-time comparison
    if not _safe_compare(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(401, detail="Invalid admin token")
    return True
```

**Защита от timing attacks:**
- Используется поразрядное XOR сравнение
- Фиксированное время выполнения независимо от позиции несовпадения

---

## 📊 Примеры ответов

### GET /health

```json
{
  "status": "ok",
  "timestamp": "2026-02-19T12:00:00.000000+00:00",
  "version": "2.0.0",
  "service": "rememberme-api"
}
```

### GET /health/ready

```json
{
  "status": "ok",
  "timestamp": "2026-02-19T12:00:00.000000+00:00",
  "version": "2.0.0",
  "service": "rememberme-api",
  "database": "ok",
  "uptime_seconds": 3600
}
```

### GET /admin/users

```json
{
  "users": [
    {
      "id": 1,
      "telegram_id": 123456789,
      "username": "john_doe",
      "first_name": "John",
      "timezone": "Europe/Moscow",
      "created_at": "2026-02-19T10:00:00"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20
}
```

### GET /admin/stats

```json
{
  "users": {
    "total": 150,
    "created_today": 12,
    "created_week": 45
  },
  "notes": {
    "total": 523,
    "created_today": 34,
    "created_week": 128
  },
  "lists": {
    "total": 234,
    "created_today": 15,
    "created_week": 67
  },
  "reminders": {
    "total": 892,
    "active": 456,
    "done": 380,
    "canceled": 45,
    "missed": 11,
    "due_soon": 23
  },
  "generated_at": "2026-02-19T12:00:00.000000+00:00"
}
```

### GET /admin/reminders/due

```json
{
  "reminders": [
    {
      "id": 123,
      "user_id": 456,
      "text": "Купить молоко...",
      "remind_at_utc": "2026-02-19T12:30:00+00:00",
      "repeat_rule": "daily"
    }
  ],
  "count": 5,
  "generated_at": "2026-02-19T12:00:00.000000+00:00"
}
```

---

## 🚀 Запуск

### Команды

```bash
cd new_architecture

# Запуск API
python -m src.main api

# Или через entry point
rememberme-bot-api
```

### Конфигурация

```bash
# .env
ADMIN_TOKEN=your-super-secret-token-here
API_HOST=0.0.0.0
API_PORT=8000
```

---

## 📚 Swagger UI

После запуска API откройте:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

### Пример запроса через Swagger

1. Откройте http://localhost:8000/docs
2. Нажмите на endpoint (например, `/admin/stats`)
3. Нажмите "Try it out"
4. Введите `X-Admin-Token: your-secret-token`
5. Нажмите "Execute"

---

## 💡 Примеры использования

### Python клиент

```python
import httpx

API_URL = "http://localhost:8000"
ADMIN_TOKEN = "your-secret-token"

headers = {"X-Admin-Token": ADMIN_TOKEN}

# Health check
async with httpx.AsyncClient() as client:
    response = await client.get(f"{API_URL}/health")
    print(response.json())
    # {"status": "ok", ...}

# Получить статистику
async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{API_URL}/admin/stats",
        headers=headers
    )
    stats = response.json()
    print(f"Total users: {stats['users']['total']}")

# Получить пользователей (paginated)
async with httpx.AsyncClient() as client:
    response = await client.get(
        f"{API_URL}/admin/users?page=1&page_size=50",
        headers=headers
    )
    users = response.json()
    print(f"Page {users['page']} of {users['total']}")
```

### cURL

```bash
# Health check
curl http://localhost:8000/health

# Statistics
curl -H "X-Admin-Token: secret" http://localhost:8000/admin/stats

# Users (page 2, 50 per page)
curl -H "X-Admin-Token: secret" \
  "http://localhost:8000/admin/users?page=2&page_size=50"

# Due reminders
curl -H "X-Admin-Token: secret" \
  "http://localhost:8000/admin/reminders/due?limit=100"
```

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI App                           │
│                                                          │
│  ┌─────────────────┐    ┌─────────────────────────┐     │
│  │  /health        │    │  /admin/*               │     │
│  │  (no auth)      │    │  (X-Admin-Token req.)   │     │
│  └─────────────────┘    └─────────────────────────┘     │
│                          │                               │
│                          ▼                               │
│                  ┌─────────────────┐                     │
│                  │  verify_admin_  │                     │
│                  │  token()        │                     │
│                  │  (constant-time)│                     │
│                  └─────────────────┘                     │
│                          │                               │
│                          ▼                               │
│                  ┌─────────────────┐                     │
│                  │  Admin Routes   │                     │
│                  │  • get_users()  │                     │
│                  │  • get_stats()  │                     │
│                  │  • get_due()    │                     │
│                  └─────────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

---

## ✅ Чеклист

| Компонент | Статус |
|-----------|--------|
| FastAPI приложение | ✅ |
| GET /health | ✅ |
| GET /health/ready (с БД проверкой) | ✅ |
| GET /health/live | ✅ |
| GET /admin/users (paginated) | ✅ |
| GET /admin/users/{user_id} | ✅ |
| GET /admin/stats | ✅ |
| GET /admin/reminders/due | ✅ |
| X-Admin-Token аутентификация | ✅ |
| Constant-time comparison | ✅ |
| Pydantic response models | ✅ |
| Swagger UI /docs | ✅ |
| CORS middleware | ✅ |
| Lifespan events | ✅ |

---

## 🔒 Безопасность

### Production рекомендации

1. **Смените ADMIN_TOKEN**
   ```bash
   # .env
   ADMIN_TOKEN=<random-64-char-string>
   ```

2. **Настройте CORS**
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://your-domain.com"],  # Не "*"!
       ...
   )
   ```

3. **Используйте HTTPS**
   ```bash
   # Запуск за reverse proxy (nginx)
   uvicorn src.api.app:create_application --proxy-headers
   ```

4. **Rate limiting** (добавить отдельно)
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)
   ```

---

## 📝 Следующие шаги

**Этап 7:** Реализация сервисов (NoteService, ListService, ReminderService) + бизнес-логика для бота
