"""
Configuration and settings for the application.
Uses pydantic-settings for environment variable validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Telegram Bot
    BOT_TOKEN: str = Field(..., description="Telegram bot token from @BotFather")
    BOT_USERNAME: Optional[str] = Field(default=None, description="Telegram bot username without @")
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/rememberme",
        description="PostgreSQL connection URL"
    )
    DB_ECHO: bool = Field(default=False, description="Enable SQL query logging")
    
    # Admin API
    ADMIN_TOKEN: str = Field(..., description="Admin API token for authentication")
    ADMIN_TELEGRAM_IDS: str = Field(
        default="",
        description="Comma-separated Telegram user IDs that should be marked as bot admins"
    )
    API_HOST: str = Field(default="0.0.0.0", description="API host")
    API_PORT: int = Field(default=8000, description="API port")
    API_DOCS_ENABLED: bool = Field(default=False, description="Expose FastAPI docs and OpenAPI schema")
    CORS_ORIGINS: str = Field(
        default="",
        description="Comma-separated allowed CORS origins, or * for local development"
    )
    USER_AUTH_MAX_AGE_SECONDS: int = Field(
        default=86400,
        description="Max age for Telegram WebApp initData used by user API"
    )
    
    # Application
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    TIMEZONE_DEFAULT: str = Field(default="Europe/Moscow", description="Default timezone")
    APP_VERSION: str = Field(default="dev", description="Human-readable application version")
    STARTUP_UPDATE_MESSAGE: str = Field(
        default="Можно продолжать пользоваться.",
        description="Short changelog sent with startup menu"
    )
    TESTING_NOTICE_ENABLED: bool = Field(
        default=True,
        description="Show a user-facing notice that the bot is in testing"
    )
    TESTING_NOTICE_TEXT: str = Field(
        default="⚠️ Бот находится в тестировании. Данные могут быть изменены или утеряны.",
        description="Short user-facing testing notice"
    )
    
    # Webhook (optional)
    WEBHOOK_URL: Optional[str] = Field(default=None, description="Webhook URL for production")
    APP_BASE_URL: Optional[str] = Field(default=None, description="Base URL of the application")
    
    # Worker
    WORKER_INTERVAL: int = Field(default=60, description="Worker check interval in seconds")
    SEND_STARTUP_MENU_ON_BOOT: bool = Field(
        default=True,
        description="Send a fresh main menu to known users when bot polling starts"
    )
    DEFAULT_SUBSCRIPTION_PLAN: str = Field(
        default="free",
        description="Default subscription plan for new users"
    )

    @property
    def admin_telegram_id_set(self) -> set[int]:
        """Parse admin Telegram IDs from environment."""
        ids: set[int] = set()
        for raw in self.ADMIN_TELEGRAM_IDS.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                ids.add(int(raw))
            except ValueError:
                continue
        return ids

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return origins


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance (for dependency injection)."""
    return settings
