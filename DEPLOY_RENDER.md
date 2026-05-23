# 🚀 Развёртывание на Render

**Дата:** 2026-02-19  
**Статус:** ✅ Готово к деплою

---

## 📋 Архитектура на Render

```
┌─────────────────────────────────────────────────────────┐
│                    Render Platform                       │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Bot         │  │  API         │  │  Worker      │  │
│  │  Web Service │  │  Web Service │  │  Background  │  │
│  │  (scale N)   │  │  (scale 1)   │  │  Job (1)     │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └─────────────────┼─────────────────┘           │
│                           │                             │
│                  ┌────────▼────────┐                    │
│                  │   PostgreSQL    │                    │
│                  │   (Managed DB)  │                    │
│                  └─────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

---

## 🔧 Предварительные требования

1. **GitHub репозиторий** с кодом
2. **Render аккаунт** (https://render.com)
3. **Telegram Bot Token** от @BotFather

---

## 📦 Шаг 1: PostgreSQL Database

### Создаём базу данных

1. В Render Dashboard нажмите **New +** → **PostgreSQL**
2. Заполните:
   - **Name:** `rememberme-db`
   - **Database:** `rememberme`
   - **User:** `postgres`
   - **Plan:** Free (или Starter за $7/мес)
   - **Region:** Выберите ближайшую

3. После создания сохраните:
   - **Internal Database URL:** `postgresql://postgres:***@dpg-xxx.db.render.com:5432/rememberme`
   - **External Database URL:** (для локальной разработки)

### Конвертируйте URL для asyncpg

```bash
# Render предоставляет:
postgresql://user:pass@host:port/db

# Для приложения нужно:
postgresql+asyncpg://user:pass@host:port/db
```

---

## 🤖 Шаг 2: Telegram Bot (Web Service)

### Создаём сервис

1. **New +** → **Web Service**
2. Подключите GitHub репозиторий
3. Заполните:

| Поле | Значение |
|------|----------|
| **Name** | `rememberme-bot` |
| **Region** | Frankfurt (или ближайшая) |
| **Branch** | `main` |
| **Root Directory** | `new_architecture` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main bot` |

### Environment Variables

```bash
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql+asyncpg://postgres:pass@dpg-xxx.db.render.com:5432/rememberme
ADMIN_TOKEN=your-super-secret-token
API_HOST=0.0.0.0
API_PORT=10000
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
WORKER_INTERVAL=60
```

### Scaling (важно!)

- **Instances:** `1` (или больше для масштабирования)
- **Instance Type:** Free или Starter ($7/мес)

### Health Check

- **Path:** `/health` (не нужен для бота, но можно добавить)
- **Port:** `10000`

---

## 🌐 Шаг 3: Admin API (Web Service)

### Создаём сервис

1. **New +** → **Web Service**
2. Подключите тот же репозиторий
3. Заполните:

| Поле | Значение |
|------|----------|
| **Name** | `rememberme-api` |
| **Region** | Та же что у бота |
| **Branch** | `main` |
| **Root Directory** | `new_architecture` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main api` |

### Environment Variables

```bash
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql+asyncpg://postgres:pass@dpg-xxx.db.render.com:5432/rememberme
ADMIN_TOKEN=your-super-secret-token
API_HOST=0.0.0.0
API_PORT=10000
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
WORKER_INTERVAL=60
```

### Scaling

- **Instances:** `1`
- **Instance Type:** Free или Starter

### Health Check

- **Path:** `/health`
- **Port:** `10000`

---

## ⏰ Шаг 4: Reminder Worker (Background Job)

### ⚠️ ВАЖНО: Single Instance Only!

Worker использует `SELECT ... FOR UPDATE SKIP LOCKED`, но для гарантии отсутствия дублей
запускайте **только 1 экземпляр**.

### Создаём Background Job

1. **New +** → **Background Job**
2. Подключите репозиторий
3. Заполните:

