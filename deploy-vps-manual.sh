#!/usr/bin/env bash
set -euo pipefail

# Manual isolated VPS deploy for hosts without docker compose.
# Run on the VPS from any directory:
#   PROJECT_DIR=/opt/bots/rememberme bash deploy-vps-manual.sh

PROJECT_DIR="${PROJECT_DIR:-/opt/bots/rememberme}"
ENV_FILE="${ENV_FILE:-.env}"
PROJECT_RESOURCE_PREFIX="${PROJECT_RESOURCE_PREFIX:-rememberme_bot}"
APP_IMAGE="${APP_IMAGE:-rememberme_bot-app:latest}"
WORKER_IMAGE="${WORKER_IMAGE:-rememberme_bot-worker:latest}"
NETWORK="${NETWORK:-rememberme_bot_network}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rememberme_bot-postgres}"
POSTGRES_HOST="${POSTGRES_HOST:-$POSTGRES_CONTAINER}"
BOT_CONTAINER="${BOT_CONTAINER:-rememberme_bot-bot}"
API_CONTAINER="${API_CONTAINER:-rememberme_bot-api}"
WORKER_CONTAINER="${WORKER_CONTAINER:-rememberme_bot-worker}"
API_BIND_HOST="${API_BIND_HOST:-127.0.0.1}"
API_HOST_PORT="${API_HOST_PORT:-8000}"

assert_owned_container_name() {
  local value="$1"
  local label="$2"
  case "$value" in
    "$PROJECT_RESOURCE_PREFIX"-*) ;;
    *)
      echo "Refusing unsafe $label='$value'. Expected prefix '$PROJECT_RESOURCE_PREFIX-'." >&2
      exit 1
      ;;
  esac
}

assert_owned_container_name "$POSTGRES_CONTAINER" "POSTGRES_CONTAINER"
assert_owned_container_name "$BOT_CONTAINER" "BOT_CONTAINER"
assert_owned_container_name "$API_CONTAINER" "API_CONTAINER"
assert_owned_container_name "$WORKER_CONTAINER" "WORKER_CONTAINER"
if [ "$NETWORK" != "${PROJECT_RESOURCE_PREFIX}_network" ]; then
  echo "Refusing unsafe NETWORK='$NETWORK'. Expected '${PROJECT_RESOURCE_PREFIX}_network'." >&2
  exit 1
fi

cd "$PROJECT_DIR"

git pull --ff-only

if docker ps -a --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
  python3 - <<'PY'
from pathlib import Path
import os
import subprocess

path = Path(os.environ.get("ENV_FILE", ".env"))
lines = path.read_text().splitlines() if path.exists() else []
keys = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]
postgres_container = os.environ.get("POSTGRES_CONTAINER", "rememberme_bot-postgres")
values = {}
for key in keys:
    values[key] = subprocess.check_output(
        ["docker", "exec", postgres_container, "printenv", key],
        text=True,
    ).strip()

seen = set()
out = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
    if key in values:
        out.append(f"{key}={values[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY
fi

docker build -t "$APP_IMAGE" -f Dockerfile .
docker build -t "$WORKER_IMAGE" -f Dockerfile.worker .

docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK"

docker run --rm \
  --env-file "$ENV_FILE" \
  -e POSTGRES_HOST="$POSTGRES_HOST" \
  --network "$NETWORK" \
  "$APP_IMAGE" \
  sh -c 'DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB} python -m src.main init-db'

docker rm -f "$BOT_CONTAINER" "$API_CONTAINER" "$WORKER_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$BOT_CONTAINER" \
  --restart unless-stopped \
  --no-healthcheck \
  --env-file "$ENV_FILE" \
  -e POSTGRES_HOST="$POSTGRES_HOST" \
  --network "$NETWORK" \
  "$APP_IMAGE" \
  sh -c 'DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB} python -m src.main bot'

docker run -d \
  --name "$API_CONTAINER" \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -e POSTGRES_HOST="$POSTGRES_HOST" \
  --network "$NETWORK" \
  -p "${API_BIND_HOST}:${API_HOST_PORT}:8000" \
  "$APP_IMAGE" \
  sh -c 'DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB} python -m src.main api'

docker run -d \
  --name "$WORKER_CONTAINER" \
  --restart unless-stopped \
  --no-healthcheck \
  --env-file "$ENV_FILE" \
  -e POSTGRES_HOST="$POSTGRES_HOST" \
  --network "$NETWORK" \
  "$WORKER_IMAGE" \
  sh -c 'DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:5432/${POSTGRES_DB} python -m src.main worker'

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'rememberme_bot|NAMES'
docker logs --tail=80 "$BOT_CONTAINER"
docker logs --tail=80 "$API_CONTAINER"
docker logs --tail=80 "$WORKER_CONTAINER"
