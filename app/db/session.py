from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DB_CONNECT_ARGS, settings

engine = create_engine(
    settings.database_url,
    connect_args=DB_CONNECT_ARGS,
    pool_pre_ping=True,   # drop stale connections (MariaDB wait_timeout)
    pool_recycle=3600,
    echo=settings.debug,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
