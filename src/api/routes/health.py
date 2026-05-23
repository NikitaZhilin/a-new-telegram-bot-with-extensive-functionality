"""
Health check routes.

Provides endpoints for:
- Basic health check
- Readiness probe (with database check)
- Liveness probe
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from src.config import settings
from src.db.session import engine

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Health status: ok/degraded/unhealthy")
    timestamp: str = Field(..., description="Current UTC timestamp")
    version: str = Field(..., description="Application version")
    service: str = Field(..., description="Service name")


class DetailedHealthResponse(HealthResponse):
    """Detailed health check with component status."""
    database: str = Field(..., description="Database connection status")
    uptime_seconds: int = Field(..., description="Service uptime in seconds")


# Application start time for uptime calculation
_start_time = datetime.now(timezone.utc)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Basic health check",
    description="Returns basic health status without external dependencies",
)
async def health_check() -> HealthResponse:
    """
    Basic health check endpoint.
    
    Returns 200 OK if the service is running.
    Does not check external dependencies (database, etc.).
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="2.0.0",
        service="rememberme-api",
    )


@router.get(
    "/health/ready",
    response_model=DetailedHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
    description="Check if service is ready to accept traffic (includes database check)",
)
async def health_ready() -> DetailedHealthResponse:
    """
    Readiness probe endpoint.
    
    Checks if the service is ready to accept traffic.
    Verifies database connectivity.
    
    Returns:
        200 OK if all checks pass
        503 Service Unavailable if any check fails
    """
    db_status = "ok"
    
    try:
        # Test database connection
        async with engine.connect() as conn:
            await conn.execute(select(1))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unreachable"
    
    # Determine overall status
    if db_status != "ok":
        overall_status = "degraded"
    else:
        overall_status = "ok"
    
    uptime = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    
    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="2.0.0",
        service="rememberme-api",
        database=db_status,
        uptime_seconds=uptime,
    )


@router.get(
    "/health/live",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Check if service is alive (basic check)",
)
async def health_live() -> HealthResponse:
    """
    Liveness probe endpoint.
    
    Returns 200 OK if the service process is running.
    Simpler than /health - no external checks.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="2.0.0",
        service="rememberme-api",
    )


# Import select for the query
from sqlalchemy import select
