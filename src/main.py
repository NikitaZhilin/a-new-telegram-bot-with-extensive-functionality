"""
Main entry point for the RememberMe Bot application.

Usage:
    python -m src.main bot       # Run Telegram bot
    python -m src.main api       # Run FastAPI API
    python -m src.main worker    # Run reminder worker
    python -m src.main all       # Run all services
    python -m src.main bot --dry-run
    python -m src.main worker --dry-run
    python -m src.main all --dry-run
"""

import asyncio
import sys
import logging
from pathlib import Path
from contextlib import suppress
import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from src.config import settings
from src.db.base import Base
from src.db.session import engine, async_session_maker


# Configure logging
def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper()),
        stream=sys.stdout
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_alembic_config() -> Config:
    """Build an Alembic config that uses the active application DATABASE_URL."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


async def _database_has_table(table_name: str) -> bool:
    """Return whether a table exists in the current PostgreSQL database."""
    query = text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = :table_name
        )
        """
    )
    async with engine.begin() as conn:
        result = await conn.execute(query, {"table_name": table_name})
        return bool(result.scalar())


async def _run_alembic_upgrade_head() -> None:
    """Run Alembic upgrade head without nesting event loops."""
    await asyncio.to_thread(command.upgrade, _make_alembic_config(), "head")


async def _run_alembic_stamp_head() -> None:
    """Stamp an already-compatible legacy database as migrated."""
    await asyncio.to_thread(command.stamp, _make_alembic_config(), "head")


