#!/usr/bin/env bash
set -euo pipefail

# Create a PostgreSQL backup for the isolated RememberMe deployment.
# This script intentionally works only with resources prefixed by rememberme_bot.

PROJECT_DIR="${PROJECT_DIR:-/opt/bots/rememberme}"
PROJECT_RESOURCE_PREFIX="${PROJECT_RESOURCE_PREFIX:-rememberme_bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rememberme_bot-postgres}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MIN_BACKUP_BYTES="${MIN_BACKUP_BYTES:-512}"

case "$POSTGRES_CONTAINER" in
  "$PROJECT_RESOURCE_PREFIX"-*) ;;
  *)
    echo "Refusing unsafe POSTGRES_CONTAINER='$POSTGRES_CONTAINER'. Expected prefix '$PROJECT_RESOURCE_PREFIX-'." >&2
    exit 1
    ;;
esac

if [ -z "$BACKUP_DIR" ] || [ "$BACKUP_DIR" = "/" ] || [ "$BACKUP_DIR" = "/opt" ]; then
  echo "Refusing unsafe BACKUP_DIR='$BACKUP_DIR'." >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || { echo "docker is required." >&2; exit 1; }
command -v gzip >/dev/null 2>&1 || { echo "gzip is required." >&2; exit 1; }

if ! docker ps --format '{{.Names}}' | grep -qx "$POSTGRES_CONTAINER"; then
  echo "Postgres container is not running: $POSTGRES_CONTAINER" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

db_user="$(docker exec "$POSTGRES_CONTAINER" printenv POSTGRES_USER | tr -d '\r')"
db_name="$(docker exec "$POSTGRES_CONTAINER" printenv POSTGRES_DB | tr -d '\r')"

if [ -z "$db_user" ] || [ -z "$db_name" ]; then
  echo "POSTGRES_USER or POSTGRES_DB is empty inside $POSTGRES_CONTAINER." >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
tmp_file="$BACKUP_DIR/.rememberme-$timestamp.sql.gz.tmp"
backup_file="$BACKUP_DIR/rememberme-$timestamp.sql.gz"

cleanup() {
  rm -f "$tmp_file"
}
trap cleanup EXIT

docker exec "$POSTGRES_CONTAINER" pg_dump \
  -U "$db_user" \
  -d "$db_name" \
  --no-owner \
  --no-acl \
  | gzip -c > "$tmp_file"

gzip -t "$tmp_file"

backup_size="$(wc -c < "$tmp_file" | tr -d ' ')"
if [ "$backup_size" -lt "$MIN_BACKUP_BYTES" ]; then
  echo "Backup is unexpectedly small: $backup_size bytes." >&2
  exit 1
fi

mv "$tmp_file" "$backup_file"
chmod 600 "$backup_file"
trap - EXIT

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'rememberme-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Backup created: $backup_file ($backup_size bytes)"
