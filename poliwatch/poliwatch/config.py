from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./poliwatch.db"

    # Congress.gov API
    congress_api_key: str = ""

    # Optional APIs
    propublica_api_key: str = ""
    opensecrets_api_key: str = ""

    # Email alerts
    alert_email_from: str = ""
    alert_email_to: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # Webhook alerts
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    # Thresholds
    suspicion_alert_threshold: float = 60.0
    data_refresh_interval_hours: int = 6

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    dashboard_port: int = 8501
    log_level: str = "INFO"


settings = Settings()
