"""Announcements the admin sends from the bot (О боте → 📣 Оповещение).

Nothing is sent automatically: the admin previews the text, sends it to
themselves, picks recipients or sends to everyone who has not got it yet.
Delivery is marked in bot_activity_events (``announcement_sent:<id>``), so the
same person is not messaged twice by «всем, кто ещё не получал». To prepare a
new announcement, change ``ANNOUNCEMENT_ID`` and the text.
"""

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import select

ANNOUNCEMENT_ID = "beta-testing-fixes-2026-10-14"

ANNOUNCEMENT_FIXES = (
    "Повторяющиеся напоминания больше не останавливаются после «Выполнено» или неудачной доставки.",
    "Ежемесячные напоминания на 29–31 число больше не сдвигаются на другие дни.",
    "После смены часового пояса напоминания остаются на тех же часах.",
    "Лекарства: «Принял» отмечает нужный приём, удалённое время приёма больше не присылает уведомления.",
    "Напоминание сохраняется сразу после выбора времени, а дату и время можно написать одной фразой: «завтра в 10 позвонить маме».",
    "«Автомобиль»: пробег и суммы можно вводить с единицами — «120 000 км», «2 500 ₽».",
    "Кнопки из старых сообщений больше не «крутятся» бесконечно, а меню закрывает незаконченный сценарий.",
)


def announcement_text(version: str) -> str:
    fixes = "\n".join(f"• {line}" for line in ANNOUNCEMENT_FIXES)
    return (
        "🧪 Бот работает в режиме тестирования\n"
        f"Версия {version}\n\n"
        "Что исправлено в последних обновлениях:\n"
        f"{fixes}\n\n"
        "Нашли ошибку или есть идея? Нажмите «💬 Обратная связь» ниже "
        "или отправьте /feedback — сообщение получит разработчик."
    )


EVENT_PREFIX = "announcement_sent"


def delivery_event_name(announcement_id: str = ANNOUNCEMENT_ID) -> str:
    return f"{EVENT_PREFIX}:{announcement_id}"[:120]


async def delivered_telegram_ids(session, announcement_id: str = ANNOUNCEMENT_ID) -> set[int]:
    from src.db.models import BotActivityEvent

    result = await session.execute(
        select(BotActivityEvent.telegram_id).where(
            BotActivityEvent.event_name == delivery_event_name(announcement_id),
            BotActivityEvent.domain == "system",
        )
    )
    return {row[0] for row in result.all() if row[0] is not None}


@dataclass
class BroadcastResult:
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    failed_ids: list[int] = field(default_factory=list)


async def send_announcement(
    bot,
    recipients: list[tuple[int, int | None]],
    session_factory,
    *,
    text: str,
    reply_markup=None,
    record: bool = True,
    pause_seconds: float = 0.05,
) -> BroadcastResult:
    """Send ``text`` to (telegram_id, user_id) pairs; mark delivery unless ``record`` is False."""
    from telegram.error import Forbidden

    from src.services.activity_service import ActivityService

    result = BroadcastResult()
    for telegram_id, user_id in recipients:
        try:
            await bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
            result.sent += 1
            delivered = True
        except Forbidden:
            result.blocked += 1
            delivered = False
        except Exception:
            result.failed += 1
            result.failed_ids.append(telegram_id)
            delivered = False
        if delivered and record:
            async with session_factory() as session:
                await ActivityService(session).record_event(
                    event_type="system",
                    event_name=delivery_event_name(),
                    domain="system",
                    user_id=user_id,
                    telegram_id=telegram_id,
                    source="system",
                    metadata={"announcement_id": ANNOUNCEMENT_ID},
                )
                await session.commit()
        if pause_seconds:
            await asyncio.sleep(pause_seconds)
    return result
