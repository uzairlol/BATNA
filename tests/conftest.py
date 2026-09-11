"""Test suite configuration and shared fixtures for BATNA."""

import pytest

from batna.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Provide isolated test settings."""
    return Settings(
        environment="test",
        log_level="DEBUG",
        database_url="postgresql+asyncpg://test:test@localhost:5432/batna_test",
        redis_url="redis://localhost:6379/1",
    )
