"""Privacy-safe activity analytics for bot diagnostics."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update

from src.db.models import BotActivityEvent, User


DOMAIN_LABELS = {
    "navigation": "навигация",
    "lists": "списки",
    "sharing": "общие списки",
    "medications": "лекарства",
    "reminders": "напоминания",
    "driver": "для водителя",
    "settings": "настройки",
    "system": "система",
    "notes_removed": "старые заметки",
    "unknown": "прочее",
}

FUNNEL_DEFINITIONS = [
    {
        "key": "lists",
        "label": "Списки",
        "stages": [
            ("open", "Открыли раздел", ["menu:lists", "lists_list"]),
            ("create_start", "Начали создание", ["list_create"]),
            ("item_add", "Добавляли пункт", ["list_add_item:{id}", "list_add_bulk:{id}"]),
            ("share", "Открывали шаринг", ["list_share:{id}"]),
        ],
    },
    {
        "key": "reminders",
        "label": "Напоминания",
        "stages": [
            ("open", "Открыли раздел", ["menu:reminders", "reminders_list"]),
            ("create_start", "Начали создание", ["reminder_create", "list_remind:{id}"]),
            ("date", "Выбрали дату", ["rem_date_today", "rem_date_tomorrow", "rem_date_after_tomorrow", "rem_date_next_week", "rem_date_custom"]),
            ("time", "Выбрали время", ["rem_time_10min", "rem_time_30min", "rem_time_1hour", "rem_time_2hour", "rem_time_clock_0900", "rem_time_clock_1200", "rem_time_clock_1800", "rem_time_clock_2100", "rem_time_custom"]),
            ("confirm", "Подтвердили", ["rem_confirm_create"]),
        ],
    },
    {
        "key": "medications",
        "label": "Лекарства",
        "stages": [
            ("open", "Открыли раздел", ["menu:medications", "medications_list"]),
            ("create_start", "Начали создание", ["med_create"]),
            ("dosage", "Указали дозировку", ["med_dosage:tablet1", "med_dosage:tablet_half", "med_dosage:drop1", "med_dosage:ml5", "med_dosage:skip"]),
            ("instructions", "Указали инструкцию", ["med_instr:after_food", "med_instr:during_food", "med_instr:before_food", "med_instr:with_water", "med_instr:separate", "med_instr:skip"]),
            ("importance", "Выбрали важность", ["med_importance:supplement", "med_importance:normal", "med_importance:important", "med_importance:critical"]),
            ("reminder", "Настраивали время", ["med_rem_freq:{id}:{id}", "med_rem_custom:{id}", "med_rem_time:{id}:{id}"]),
        ],
    },
    {
        "key": "driver",
        "label": "Для водителя",
        "stages": [
            ("open", "Открыли раздел", ["menu:driver", "driver_menu"]),
            ("vehicle_create", "Создавали авто", ["driver_vehicle_create"]),
            ("fuel_add", "Добавляли заправку", ["driver_fuel_add:{id}"]),
            ("expense_add", "Добавляли расход", ["driver_expense_add", "driver_expense_add:{id}"]),
            ("document_add", "Добавляли документ", ["driver_document_add", "driver_document_add:{id}"]),
            ("service_done", "Отмечали ТО", ["driver_service_done:{id}"]),
            ("templates", "Использовали шаблоны", ["driver_list_template:parts", "driver_list_template:trip_check", "driver_list_template:fluids_check", "driver_reminder_template:oil", "driver_reminder_template:fluids", "driver_reminder_template:wash", "driver_reminder_template:tire_pressure"]),
        ],
    },
]


class ActivityService:
    """Record and aggregate sanitized bot interaction events."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_event(
        self,
        *,
        event_type: str,
        event_name: str,
        domain: str,
        user_id: Optional[int] = None,
        telegram_id: Optional[int] = None,
        source: str = "telegram",
        metadata: Optional[dict[str, Any]] = None,
    ) -> BotActivityEvent:
        """Persist one sanitized activity event."""
        event = BotActivityEvent(
            user_id=user_id,
            telegram_id=telegram_id,
            source=source[:30],
            event_type=event_type[:30],
            event_name=event_name[:120],
            domain=domain[:30],
            metadata_json=metadata or None,
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def record_telegram_update(self, update: Update) -> Optional[BotActivityEvent]:
        """Record a Telegram update without storing message text or callback IDs."""
        telegram_user = update.effective_user
        if not telegram_user:
            return None

        event = parse_telegram_update(update)
        if not event:
            return None

        result = await self.db.execute(
            select(User.id).where(User.telegram_id == telegram_user.id)
        )
        user_id = result.scalar_one_or_none()

        return await self.record_event(
            user_id=user_id,
            telegram_id=telegram_user.id,
            event_type=event["event_type"],
            event_name=event["event_name"],
            domain=event["domain"],
            metadata=event.get("metadata"),
        )

    async def get_admin_event_summary(
        self,
        current_user_id: int,
        days: int = 7,
        top_limit: int = 5,
        user_id: Optional[int] = None,
    ) -> dict:
        """Aggregate activity for admin diagnostics."""
        now = datetime.now(timezone.utc)
        since_24h = now - timedelta(hours=24)
        since_days = now - timedelta(days=days)

        async def scalar(query) -> int:
            result = await self.db.execute(query)
            return result.scalar() or 0

        base_filters = [
            BotActivityEvent.created_at >= since_days,
        ]
        base_24h_filters = [
            BotActivityEvent.created_at >= since_24h,
        ]
        if user_id is not None:
            base_filters.append(BotActivityEvent.user_id == user_id)
            base_24h_filters.append(BotActivityEvent.user_id == user_id)
        other_user_filters = [
            *base_filters,
            BotActivityEvent.user_id.is_not(None),
            BotActivityEvent.user_id != current_user_id,
        ]

        total_24h = await scalar(
            select(func.count(BotActivityEvent.id)).where(*base_24h_filters)
        )
        total_period = await scalar(select(func.count(BotActivityEvent.id)).where(*base_filters))
        active_users_24h = await scalar(
            select(func.count(distinct(BotActivityEvent.user_id))).where(
                BotActivityEvent.created_at >= since_24h,
                BotActivityEvent.user_id.is_not(None),
                BotActivityEvent.user_id != current_user_id,
            )
        )
        active_users_period = await scalar(
            select(func.count(distinct(BotActivityEvent.user_id))).where(*other_user_filters)
        )

        domain_count = func.count(BotActivityEvent.id).label("count")
        domains_result = await self.db.execute(
            select(BotActivityEvent.domain, domain_count)
            .where(*base_filters)
            .group_by(BotActivityEvent.domain)
            .order_by(desc(domain_count))
            .limit(top_limit)
        )
        action_count = func.count(BotActivityEvent.id).label("count")
        actions_result = await self.db.execute(
            select(BotActivityEvent.domain, BotActivityEvent.event_name, action_count)
            .where(*base_filters)
            .group_by(BotActivityEvent.domain, BotActivityEvent.event_name)
            .order_by(desc(action_count))
            .limit(top_limit)
        )

        return {
            "period_days": days,
            "filtered_user_id": user_id,
            "events_24h": total_24h,
            "events_period": total_period,
            "active_other_users_24h": active_users_24h,
            "active_other_users_period": active_users_period,
            "top_domains": [
                {
                    "domain": domain,
                    "label": DOMAIN_LABELS.get(domain, domain),
                    "count": count,
                }
                for domain, count in domains_result.all()
            ],
            "top_actions": [
                {
                    "domain": domain,
                    "domain_label": DOMAIN_LABELS.get(domain, domain),
                    "event_name": event_name,
                    "label": format_event_label(event_name),
                    "count": count,
                }
                for domain, event_name, count in actions_result.all()
            ],
        }

    async def get_funnel_summary(self, days: int = 7, user_id: Optional[int] = None) -> dict:
        """Return basic product funnels from sanitized activity events."""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        funnels = []
        base_filters = [BotActivityEvent.created_at >= since]
        if user_id is not None:
            base_filters.append(BotActivityEvent.user_id == user_id)

        for definition in FUNNEL_DEFINITIONS:
            previous_count: Optional[int] = None
            stages = []
            for key, label, event_names in definition["stages"]:
                result = await self.db.execute(
                    select(func.count(BotActivityEvent.id)).where(
                        *base_filters,
                        BotActivityEvent.event_name.in_(event_names),
                    )
                )
                count = result.scalar() or 0
                drop_from_previous = None
                conversion_from_previous = None
                if previous_count is not None:
                    drop_from_previous = max(previous_count - count, 0)
                    conversion_from_previous = round((count / previous_count) * 100, 1) if previous_count else 0.0
                stages.append(
                    {
                        "key": key,
                        "label": label,
                        "count": count,
                        "drop_from_previous": drop_from_previous,
                        "conversion_from_previous": conversion_from_previous,
                    }
                )
                previous_count = count

            funnels.append(
                {
                    "key": definition["key"],
                    "label": definition["label"],
                    "stages": stages,
                }
            )

        return {
            "period_days": days,
            "filtered_user_id": user_id,
            "funnels": funnels,
        }


def parse_telegram_update(update: Update) -> Optional[dict[str, Any]]:
    """Return a sanitized event dict for a Telegram update."""
    if update.callback_query:
        raw_data = update.callback_query.data or "callback"
        event_name = normalize_callback_data(raw_data)
        return {
            "event_type": "callback",
            "event_name": event_name,
            "domain": infer_domain(event_name),
            "metadata": {
                "callback_prefix": raw_data.split(":", 1)[0][:80],
                "has_identifier": ":" in raw_data,
            },
        }

    message = update.effective_message
    if not message:
        return None

    text = message.text or ""
    if text.startswith("/"):
        command = text.split(maxsplit=1)[0].split("@", 1)[0]
        return {
            "event_type": "command",
            "event_name": command[:120],
            "domain": infer_domain(command),
            "metadata": {"has_args": len(text.split(maxsplit=1)) > 1},
        }

    if text:
        menu_action = normalize_menu_text(text)
        if menu_action:
            return {
                "event_type": "menu",
                "event_name": menu_action,
                "domain": infer_domain(menu_action),
                "metadata": {"message_len": len(text)},
            }
        return {
            "event_type": "text_input",
            "event_name": "text_input",
            "domain": "unknown",
            "metadata": {"message_len": len(text)},
        }

    return {
        "event_type": "message",
        "event_name": "non_text_message",
        "domain": "unknown",
        "metadata": {"has_attachment": True},
    }


def normalize_callback_data(value: str) -> str:
    """Remove row IDs and token-like values from callback names."""
    parts = value.split(":")
    if parts[0] == "startup_update_sent":
        return "startup_update_sent:{version}"

    normalized = [parts[0]]
    for part in parts[1:]:
        if part.isdigit():
            normalized.append("{id}")
        elif len(part) >= 10 and re.fullmatch(r"[A-Za-z0-9_-]+", part):
            normalized.append("{token}")
        else:
            normalized.append(part[:40])
    return ":".join(normalized)[:120]


def normalize_menu_text(text: str) -> Optional[str]:
    """Convert visible menu button text into stable event names."""
    normalized = text.strip().lower()
    if "списки" in normalized:
        return "menu:lists"
    if "лекарства" in normalized:
        return "menu:medications"
    if "напоминания" in normalized:
        return "menu:reminders"
    if "водител" in normalized:
        return "menu:driver"
    if "настройки" in normalized:
        return "menu:settings"
    if "поделиться" in normalized:
        return "menu:share_bot"
    if "помощь" in normalized:
        return "menu:help"
    return None


def infer_domain(event_name: str) -> str:
    """Infer product domain from a stable event name."""
    if event_name.startswith("startup_update_sent"):
        return "system"
    if event_name in {"/start", "/help", "/cancel", "home", "back", "cancel", "menu:help"}:
        return "navigation"
    if event_name.startswith(("list_share", "list_members", "list_member", "/join_list", "menu:share_bot", "share_bot")):
        return "sharing"
    if event_name.startswith(("checklist_",)):
        return "checklists"
    if event_name.startswith(("list_", "lists_", "menu:lists", "/import_list")):
        return "lists"
    if event_name.startswith(("med_", "medication", "menu:medications")):
        return "medications"
    if event_name.startswith(("rem_", "reminder", "reminders_", "menu:reminders")):
        return "reminders"
    if event_name.startswith(("driver_", "menu:driver")):
        return "driver"
    if event_name.startswith(("settings", "tz_", "menu:settings")):
        return "settings"
    if event_name.startswith(("note_", "notes_")):
        return "notes_removed"
    return "unknown"


def format_event_label(event_name: str) -> str:
    """Human-readable compact label for admin output."""
    if event_name.startswith("startup_update_sent"):
        return "отправлено сообщение об обновлении"

    known = {
        "/start": "команда запуска",
        "/help": "команда помощи",
        "/cancel": "команда отмены",
        "home": "возврат в главное меню",
        "back": "назад",
        "cancel": "отмена действия",
        "menu:lists": "кнопка меню: списки",
        "menu:medications": "кнопка меню: лекарства",
        "menu:reminders": "кнопка меню: напоминания",
        "menu:driver": "кнопка меню: водитель",
        "menu:settings": "кнопка меню: настройки",
        "menu:share_bot": "кнопка меню: поделиться ботом",
        "menu:help": "кнопка меню: помощь",
        "settings_menu": "открытие настроек",
        "settings_stats": "просмотр статистики",
        "settings_subscription": "просмотр подписки",
        "settings_web_login": "получение ссылки web-версии",
        "share_bot": "экран приглашения в бот",
        "lists_list": "открытие списков",
        "list_create": "создание списка",
        "list_add_item:{id}": "добавление пункта списка",
        "list_add_bulk:{id}": "пакетное добавление пунктов",
        "list_share:{id}": "открытие доступа к списку",
        "list_view:{id}": "просмотр списка",
        "checklist_start:{id}": "запуск чек-листа",
        "checklist_toggle:{id}:{id}": "отметка пункта чек-листа",
        "checklist_check_all:{id}": "отметка всех пунктов чек-листа",
        "checklist_finish:{id}": "завершение чек-листа",
        "checklist_cancel:{id}": "отмена чек-листа",
        "medications_list": "открытие лекарств",
        "med_create": "добавление лекарства",
        "med_taken:{id}": "отметка приема лекарства",
        "med_skip:{id}": "пропуск приема лекарства",
        "med_remind:{id}": "настройка времени приема",
        "med_edit:{id}": "редактирование лекарства",
        "reminders_list": "открытие напоминаний",
        "reminder_create": "создание напоминания",
        "rem_confirm_create": "подтверждение напоминания",
        "reminder_done:{id}": "отметка напоминания выполненным",
        "reminder_cancel:{id}": "отмена напоминания",
        "reminder_edit_text:{id}": "изменение текста напоминания",
        "reminder_edit_time:{id}": "изменение времени напоминания",
        "reminder_edit_repeat:{id}": "изменение повтора напоминания",
        "driver_menu": "открытие раздела водителя",
        "driver_vehicle_create": "добавление автомобиля",
        "driver_fuel_add:{id}": "добавление заправки",
        "driver_expense_add": "добавление расхода",
        "driver_expense_add:{id}": "добавление расхода",
        "driver_document_add": "добавление документа",
        "driver_document_add:{id}": "добавление документа",
        "driver_service_done:{id}": "отметка прохождения ТО",
        "text_input": "текстовый ввод",
        "non_text_message": "сообщение с вложением",
    }
    if event_name in known:
        return known[event_name]

    prefix_labels = {
        "checklist_": "прохождение чек-листа",
        "list_": "действие со списком",
        "lists_": "раздел списков",
        "med_": "действие с лекарством",
        "rem_": "создание напоминания",
        "reminder_": "действие с напоминанием",
        "driver_": "действие в разделе водителя",
        "settings": "действие в настройках",
        "tz_": "выбор часового пояса",
    }
    for prefix, label in prefix_labels.items():
        if event_name.startswith(prefix):
            return label

    return "прочее действие"
