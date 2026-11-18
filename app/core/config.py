import hashlib
import hmac
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "SpecGrid API"
    app_env: str = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = []

    db_host: str = "127.0.0.1"
    db_port: int = 3307
    db_name: str = "specgrid"
    # Runtime account: DML only (SELECT/INSERT/UPDATE/DELETE).
    db_user: str = "specgrid_app"
    db_password: str = ""
    # Migration account: DDL privileges, used only by Alembic.
    db_migration_user: str = "specgrid_migrator"
    db_migration_password: str = ""

    redis_url: str = "redis://localhost:6379/0"

    # JWT — no default secret: the app refuses to start without a real one.
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Media storage. Keys are stored in the DB; URLs are built from media_base_url,
    # so moving to a CDN/S3 later only changes these settings + the storage backend.
    media_root: str = "media"
    media_base_url: str = "http://localhost:8000/media"
    max_images_per_product: int = 10
    max_image_upload_mb: int = 10

    # Kakao Maps JavaScript key. It is public by design (the browser loads the SDK with it); Kakao
    # only accepts it from the site domains registered in Kakao Developers. Empty = maps disabled.
    kakao_js_key: str = ""

    # Activity logs never store a raw IP, only HMAC-SHA256(key, ip): "same IP?" can still be checked
    # for abuse investigation, but a leaked log table reveals no addresses. Empty = derived from
    # JWT_SECRET_KEY (set it explicitly in production so rotating the JWT key keeps hashes stable).
    log_hash_key: str = ""

    # Brute-force protection (Redis counters)
    login_max_attempts_per_email: int = 5
    login_max_attempts_per_ip: int = 30
    login_lock_minutes: int = 15
    # Signup "중복 확인" reveals whether an email is registered, so cap it per IP to stop harvesting.
    availability_checks_per_ip: int = 60
    availability_window_minutes: int = 10

    def _url(self, username: str, password: str) -> URL:
        # URL.create escapes special characters in the password safely.
        return URL.create(
            drivername="mysql+pymysql",
            username=username,
            password=password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )

    @property
    def database_url(self) -> URL:
        return self._url(self.db_user, self.db_password)

    @property
    def migration_database_url(self) -> URL:
        return self._url(self.db_migration_user, self.db_migration_password)

    @property
    def log_hash_secret(self) -> bytes:
        if self.log_hash_key:
            return self.log_hash_key.encode()
        return hmac.new(self.jwt_secret_key.encode(), b"specgrid-activity-log-ip", hashlib.sha256).digest()


# Applied on every new connection: store all timestamps in UTC and reject
# invalid/truncated data instead of silently coercing it.
DB_CONNECT_ARGS = {
    "init_command": (
        "SET time_zone = '+00:00', "
        "sql_mode = 'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,"
        "NO_ENGINE_SUBSTITUTION,NO_ZERO_DATE,NO_ZERO_IN_DATE'"
    )
}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
