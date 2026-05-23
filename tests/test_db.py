"""Database tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_db_session(db_session: AsyncSession):
    """Test database session fixture."""
    assert db_session is not None
