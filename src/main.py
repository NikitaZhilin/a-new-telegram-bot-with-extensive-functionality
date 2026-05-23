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
from contextlib import suppress
import structlog
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


async def init_db() -> None:
    """Initialize database tables (for development only)."""
    # Import models before create_all so SQLAlchemy registers every table.
    import src.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS list_id INTEGER"))
        await conn.execute(text("ALTER TABLE reminders ADD COLUMN IF NOT EXISTS medication_id INTEGER"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_list_id ON reminders (list_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_medication_id ON reminders (medication_id)"))
        await conn.execute(text("ALTER TABLE medication_intakes ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'TAKEN'"))
        await conn.execute(text("ALTER TABLE medications ADD COLUMN IF NOT EXISTS importance VARCHAR(20) NOT NULL DEFAULT 'normal'"))
        await conn.execute(text("ALTER TABLE list_share_tokens ADD COLUMN IF NOT EXISTS token_type VARCHAR(20) NOT NULL DEFAULT 'copy'"))
        await conn.execute(text("ALTER TABLE list_share_tokens ADD COLUMN IF NOT EXISTS access_role VARCHAR(20) NOT NULL DEFAULT 'editor'"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT false"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_source VARCHAR(100)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_admin ON users (is_admin)"))


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
