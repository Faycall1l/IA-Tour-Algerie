from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://athar:athar_pass@localhost:5432/athar_db"
    pool_size: int = 20
    max_overflow: int = 10
    pool_pre_ping: bool = True
    pool_recycle: int = 1800


class QdrantSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    prefer_grpc: bool = False


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    otp_ttl_seconds: int = 300


class MinIOSettings(BaseSettings):
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "athar-uploads"
    secure: bool = False


class AuthSettings(BaseSettings):
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30


class TwilioSettings(BaseSettings):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    verify_service_sid: Optional[str] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")

    app_name: str = "ATHAR OS (أثر)"
    app_version: str = "0.2.0"
    debug: bool = False
    allowed_origins: list[str] = ["*"]

    database: DatabaseSettings = DatabaseSettings()
    qdrant: QdrantSettings = QdrantSettings()
    redis: RedisSettings = RedisSettings()
    minio: MinIOSettings = MinIOSettings()
    auth: AuthSettings = AuthSettings()
    twilio: TwilioSettings = TwilioSettings()


settings = Settings()
