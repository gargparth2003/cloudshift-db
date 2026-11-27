from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "cloudshift-control-plane"
    deployment_mode: str = "LIVE_LOCAL"
    log_level: str = "INFO"
    control_api_token: str = Field(min_length=16)
    migration_db_password: str = Field(min_length=12)
    source_database_url: str = Field(min_length=1)
    target_database_url: str = Field(min_length=1)
    control_database_url: str = Field(min_length=1)
    app_source_database_url: str = Field(min_length=1)
    app_target_database_url: str = Field(min_length=1)
    commerce_base_url: str = "http://commerce-demo:8001"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
