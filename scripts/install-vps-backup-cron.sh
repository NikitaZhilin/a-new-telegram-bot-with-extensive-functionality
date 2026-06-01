#!/usr/bin/env bash
set -euo pipefail

# Install a root cron job that creates regular RememberMe database backups.
# It only writes /etc/cron.d/rememberme-backup and project backup/log files.

PROJECT_DIR="${PROJECT_DIR:-/opt/bots/rememberme}"
PROJECT_RESOURCE_PREFIX="${PROJECT_RESOURCE_PREFIX:-rememberme_bot}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-rememberme_bot-postgres}"
BACKUP_INTERVAL_CRON="${BACKUP_INTERVAL_CRON:-17 */6 * * *}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
CRON_FILE="${CRON_FILE:-/etc/cron.d/rememberme-backup}"
BACKUP_SCRIPT="$PROJECT_DIR/scripts/backup-vps.sh"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/backup.log"

case "$POSTGRES_CONTAINER" in
  "$PROJECT_RESOURCE_PREFIX"-*) ;;
  *)
    echo "Refusing unsafe POSTGRES_CONTAINER='$POSTGRES_CONTAINER'. Expected prefix '$PROJECT_RESOURCE_PREFIX-'." >&2
    exit 1
    ;;
esac

if [ ! -f "$BACKUP_SCRIPT" ]; then
  echo "Backup script was not found: $BACKUP_SCRIPT" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR" "$LOG_DIR"
chmod 700 "$BACKUP_DIR"
chmod 755 "$LOG_DIR"
chmod +x "$BACKUP_SCRIPT"

cat > "$CRON_FILE" <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

$BACKUP_INTERVAL_CRON root PROJECT_DIR=$PROJECT_DIR PROJECT_RESOURCE_PREFIX=$PROJECT_RESOURCE_PREFIX POSTGRES_CONTAINER=$POSTGRES_CONTAINER RETENTION_DAYS=$RETENTION_DAYS $BACKUP_SCRIPT >> $LOG_FILE 2>&1
EOF

chmod 644 "$CRON_FILE"

echo "RememberMe backup cron installed: $CRON_FILE"
echo "Schedule: $BACKUP_INTERVAL_CRON"
echo "Backup directory: $BACKUP_DIR"
