"""
FastAPI application factory.

Provides REST API for:
- Health checks
- Admin operations (protected by X-Admin-Token)
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health, admin, admin_ui, me, web
from src.config import settings
from src.db.session import engine
from src.services.service_heartbeat import ServiceHeartbeatWriter

logger = logging.getLogger(__name__)

_TOKEN_IN_QUERY = re.compile(r"(?i)([?&](?:token|key)=)[^&\s\"]+")
NO_STORE_PREFIXES = ("/web", "/miniapp", "/me", "/admin")


def redact_query_tokens(value: str) -> str:
    """Hide ?token=... values (30-day web login keys) in log lines."""
    return _TOKEN_IN_QUERY.sub(r"\1***", value)


class RedactTokenFilter(logging.Filter):
    """Strip login keys from uvicorn access log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(
                redact_query_tokens(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        elif isinstance(record.msg, str):
            record.msg = redact_query_tokens(record.msg)
        return True


def install_access_log_redaction() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, RedactTokenFilter) for item in access_logger.filters):
        access_logger.addFilter(RedactTokenFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("FastAPI application starting")
    install_access_log_redaction()
    heartbeat = ServiceHeartbeatWriter(
        "api",
        metadata_factory=lambda: {
            "api_host": settings.API_HOST,
            "api_port": settings.API_PORT,
            "docs_enabled": settings.API_DOCS_ENABLED,
        },
    )
    heartbeat_task = asyncio.create_task(heartbeat.run(), name="heartbeat-api")
    try:
        yield
    finally:
        # Shutdown
        heartbeat.stop()
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        logger.info("FastAPI application shutting down")
        await engine.dispose()


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    docs_url = "/docs" if settings.API_DOCS_ENABLED else None
    redoc_url = "/redoc" if settings.API_DOCS_ENABLED else None
    openapi_url = "/openapi.json" if settings.API_DOCS_ENABLED else None

    app = FastAPI(
        title="RememberMe API",
        description="Web, user, and admin API for RememberMe bot",
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )

    cors_origins = settings.cors_origin_list
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_access_log_redaction()

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        path = request.url.path
        if path == "/" or path.startswith(NO_STORE_PREFIXES):
            response.headers["Cache-Control"] = "no-store"
        return response

    # Include routers
    app.include_router(web.router, tags=["Web"])
    app.include_router(health.router, tags=["Health"])
    app.include_router(admin_ui.router, tags=["Admin UI"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(me.router, tags=["User"])

    logger.info("FastAPI application created")

    return app
