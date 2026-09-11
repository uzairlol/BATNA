"""Tests for application settings and configuration loading."""

from batna.config import Settings, settings


def test_default_settings_loaded() -> None:
    """Ensure default configuration loads cleanly."""
    assert settings.environment in ("development", "test", "production")
    assert settings.app_port == 8000
    assert "batna" in settings.database_url


def test_custom_settings_instantiation(test_settings: Settings) -> None:
    """Ensure isolated settings can be instantiated with custom values."""
    assert test_settings.environment == "test"
    assert test_settings.log_level == "DEBUG"
    assert "batna_test" in test_settings.database_url
