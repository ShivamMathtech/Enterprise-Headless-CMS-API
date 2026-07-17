from functools import lru_cache
from typing import Annotated
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


def _csv_or_list(value):
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if value.startswith('['):
            import json
            return json.loads(value)
        return [part.strip() for part in value.split(',') if part.strip()]
    return value

StringList = Annotated[list[str], NoDecode, BeforeValidator(_csv_or_list)]


class Settings(BaseSettings):
    app_name: str = 'Enterprise Headless CMS API'
    environment: str = 'development'
    debug: bool = False
    api_v1_prefix: str = '/api/v1'
    secret_key: str = 'dev-secret-change-me-at-least-32-characters'
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    database_url: str = 'sqlite:///./cms.db'
    redis_url: str = ''
    cors_origins: StringList = ['http://localhost:3000', 'http://localhost:5173']
    trusted_hosts: StringList = ['localhost', '127.0.0.1', 'testserver']
    upload_dir: str = './uploads'
    public_media_base_url: str = 'http://127.0.0.1:8000/media'
    default_locale: str = 'en-US'
    default_timezone: str = 'UTC'
    max_upload_bytes: int = 25 * 1024 * 1024
    webhook_timeout_seconds: int = 10
    model_config = SettingsConfigDict(
        env_file='.env', env_file_encoding='utf-8', case_sensitive=False, extra='ignore'
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
