"""Send a database backup file to the bot admins (ADMIN_TELEGRAM_IDS) only.

Runs inside the bot container, so it uses the bot's own token and network:
    docker cp backup.sql.gz rememberme_bot-bot:/tmp/backup.sql.gz
    docker exec -i rememberme_bot-bot python - /tmp/backup.sql.gz < scripts/send-backup-telegram.py
"""

import os
import sys
from datetime import datetime, timezone

import httpx

MAX_RECIPIENTS = 3
MAX_BYTES = 45 * 1024 * 1024  # Telegram bots can send files up to 50 MB


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    token = os.environ.get("BOT_TOKEN", "")
    admins = [item.strip() for item in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",") if item.strip()]
    if not path or not os.path.isfile(path):
        print("backup file not found", file=sys.stderr)
        return 1
    if not token or not admins:
        print("BOT_TOKEN or ADMIN_TELEGRAM_IDS is empty; nothing sent", file=sys.stderr)
        return 1
    if len(admins) > MAX_RECIPIENTS:
        print(f"refusing to send a backup to {len(admins)} recipients", file=sys.stderr)
        return 1
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        print(f"backup is too big for Telegram: {size} bytes", file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    caption = (
        f"🗄 Бэкап базы RememberMe — {stamp}, {size / 1024:.0f} КБ.\n"
        "Здесь все данные пользователей: не пересылайте этот файл. "
        "Восстановление: gunzip -c файл | psql."
    )
    sent = 0
    with httpx.Client(timeout=60) as client:
        for chat_id in admins:
            with open(path, "rb") as handle:
                response = client.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id, "caption": caption},
                    files={"document": (os.path.basename(path), handle, "application/gzip")},
                )
            if response.status_code == 200 and response.json().get("ok"):
                sent += 1
            else:
                print(f"sending failed: HTTP {response.status_code}", file=sys.stderr)
    print(f"backup sent to {sent} of {len(admins)} admin(s)")
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