async def _ensure_legacy_unversioned_schema() -> None:
    """Bring old create_all-based databases to the current schema before stamping."""
    # Import models before create_all so SQLAlchemy registers every table.
    import src.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS list_id INTEGER"))
        await conn.execute(text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS medication_id INTEGER"))
        await conn.execute(text("ALTER TABLE lists ADD COLUMN IF NOT EXISTS source_module VARCHAR(30) NOT NULL DEFAULT 'general'"))
        await conn.execute(text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS source_module VARCHAR(30) NOT NULL DEFAULT 'general'"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_list_id ON reminders (list_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_medication_id ON reminders (medication_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_lists_source_module ON lists (source_module)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_source_module ON reminders (source_module)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_user_source_status ON reminders (user_id, source_module, status)"))
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS bot_activity_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    telegram_id BIGINT,
                    source VARCHAR(30) NOT NULL DEFAULT 'telegram',
                    event_type VARCHAR(30) NOT NULL,
                    event_name VARCHAR(120) NOT NULL,
                    domain VARCHAR(30) NOT NULL DEFAULT 'general',
                    metadata_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_user_id ON bot_activity_events (user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_telegram_id ON bot_activity_events (telegram_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_event_type ON bot_activity_events (event_type)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_event_name ON bot_activity_events (event_name)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_domain ON bot_activity_events (domain)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_events_created_at ON bot_activity_events (created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_user_created ON bot_activity_events (user_id, created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_domain_created ON bot_activity_events (domain, created_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_bot_activity_event_created ON bot_activity_events (event_name, created_at)"))
        await conn.execute(
            text(
                """
                UPDATE lists
                SET source_module = 'driver'
                WHERE title IN (
                    '🚗 Запчасти к покупке',
                    '🚗 Проверка перед поездкой',
                    '💧 Проверка жидкостей'
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE reminders
                SET source_module = 'medication'
                WHERE medication_id IS NOT NULL
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE reminders
                SET source_module = 'list'
                WHERE list_id IS NOT NULL
                  AND source_module = 'general'
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE reminders
                SET source_module = 'driver'
                WHERE text IN (
                    'Заменить моторное масло и масляный фильтр',
                    'Проверить уровни жидкостей: масло, антифриз, тормозная, омывайка',
                    'Помыть кузов и убрать салон',
                    'Проверить давление в шинах',
                    'Запланировать прохождение ТО'
                )
                """
            )
        )
        await conn.execute(text("ALTER TABLE medication_intakes ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'TAKEN'"))
        await conn.execute(text("ALTER TABLE medications ADD COLUMN IF NOT EXISTS importance VARCHAR(20) NOT NULL DEFAULT 'normal'"))
        await conn.execute(text("ALTER TABLE list_share_tokens ADD COLUMN IF NOT EXISTS token_type VARCHAR(20) NOT NULL DEFAULT 'copy'"))
        await conn.execute(text("ALTER TABLE list_share_tokens ADD COLUMN IF NOT EXISTS access_role VARCHAR(20) NOT NULL DEFAULT 'editor'"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_source VARCHAR(100)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_admin ON users (is_admin)"))
        await conn.execute(text("ALTER TABLE driver_vehicles ADD COLUMN IF NOT EXISTS manual_mileage_km INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(
            text(
                """
                UPDATE driver_vehicles
                SET
                    manual_mileage_km = GREATEST(COALESCE(manual_mileage_km, current_mileage_km, 0), 0),
                    current_mileage_km = GREATEST(COALESCE(current_mileage_km, 0), 0),
                    service_interval_km = GREATEST(COALESCE(service_interval_km, 10000), 1),
                    service_interval_months = GREATEST(COALESCE(service_interval_months, 12), 1),
                    last_service_mileage_km = CASE
                        WHEN last_service_mileage_km IS NULL THEN NULL
                        ELSE GREATEST(last_service_mileage_km, 0)
                    END
                """
            )
        )
        await conn.execute(
            text(
                """
                UPDATE driver_fuel_entries
                SET
                    mileage_km = GREATEST(COALESCE(mileage_km, 0), 0),
                    liters = CASE WHEN liters <= 0 THEN 0.01 ELSE liters END,
                    total_cost = CASE WHEN total_cost <= 0 THEN 0.01 ELSE total_cost END,
                    price_per_liter = CASE
                        WHEN liters > 0 AND total_cost > 0 THEN total_cost / liters
                        ELSE NULL
                    END,
                    consumption_l_per_100 = CASE
                        WHEN consumption_l_per_100 IS NULL THEN NULL
                        ELSE GREATEST(consumption_l_per_100, 0)
                    END,
                    cost_per_km = CASE
                        WHEN cost_per_km IS NULL THEN NULL
                        ELSE GREATEST(cost_per_km, 0)
                    END
                """
            )
        )
        legacy_constraints = {
            "ck_driver_vehicles_manual_mileage_non_negative": (
                "driver_vehicles",
                "manual_mileage_km >= 0",
            ),
            "ck_driver_vehicles_current_mileage_non_negative": (
                "driver_vehicles",
                "current_mileage_km >= 0",
            ),
            "ck_driver_vehicles_service_interval_km_positive": (
                "driver_vehicles",
                "service_interval_km > 0",
            ),
            "ck_driver_vehicles_service_interval_months_positive": (
                "driver_vehicles",
                "service_interval_months > 0",
            ),
            "ck_driver_vehicles_year_reasonable": (
                "driver_vehicles",
                "year IS NULL OR (year >= 1886 AND year <= 2100)",
            ),
            "ck_driver_vehicles_last_service_mileage_non_negative": (
                "driver_vehicles",
                "last_service_mileage_km IS NULL OR last_service_mileage_km >= 0",
            ),
            "ck_driver_fuel_entries_mileage_non_negative": (
                "driver_fuel_entries",
                "mileage_km >= 0",
            ),
            "ck_driver_fuel_entries_liters_positive": (
                "driver_fuel_entries",
                "liters > 0",
            ),
            "ck_driver_fuel_entries_total_cost_positive": (
                "driver_fuel_entries",
                "total_cost > 0",
            ),
            "ck_driver_fuel_entries_price_positive": (
                "driver_fuel_entries",
                "price_per_liter IS NULL OR price_per_liter > 0",
            ),
            "ck_driver_fuel_entries_consumption_non_negative": (
                "driver_fuel_entries",
                "consumption_l_per_100 IS NULL OR consumption_l_per_100 >= 0",
            ),
            "ck_driver_fuel_entries_cost_per_km_non_negative": (
                "driver_fuel_entries",
                "cost_per_km IS NULL OR cost_per_km >= 0",
            ),
        }
        for name, (table, expression) in legacy_constraints.items():
            await conn.execute(
                text(
                    f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint WHERE conname = '{name}'
                        ) THEN
                            ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({expression});
                        END IF;
                    END $$;
                    """
                )
            )


async def init_db() -> None:
    """Initialize or migrate the database schema to the latest Alembic revision."""
    has_alembic_version = await _database_has_table("alembic_version")
    has_existing_app_schema = await _database_has_table("users")

    if has_alembic_version or not has_existing_app_schema:
        await _run_alembic_upgrade_head()
        return

    await _ensure_legacy_unversioned_schema()
    await _run_alembic_stamp_head()


async def check_db_connection() -> None:
    """Verify that the configured database accepts a simple query."""
    async with async_session_maker() as session:
        await session.execute(text("SELECT 1"))


def count_bot_handlers(application) -> int:
    """Count registered Telegram handlers across all handler groups."""
    return sum(len(handlers) for handlers in application.handlers.values())


async def dry_run_bot() -> None:
    """Build the Telegram application without network initialization."""
    from src.bot.app import create_application

    logger = structlog.get_logger(__name__)

    bot_app = create_application()
    logger.info(
        "Bot dry-run completed",
        handlers=count_bot_handlers(bot_app),
        webhook_configured=bool(settings.WEBHOOK_URL),
    )


async def dry_run_worker() -> None:
    """Build the worker service and verify database access without Telegram calls."""
    from telegram import Bot
    from src.repositories.reminder_repo import ReminderRepository
    from src.worker import ReminderWorkerService

    logger = structlog.get_logger(__name__)

    bot = Bot(token=settings.BOT_TOKEN)
    worker = ReminderWorkerService(
        bot=bot,
        batch_size=100,
        poll_interval=settings.WORKER_INTERVAL,
    )

    async with async_session_maker() as session:
        ReminderRepository(session)
        await session.execute(text("SELECT 1"))

    logger.info(
        "Worker dry-run completed",
        service=worker.__class__.__name__,
        poll_interval=worker.poll_interval,
    )


async def dry_run_all() -> None:
    """Check API, bot, and worker factories without starting external loops."""
    from src.api.app import create_application

    logger = structlog.get_logger(__name__)

    api_app = create_application()
    await dry_run_bot()
    await dry_run_worker()

    logger.info(
        "All services dry-run completed",
        api=api_app.title,
        bot="ok",
        worker="ok",
    )


async def run_bot() -> None:
    """Run Telegram bot."""
    from src.bot.app import create_application
    from src.bot.keyboards import get_main_menu_keyboard
    from src.repositories.user_repo import UserRepository
    from telegram import BotCommand
    
    logger = structlog.get_logger(__name__)
    
    bot_app = create_application()
    initialized = False
    started = False
    polling_started = False

    await bot_app.initialize()
    initialized = True
    await bot_app.start()
    started = True

    await bot_app.bot.set_my_commands(
        [
            BotCommand("start", "Открыть свежее меню"),
            BotCommand("help", "Помощь"),
            BotCommand("import_list", "Импортировать копию списка"),
            BotCommand("join_list", "Присоединиться к общему списку"),
            BotCommand("cancel", "Отменить текущий сценарий"),
        ]
    )
    
    if settings.WEBHOOK_URL:
        await bot_app.bot.set_webhook(settings.WEBHOOK_URL)
        logger.info("Webhook set", url=settings.WEBHOOK_URL)
    else:
        await bot_app.bot.delete_webhook()
        logger.info("Webhook deleted, starting polling")

    if settings.SEND_STARTUP_MENU_ON_BOOT:
        async with async_session_maker() as session:
            user_repo = UserRepository(session)
            users = await user_repo.get_all_with_telegram_id()

        startup_recipients: dict[int, int | None] = {
            user.telegram_id: user.id
            for user in users
        }
        for admin_telegram_id in settings.admin_telegram_id_set:
            startup_recipients.setdefault(admin_telegram_id, None)

        for telegram_id, user_id in startup_recipients.items():
            try:
                update_message = (
                    settings.STARTUP_UPDATE_MESSAGE.strip()
                    .strip("\"'")
                    .strip()
                    or "Можно продолжать пользоваться."
                )
                await bot_app.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"Бот обновлен до версии {settings.APP_VERSION} и перезапущен.\n\n"
                        f"{update_message}"
                    ),
                    reply_markup=get_main_menu_keyboard(),
                )
            except Exception:
                logger.warning(
                    "Failed to send startup menu",
                    user_id=user_id,
                    telegram_id=telegram_id,
                    exc_info=True,
                )
    
    try:
        await bot_app.updater.start_polling()
        polling_started = True
        logger.info("Bot started")

        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Bot stopping after cancellation...")
        raise
    except KeyboardInterrupt:
        logger.info("Bot stopping...")
    finally:
        if polling_started and bot_app.updater:
            with suppress(Exception):
                await bot_app.updater.stop()
        if started:
            with suppress(Exception):
                await bot_app.stop()
        if initialized:
            with suppress(Exception):
                await bot_app.shutdown()


async def run_worker() -> None:
    """Run reminder worker."""
    from src.worker import ReminderWorkerService

    logger = structlog.get_logger(__name__)

    # Create bot for sending messages
    from telegram import Bot
    bot = Bot(token=settings.BOT_TOKEN)

    try:
        await bot.initialize()
        
        worker = ReminderWorkerService(
            bot=bot,
            batch_size=100,
            poll_interval=settings.WORKER_INTERVAL,
        )

        logger.info("Reminder worker started")
        await worker.start()
    finally:
        await bot.shutdown()


def run_api() -> None:
    """Run FastAPI API."""
    import uvicorn
    from src.api.app import create_application
    
    logger = structlog.get_logger(__name__)
    
    app = create_application()
    
    logger.info(
        "API starting",
        host=settings.API_HOST,
        port=settings.API_PORT
    )
    
    uvicorn.run(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower()
    )


async def run_api_async() -> None:
    """Run FastAPI API inside the current asyncio loop."""
    import uvicorn
    from src.api.app import create_application

    logger = structlog.get_logger(__name__)
    app = create_application()
    config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)

    logger.info(
        "API starting",
        host=settings.API_HOST,
        port=settings.API_PORT,
    )
    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("API stopping after cancellation...")
        server.should_exit = True
        raise


async def run_all() -> None:
    """Run all services (bot, worker, api)."""
    logger = structlog.get_logger(__name__)

    tasks = [
        asyncio.create_task(run_bot(), name="bot"),
        asyncio.create_task(run_worker(), name="worker"),
        asyncio.create_task(run_api_async(), name="api"),
    ]
    logger.info("All services started")

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc:
                raise exc
        await asyncio.gather(*pending)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Services stopping...")
        raise
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All services stopped")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.main [bot|api|worker|all|init-db] [--dry-run]")
        print("  bot      - Run Telegram bot")
        print("  api      - Run FastAPI API")
        print("  worker   - Run reminder worker")
        print("  all      - Run all services")
        print("  init-db  - Initialize database tables")
        print("  --dry-run - Validate startup without polling, webhooks, or Telegram API")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    dry_run = "--dry-run" in sys.argv[2:]
    
    # Setup logging
    setup_logging(settings.LOG_LEVEL)
    logger = structlog.get_logger(__name__)
    
    if command == "init-db":
        logger.info("Initializing database...")
        asyncio.run(init_db())
        logger.info("Database initialized")
    
    elif command == "bot":
        if dry_run:
            logger.info("Starting bot dry-run...")
            asyncio.run(dry_run_bot())
        else:
            logger.info("Starting bot...")
            asyncio.run(run_bot())
    
    elif command == "api":
        if dry_run:
            from src.api.app import create_application

            app = create_application()
            logger.info("API dry-run completed", title=app.title)
        else:
            logger.info("Starting API...")
            run_api()
    
    elif command == "worker":
        if dry_run:
            logger.info("Starting worker dry-run...")
            asyncio.run(dry_run_worker())
        else:
            logger.info("Starting worker...")
            asyncio.run(run_worker())
    
    elif command == "all":
        if dry_run:
            logger.info("Starting all services dry-run...")
            asyncio.run(dry_run_all())
        else:
            logger.info("Starting all services...")
            asyncio.run(run_all())
    
    else:
        print(f"Unknown command: {command}")
        print("Use 'bot', 'api', 'worker', 'all', or 'init-db'")
        sys.exit(1)


if __name__ == "__main__":
    main()
