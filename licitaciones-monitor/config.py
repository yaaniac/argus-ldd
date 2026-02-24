"""
Configuración central del sistema LicitaForense Monitor.
Usa pydantic-settings para tipado y validación de variables de entorno.
"""
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "LicitaForense Monitor"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "dev-secret-key-change-in-production"

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./licitaciones.db"

    # --- Web Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # --- Scheduler ---
    SCAN_INTERVAL_HOURS: int = 4
    SCAN_ON_STARTUP: bool = True

    # --- HTTP Client ---
    API_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    REQUEST_DELAY_SECONDS: float = 2.0

    # --- Email Alerts ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_FROM: str = ""
    ALERT_EMAIL_TO: str = ""
    ALERTS_ENABLED: bool = False

    # --- Paths ---
    DATA_DIR: Path = Path("data")
    PORTALS_REGISTRY_FILE: Path = Path("data/portals_registry.json")

    # --- Scraping ---
    MAX_RESULTS_PER_RUN: int = 500

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.DATABASE_URL


settings = Settings()
