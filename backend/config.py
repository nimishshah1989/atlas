"""ATLAS configuration — loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://jip_admin:JipDataEngine2026Secure@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine"
    database_url_sync: str = "postgresql+psycopg2://jip_admin:JipDataEngine2026Secure@jip-data-engine.ctay2iewomaj.ap-south-1.rds.amazonaws.com:5432/data_engine"
    atlas_api_port: int = 8010
    atlas_api_host: str = "0.0.0.0"
    cors_origins: str = (
        "https://atlas.jslwealth.in,http://localhost:3000,http://localhost:3001"
    )
    jip_api_base_url: str = "http://172.31.10.182:8000"
    rate_limit_default: str = "60/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
