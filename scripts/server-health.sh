#!/usr/bin/env bash
# Read-only health report for the RememberMe VPS. Changes nothing.
# Usage on the VPS: PROJECT_DIR=/opt/bots/rememberme bash scripts/server-health.sh
# Prints "KEY: value" lines; lines starting with "WARN:" need attention.
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/bots/rememberme}"
PREFIX="${COMPOSE_PROJECT_NAME:-rememberme_bot}"
cd "$PROJECT_DIR" 2>/dev/null || { echo "WARN: project dir $PROJECT_DIR not found"; exit 0; }

WARNINGS=""
warn() { echo "WARN: $*"; WARNINGS="${WARNINGS}• $*
"; }

echo "HOST: $(hostname) | uptime: $(uptime -p 2>/dev/null || uptime)"
read -r load1 load5 load15 _ < /proc/loadavg
cpus=$(nproc 2>/dev/null || echo 1)
echo "LOAD: $load1 / $load5 / $load15 (CPU: $cpus)"
awk -v l="$load5" -v c="$cpus" 'BEGIN { exit !(l > c * 1.5) }' && warn "high load: $load5 on $cpus CPU"

mem_line=$(free -m | awk '/^Mem:/ {printf "%d/%d MB used, available %d MB", $3, $2, $7}')
echo "MEMORY: $mem_line"
avail=$(free -m | awk '/^Mem:/ {print $7}')
[ "${avail:-0}" -lt 150 ] && warn "low free memory: ${avail} MB"
swap=$(free -m | awk '/^Swap:/ {printf "%d/%d MB", $3, $2}')
echo "SWAP: $swap"

disk=$(df -P / | awk 'NR==2 {print $5" used, "int($4/1024)" MB free"}')
echo "DISK /: $disk"
used_pct=$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')
[ "${used_pct:-0}" -ge 85 ] && warn "disk almost full: ${used_pct}%"

if command -v docker >/dev/null 2>&1; then
  echo "DOCKER DISK: $(docker system df --format '{{.Type}} {{.Size}} (reclaimable {{.Reclaimable}})' 2>/dev/null | tr '\n' ';')"
  for svc in postgres bot api worker; do
    name="$PREFIX-$svc"
    if ! docker inspect "$name" >/dev/null 2>&1; then
      warn "container $name not found"
      continue
    fi
    state=$(docker inspect -f '{{.State.Status}}' "$name")
    started=$(docker inspect -f '{{.State.StartedAt}}' "$name" | cut -c1-19)
    restarts=$(docker inspect -f '{{.RestartCount}}' "$name")
    health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$name")
    usage=$(docker stats --no-stream --format '{{.CPUPerc}} CPU, {{.MemUsage}}' "$name" 2>/dev/null)
    errors=$(docker logs --since 24h "$name" 2>&1 | grep -ciE '"level": ?"error"|traceback|exception' || true)
    echo "CONTAINER $svc: $state since $started UTC, restarts $restarts, health $health, $usage, errors 24h: $errors"
    [ "$state" != "running" ] && warn "$svc is $state"
    [ "${restarts:-0}" -gt 3 ] && warn "$svc restarted $restarts times"
    [ "${errors:-0}" -gt 20 ] && warn "$svc logged $errors errors in 24h"
  done

  # Second bot instance with the same token shows up as getUpdates conflicts.
  conflicts=$(docker logs --since 24h "$PREFIX-bot" 2>&1 | grep -ci 'conflict' || true)
  echo "BOT getUpdates CONFLICTS 24h: ${conflicts:-0}"
  [ "${conflicts:-0}" -gt 0 ] && warn "another bot instance is polling with the same token"

  status_json=$(docker exec "$PREFIX-api" python -c '
import json, os, urllib.request
req = urllib.request.Request("http://localhost:8000/admin/service-status", headers={"X-Admin-Token": os.environ.get("ADMIN_TOKEN", "")})
data = json.load(urllib.request.urlopen(req, timeout=10))
services = data.get("services", {})
parts = ["%s=%s" % (name, info.get("status")) for name, info in sorted(services.items())]
print("%s | version %s | db %s | %s" % (data.get("status"), data.get("version"), data.get("database"), ", ".join(parts)))
' 2>&1 | tail -n 1)
  echo "APP STATUS: $status_json"
  case "$status_json" in ok*) ;; *) warn "app status is not ok: $status_json" ;; esac

  pending=$(docker exec "$PREFIX-postgres" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
    SELECT count(*) FILTER (WHERE n.status = '\''PENDING'\'' AND r.status = '\''ACTIVE'\'' AND n.notify_at_utc < now() - interval '\''10 minutes'\''),
           count(*) FILTER (WHERE n.status = '\''FAILED'\'' AND n.updated_at > now() - interval '\''1 day'\'')
    FROM reminder_notifications n JOIN reminders r ON r.id = n.reminder_id"' 2>/dev/null | tr '|' ' ')
  if [ -n "$pending" ]; then
    set -- $pending
    echo "REMINDERS: overdue (>10 min) $1, failed last 24h $2"
    if [ "${1:-0}" -gt 0 ]; then
      warn "$1 reminder notifications are overdue"
      docker exec "$PREFIX-postgres" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
        SELECT '\''OVERDUE: notification '\'' || n.id || '\'' reminder '\'' || r.id || '\'' ('\'' || r.source_module || '\'', '\'' || r.repeat_rule || '\'', '\'' || r.status || '\'') due '\'' || to_char(n.notify_at_utc, '\''YYYY-MM-DD HH24:MI'\'') || '\'' UTC, user tz '\'' || u.timezone || '\'', error: '\'' || coalesce(left(n.last_error, 160), '\''-'\'')
        FROM reminder_notifications n JOIN reminders r ON r.id = n.reminder_id JOIN users u ON u.id = r.user_id
        WHERE n.status = '\''PENDING'\'' AND r.status = '\''ACTIVE'\'' AND n.notify_at_utc < now() - interval '\''10 minutes'\''
        ORDER BY n.notify_at_utc LIMIT 5"' 2>&1
    fi
  fi
  new_errors=$(docker exec "$PREFIX-postgres" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM error_events WHERE resolved_at IS NULL AND last_seen_at > now() - interval '\''1 day'\''"' 2>/dev/null)
  if [ -n "$new_errors" ]; then
    echo "ERROR JOURNAL: open kinds seen in 24h: $new_errors"
    [ "${new_errors:-0}" -gt 0 ] && warn "$new_errors error kind(s) in the journal in 24h (Настройки → О боте → Журнал ошибок)"
  fi
  users=$(docker exec "$PREFIX-postgres" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM users"' 2>/dev/null)
  [ -n "$users" ] && echo "USERS: $users"
else
  warn "docker not available"
fi

latest_backup=$(ls -1t "$PROJECT_DIR"/backups/rememberme-*.sql.gz 2>/dev/null | head -n 1)
if [ -n "$latest_backup" ]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$latest_backup") ) / 3600 ))
  echo "BACKUP: $(basename "$latest_backup"), $(du -h "$latest_backup" | cut -f1), ${age_h}h ago"
  [ "$age_h" -gt 26 ] && warn "last backup is ${age_h}h old"
else
  warn "no database backups in $PROJECT_DIR/backups"
fi
[ -f /etc/cron.d/rememberme-backup ] && echo "BACKUP CRON: installed" || warn "backup cron is not installed"
last_log=$(tail -n 1 "$PROJECT_DIR/logs/backup.log" 2>/dev/null)
case "$last_log" in
  *"Permission denied"*|*rror*|*"not running"*|*"unexpectedly small"*) warn "last backup run failed: ${last_log:0:160}" ;;
esac

# Daily run: tell the admins in Telegram when something needs attention, so a
# problem (like backups that silently stopped) is not noticed days later.
if [ "${NOTIFY_ADMINS:-0}" = "1" ] && [ -n "$WARNINGS" ] && [ -f "$PROJECT_DIR/scripts/notify-admins.py" ]; then
  alert="⚠️ RememberMe: проверка сервера нашла проблемы

${WARNINGS}
Подробности — в GitHub Actions → Server health."
  docker exec -u 0 -i -e ALERT_TEXT="$alert" "$PREFIX-bot" python - < "$PROJECT_DIR/scripts/notify-admins.py" >/dev/null 2>&1 \
    && echo "ALERT: sent to admins" || echo "ALERT: could not be sent"
fi
exit 0
