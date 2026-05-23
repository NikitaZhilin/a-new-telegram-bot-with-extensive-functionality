"""
API authentication.

All admin endpoints require X-Admin-Token header.
"""

import logging
from fastapi import Header, HTTPException, Depends, status

from src.config import settings

logger = logging.getLogger(__name__)


async def verify_admin_token(
    x_admin_token: str = Header(
        ...,
        alias="X-Admin-Token",
        description="Admin authentication token"
    )
) -> bool:
    """
    Verify admin token from X-Admin-Token header.
    
    Args:
        x_admin_token: Token from request header
        
    Raises:
        HTTPException: 401 if token is missing or invalid
        
    Returns:
        True if token is valid
    """
    if not x_admin_token:
        logger.warning("Missing X-Admin-Token header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Token header",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )
    
    if not settings.ADMIN_TOKEN:
        logger.error("ADMIN_TOKEN not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error",
        )
    
    # Constant-time comparison to prevent timing attacks
    if not _safe_compare(x_admin_token, settings.ADMIN_TOKEN):
        logger.warning("Invalid admin token attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )
    
    return True


def _safe_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.
    
    Args:
        a: First string
        b: Second string
        
    Returns:
        True if strings are equal
    """
    if len(a) != len(b):
        return False
    
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    
    return result == 0


# Dependency for routes
require_admin = Depends(verify_admin_token)
