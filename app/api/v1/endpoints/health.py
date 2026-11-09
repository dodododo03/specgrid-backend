from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    cache: Annotated[redis.Redis, Depends(get_redis)],
) -> dict[str, str]:
    """Liveness + dependency check. Returns 503 if MariaDB or Redis is unreachable."""
    result = {"status": "ok", "database": "ok", "redis": "ok"}

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        result["database"] = "unavailable"

    try:
        cache.ping()
    except redis.RedisError:
        result["redis"] = "unavailable"

    if "unavailable" in result.values():
        result["status"] = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
