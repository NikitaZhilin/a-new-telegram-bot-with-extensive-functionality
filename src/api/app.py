"""
FastAPI application factory.

Provides REST API for:
- Health checks
- Admin operations (protected by X-Admin-Token)
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health, admin, admin_ui, me, web
from src.config import settings
from src.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("FastAPI application starting")
    yield
    # Shutdown
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
        version="2.0.0",
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

    # Include routers
    app.include_router(web.router, tags=["Web"])
    app.include_router(health.router, tags=["Health"])
    app.include_router(admin_ui.router, tags=["Admin UI"])
    app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    app.include_router(me.router, tags=["User"])

    logger.info("FastAPI application created")

    return app
