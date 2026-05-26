> ARCHIVE NOTICE: This file is historical context only. It is not a current setup, launch, deployment, or security instruction. Use ../README.md, ../USER_GUIDE.md, ../TECHNICAL.md, and ../DEPLOYMENT.md instead.
# 📋 Этап 8: Docker + Render Deployment

**Дата:** 2026-02-19  
**Статус:** ✅ **ЗАВЕРШЕНО**

---

## 📁 Файлы

```
new_architecture/
├── Dockerfile                 # ⭐ Multi-stage build для bot/api
├── Dockerfile.worker          # ⭐ Отдельный для worker
├── docker-compose.yml         # ⭐ Postgres + bot + api + worker
├── .env.example               # ⭐ Шаблон переменных окружения
├── .dockerignore              # Исключения для Docker
└── DEPLOY_RENDER.md           # ⭐ Инструкция для Render
```

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose                            │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Bot        │  │  API        │  │  Worker     │         │
│  │  :10000     │  │  :8000      │  │  (none)     │         │
│  │  scale: N   │  │  scale: 1   │  │  scale: 1   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                 │                 │                │
│         └─────────────────┼─────────────────┘                │
│                           │                                  │
│                  ┌────────▼────────┐                         │
│                  │   PostgreSQL    │                         │
│                  │   :5432         │                         │
│                  └─────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 🐳 Docker Compose

### Запуск

```bash
cd new_architecture

# Копирование .env
cp .env.example .env

# Редактирование .env
nano .env  # или ваш редактор

# Запуск всех сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f
docker-compose logs -f bot
docker-compose logs -f worker
docker-compose logs -f api

# Остановка
docker-compose down

# Пересборка
docker-compose up -d --build
```

### Масштабирование

```bash
# Масштабирование бота (можно N экземпляров)
docker-compose up -d --scale bot=3

# Worker - ТОЛЬКО 1 экземпляр!
docker-compose up -d --scale worker=1  # ⚠️ НЕ МЕНЬШЕ И НЕ БОЛЬШЕ!
```

---

## 🔐 Environment Variables

### .env (локально)

```bash
# Telegram Bot
BOT_TOKEN=replace-with-bot-token

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=rememberme
POSTGRES_PORT=5432

DATABASE_URL=postgresql+asyncpg://postgres:your-secure-password@localhost:5432/rememberme
DB_ECHO=false

# Admin API
ADMIN_TOKEN=your-super-secret-token-here
API_HOST=0.0.0.0
API_PORT=8000

# Application
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
WORKER_INTERVAL=60
```

### Render (Production)

```bash
# Для всех 3 сервисов
BOT_TOKEN=replace-with-bot-token
DATABASE_URL=postgresql+asyncpg://postgres:pass@dpg-xxx.db.render.com:5432/rememberme
ADMIN_TOKEN=your-super-secret-token

# Для Bot и API
API_HOST=0.0.0.0
API_PORT=10000

# Для Worker
WORKER_INTERVAL=60

# Общие
LOG_LEVEL=INFO
TIMEZONE_DEFAULT=Europe/Moscow
```

---

## 🚀 Render: 3 Сервиса

### 1. Bot (Web Service)

| Параметр | Значение |
|----------|----------|
| **Type** | Web Service |
| **Name** | `rememberme-bot` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main bot` |
| **Instances** | `1` (можно масштабировать) |
| **Port** | `10000` |

**Scaling:** Можно увеличивать до N экземпляров для обработки больших нагрузок.

### 2. API (Web Service)

| Параметр | Значение |
|----------|----------|
| **Type** | Web Service |
| **Name** | `rememberme-api` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main api` |
| **Instances** | `1` |
| **Port** | `10000` |
| **Health Check** | `/health` |

**Scaling:** Можно масштабировать, но обычно достаточно 1 экземпляра.

### 3. Worker (Background Job) ⚠️

| Параметр | Значение |
|----------|----------|
| **Type** | Background Job |
| **Name** | `rememberme-worker` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -m src.main worker` |
| **Instances** | `1` ⚠️ **СТРОГО ОДИН!** |

**⚠️ КРИТИЧНО:** Worker должен быть в **единственном экземпляре**!

**Причина:** Хотя используется `SELECT ... FOR UPDATE SKIP LOCKED`, 
гарантировать отсутствие race conditions можно только при 1 экземпляре.

---

## 📊 Сравнение сервисов

| Характеристика | Bot | API | Worker |
|----------------|-----|-----|--------|
| **Type** | Web Service | Web Service | Background Job |
| **Port** | 10000 | 10000 | None |
| **Scaling** | ✅ N экземпляров | ✅ N экземпляров | ❌ Строго 1 |
| **Health Check** | Опционально | `/health` | По логам |
| **Public URL** | Нет | Да | Нет |
| **Зависимости** | DB | DB | DB + Bot |

---

## 🔧 Dockerfile

### Multi-stage build (bot/api)

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder
# Install dependencies, build wheels

# Stage 2: Production
FROM python:3.11-slim as production
# Copy wheels, install, run
```

