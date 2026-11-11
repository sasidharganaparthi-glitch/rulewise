"""Application configuration and environment settings management for RuleWise AI.

Loads settings from environment variables and .env file with safe defaults.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine project root based on this file's location (backend/core/config.py -> root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """RuleWise AI application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH if ENV_FILE_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini API configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Google OAuth 2.0 configuration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # Administrator initial configuration
    ADMIN_EMAIL: str = "sasiganaparthi@gmail.com"
    ADMIN_INITIAL_PASSWORD: Optional[str] = None

    # Application server configuration
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEBUG: bool = True

    # NLP and LLM configuration
    MAX_INPUT_LENGTH: int = 20000
    LLM_TIMEOUT_SECONDS: float = 12.0


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Retrieve or initialize singleton application configuration."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset configuration singleton (primarily for testing with custom envs)."""
    global _settings
    _settings = None
