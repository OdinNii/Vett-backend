from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Vett API"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Database
    database_url: str = "postgresql+asyncpg://vett:vett@localhost:5432/vett"

    # Adzuna
    adzuna_app_id: str = ""
    adzuna_api_key: str = ""
    adzuna_base_url: str = "https://api.adzuna.com/v1/api"

    # Job scanner
    scan_interval_hours: int = 6
    max_jobs_per_scan: int = 50
    min_fit_score: int = 60  # hide jobs below this threshold

    # CV
    max_cv_size_mb: int = 10

    # SendGrid email
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "hello@vett.app"
    sendgrid_from_name: str = "Vett"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
