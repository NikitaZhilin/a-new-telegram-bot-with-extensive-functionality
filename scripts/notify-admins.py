"""Send a short service alert to the bot admins (ADMIN_TELEGRAM_IDS) only.

Runs inside the bot container (it has the token and admin IDs):
    docker exec -i -e ALERT_TEXT="..." rememberme_bot-bot python - < scripts/notify-admins.py
"""

import os
import sys

import httpx

MAX_RECIPIENTS = 3


def main() -> int:
    text = (os.environ.get("ALERT_TEXT") or "").strip()
    token = os.environ.get("BOT_TOKEN", "")
    admins = [item.strip() for item in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",") if item.strip()]
    if not text or not token or not admins:
        print("nothing to send", file=sys.stderr)
        return 1
    if len(admins) > MAX_RECIPIENTS:
        print(f"refusing to alert {len(admins)} recipients", file=sys.stderr)
        return 1
    sent = 0
    with httpx.Client(timeout=30) as client:
        for chat_id in admins:
            response = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": text[:3900]},
            )
            sent += int(response.status_code == 200)
    print(f"alert sent to {sent} admin(s)")
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