**Преимущества:**
- Минимальный размер образа (~150MB)
- Нет build-зависимостей в production
- Non-root user для безопасности

### Dockerfile.worker

Отдельный файл для worker с health check по процессу.

---

## 🏥 Health Checks

### Bot

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

### API

```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Worker

```dockerfile
HEALTHCHECK --interval=60s --timeout=30s --retries=3 \
    CMD pgrep -f "reminder_worker" || exit 1
```

---

## 💰 Стоимость Render

### Free Plan

| Сервис | Стоимость |
|--------|-----------|
| PostgreSQL (90 дней) | $0 |
| Bot (750 часов) | $0 |
| API (750 часов) | $0 |
| Worker (500 часов) | $0 |
| **Итого** | **$0** |

### Production

| Сервис | Plan | Стоимость/мес |
|--------|------|---------------|
| PostgreSQL | Starter | $7 |
| Bot | Starter | $7 |
| API | Starter | $7 |
| Worker | Starter | $7 |
| **Итого** | | **$28** |

---

## 📝 Команды для управления

### Локально (Docker Compose)

```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Логи
docker-compose logs -f bot
docker-compose logs -f api
docker-compose logs -f worker

# Перезапуск сервиса
docker-compose restart bot

# Масштабирование бота
docker-compose up -d --scale bot=3

# Проверка статуса
docker-compose ps

# Вход в контейнер
docker-compose exec bot bash

# База данных
docker-compose exec postgres psql -U postgres -d rememberme
```

### Render

```bash
# Через Render CLI (установить отдельно)
renderctl services list
renderctl logs show rememberme-bot
renderctl services restart rememberme-bot

# Или через Web Dashboard
https://dashboard.render.com
```

---

## 🔒 Безопасность

### Production Checklist

1. **Смените ADMIN_TOKEN:**
   ```bash
   ADMIN_TOKEN=$(openssl rand -hex 32)
   ```

2. **Сложный пароль PostgreSQL:**
   ```bash
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   ```

3. **Render Secrets:**
   - Сохраните токены в Render Secrets
   - Не храните в .env файле

4. **Private Networking:**
   - Включите для всех сервисов
   - Database только для внутренней сети

5. **CORS для API:**
   ```python
   # src/api/app.py
   allow_origins=["https://your-domain.com"]  # Не "*"!
   ```

---

## 📊 Мониторинг

### Render Dashboard

- **Logs:** Вкладка "Logs" каждого сервиса
- **Metrics:** Вкладка "Metrics" (CPU, memory)
- **Alerts:** Настройте уведомления по email

### Логи worker

```
INFO: Reminder worker started
INFO: Processing 5 due reminder(s)
INFO: Sent reminder 123 to user 456
INFO: Reminder processing cycle completed
```

### API endpoints

```bash
# Health check
curl https://rememberme-api.onrender.com/health

# Statistics (с токеном)
curl -H "X-Admin-Token: your-token" \
     https://rememberme-api.onrender.com/admin/stats

# Due reminders
curl -H "X-Admin-Token: your-token" \
     https://rememberme-api.onrender.com/admin/reminders/due
```

---

## ✅ Чеклист деплоя

| Шаг | Статус |
|-----|--------|
| Создать PostgreSQL на Render | ✅ |
| Создать Bot (Web Service) | ✅ |
| Создать API (Web Service) | ✅ |
| Создать Worker (Background Job) | ✅ |
| Настроить Environment Variables | ✅ |
| Проверить логи | ✅ |
| Протестировать API | ✅ |
| Проверить worker | ✅ |

---

## 📚 Ссылки

- **Render Dashboard:** https://dashboard.render.com
- **Render CLI:** https://render.github.io/docs/cli
- **PostgreSQL:** https://render.com/docs/postgresql
- **Web Services:** https://render.com/docs/web-services
- **Background Jobs:** https://render.com/docs/background-jobs

---

## 🎯 ИТОГ

**Статус:** ✅ **ЭТАП 8 ЗАВЕРШЁН НА 100%**

**Создано:**
- ✅ Dockerfile (multi-stage)
- ✅ Dockerfile.worker (single instance)
- ✅ docker-compose.yml (4 сервиса)
- ✅ .env.example (шаблон)
- ✅ .dockerignore
- ✅ DEPLOY_RENDER.md (инструкция)

**Готово к:**
- ✅ Локальному запуску: `docker-compose up -d`
- ✅ Деплою на Render (3 сервиса)
- ✅ Масштабированию бота (N экземпляров)
- ✅ Worker (строго 1 экземпляр)
