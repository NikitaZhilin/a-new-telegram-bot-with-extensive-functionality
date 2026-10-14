#!/usr/bin/env bash
# Read-only health report for the RememberMe VPS. Changes nothing.
# Usage on the VPS: PROJECT_DIR=/opt/bots/rememberme bash scripts/server-health.sh
# Prints "KEY: value" lines; lines starting with "WARN:" need attention.
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/bots/rememberme}"
PREFIX="${COMPOSE_PROJECT_NAME:-rememberme_bot}"
cd "$PROJECT_DIR" 2>/dev/null || { echo "WARN: project dir $PROJECT_DIR not found"; exit 0; }

warn() { echo "WARN: $*"; }

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
parts = [f"{k}={v.get(\"status\")}" for k, v in sorted(services.items())]
print(f"{data.get(\"status\")} | version {data.get(\"version\")} | db {data.get(\"database\")} | " + ", ".join(parts))
' 2>&1 | tail -n 1)
  echo "APP STATUS: $status_json"
  case "$status_json" in ok*) ;; *) warn "app status is not ok: $status_json" ;; esac

  pending=$(docker exec "$PREFIX-postgres" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
    SELECT count(*) FILTER (WHERE status = '\''PENDING'\'' AND notify_at_utc < now() - interval '\''10 minutes'\''),
           count(*) FILTER (WHERE status = '\''FAILED'\'' AND updated_at > now() - interval '\''1 day'\'')
    FROM reminder_notifications"' 2>/dev/null | tr '|' ' ')
  if [ -n "$pending" ]; then
    set -- $pending
    echo "REMINDERS: overdue (>10 min) $1, failed last 24h $2"
    [ "${1:-0}" -gt 0 ] && warn "$1 reminder notifications are overdue"
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
exit 0
