from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://athar:athar_pass@localhost:5432/athar_db"
    pool_size: int = 10
    max_overflow: int = 5
    pool_pre_ping: bool = True
    pool_recycle: int = 1800
    pool_timeout: int = 30


class QdrantSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    prefer_grpc: bool = True
    api_key: str = ""


class RedisSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str = ""
    otp_ttl_seconds: int = 300


class MinIOSettings(BaseSettings):
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "athar-uploads"
    secure: bool = False
    public_url: str = ""


class AuthSettings(BaseSettings):
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_algorithm: str = "EdDSA"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30


class TwilioSettings(BaseSettings):
    account_sid: str | None = None
    auth_token: str | None = None
    verify_service_sid: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")

    app_name: str = "ATHAR OS (أثر)"
    app_version: str = "0.3.0"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    database: DatabaseSettings = DatabaseSettings()
    qdrant: QdrantSettings = QdrantSettings()
    redis: RedisSettings = RedisSettings()
    minio: MinIOSettings = MinIOSettings()
    auth: AuthSettings = AuthSettings()
    twilio: TwilioSettings = TwilioSettings()


settings = Settings()