| Поле | Значение |
|------|----------|
| **Name** | `rememberme-worker` |
| **Region** | Та же что у бота |
| **Branch** | `main` |
| **Root Directory** | `new_architecture` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main worker` |

### Environment Variables

```bash
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
DATABASE_URL=postgresql+asyncpg://postgres:pass@dpg-xxx.db.render.com:5432/rememberme
ADMIN_TOKEN=your-super-secret-token
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
WORKER_INTERVAL=60
```

### Scaling (КРИТИЧНО!)

- **Instances:** `1` ⚠️ **НЕ МАСШТАБИРОВАТЬ!**
- **Instance Type:** Free или Starter

---

## 🔐 Environment Variables (сводная таблица)

| Переменная | Bot | API | Worker | Описание |
|------------|-----|-----|--------|----------|
| `BOT_TOKEN` | ✅ | ✅ | ✅ | Telegram bot token |
| `DATABASE_URL` | ✅ | ✅ | ✅ | PostgreSQL URL (asyncpg) |
| `ADMIN_TOKEN` | ✅ | ✅ | ✅ | Secret для API auth |
| `API_HOST` | ✅ | ✅ | ❌ | Host для API |
| `API_PORT` | ✅ | ✅ | ❌ | Port для API |
| `LOG_LEVEL` | ✅ | ✅ | ✅ | Уровень логирования |
| `TIMEZONE_DEFAULT` | ✅ | ✅ | ✅ | Timezone по умолчанию |
| `WORKER_INTERVAL` | ❌ | ❌ | ✅ | Интервал worker (сек) |

---

## 🚀 Команды для локального тестирования

### Docker Compose

```bash
cd new_architecture

# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f bot
docker-compose logs -f api
docker-compose logs -f worker

# Остановка
docker-compose down

# Пересборка
docker-compose up -d --build
```

### Локальный запуск без Docker

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск бота
python -m src.main bot

# Запуск API
python -m src.main api

# Запуск worker
python -m src.main worker
```

---

## 📊 Мониторинг на Render

### Bot

- **Dashboard:** https://dashboard.render.com
- **Logs:** Вкладка "Logs" веб-сервиса
- **Metrics:** Вкладка "Metrics"

### API

- **Swagger UI:** `https://rememberme-api.onrender.com/docs`
- **Health:** `https://rememberme-api.onrender.com/health`
- **Stats:** `https://rememberme-api.onrender.com/admin/stats` (с токеном)

### Worker

- **Logs:** Вкладка "Logs" background job
- **Status:** Проверка по логам "Processing X due reminder(s)"

---

## 🔒 Безопасность

### Production Checklist

1. **Смените все токены:**
   ```bash
   ADMIN_TOKEN=$(openssl rand -hex 32)
   ```

2. **Настройте CORS для API:**
   ```python
   # src/api/app.py
   allow_origins=["https://your-domain.com"]
   ```

3. **Используйте Secrets Manager:**
   - Render Secrets: https://dashboard.render.com/secrets
   - Или GitHub Secrets для CI/CD

4. **Включите Private Networking:**
   - Все сервисы в одной сети Render
   - Database только для внутренних сервисов

---

## 💰 Стоимость (оценка)

| Сервис | Plan | Цена/мес |
|--------|------|----------|
| PostgreSQL | Free | $0 |
| Bot | Free | $0 |
| API | Free | $0 |
| Worker | Free | $0 |
| **Итого** | | **$0** |

**При нагрузке:**

| Сервис | Plan | Цена/мес |
|--------|------|----------|
| PostgreSQL | Starter | $7 |
| Bot | Starter | $7 |
| API | Starter | $7 |
| Worker | Starter | $7 |
| **Итого** | | **$28** |

---

## 🐛 Troubleshooting

### Bot не запускается

```bash
# Проверьте логи
docker-compose logs bot

# Проверьте токен
echo $BOT_TOKEN
```

### Worker не отправляет напоминания

```bash
# Проверьте время в БД
psql $DATABASE_URL -c "SELECT id, remind_at_utc, notified_at FROM reminders LIMIT 5;"

# Проверьте логи worker
docker-compose logs worker
```

### API возвращает 401

```bash
# Проверьте токен
curl -H "X-Admin-Token: your-token" https://your-api.onrender.com/admin/stats

# Должен вернуть 200 OK
```

---

## 📝 Следующие шаги

1. ✅ Настроить CI/CD (GitHub Actions)
2. ✅ Добавить миграции (Alembic)
3. ✅ Настроить мониторинг (Sentry, Prometheus)
4. ✅ Добавить rate limiting для API
