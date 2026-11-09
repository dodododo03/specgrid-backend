from functools import lru_cache

import redis

from app.core.config import settings


@lru_cache
def get_redis_client() -> redis.Redis:
    """Shared Redis client (connection pool). Used for caching and distributed locks."""
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def get_redis() -> redis.Redis:
    """FastAPI dependency."""
    return get_redis_client()
