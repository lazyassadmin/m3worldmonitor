"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # External APIs
    congress_api_key: str = Field(default="", description="api.congress.gov API key")
    propublica_api_key: str = Field(default="")
    opensecrets_api_key: str = Field(default="")

    # Database
    database_url: str = Field(default=f"sqlite:///{DATA_DIR / 'poliwatch.db'}")

    # Alerts
    alert_email_from: str = Field(default="")
    alert_email_to: str = Field(default="")
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    discord_webhook_url: str = Field(default="")
    slack_webhook_url: str = Field(default="")

    # Thresholds
    suspicion_alert_threshold: float = Field(default=60.0, ge=0.0, le=100.0)
    data_refresh_interval_hours: int = Field(default=6, ge=1)

    # Servers
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    dashboard_port: int = Field(default=8501)

    # Logging
    log_level: str = Field(default="INFO")

    # ---- Derived flags ----
    @property
    def has_congress_api(self) -> bool:
        return bool(self.congress_api_key)

    @property
    def has_propublica_api(self) -> bool:
        return bool(self.propublica_api_key)

    @property
    def has_opensecrets_api(self) -> bool:
        return bool(self.opensecrets_api_key)

    @property
    def has_smtp(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.alert_email_to)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
