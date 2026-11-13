from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SensorStream"
    database_url: str = "sqlite:///./sensorstream.db"
    # Key for operators: register devices, manage alert rules, read analytics.
    admin_api_key: str = "dev-admin-key"
    max_batch_size: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
