"""Simple fixed-window rate limit on a Redis counter."""

import math

import redis

from app.core.exceptions import TooManyRequestsError
from app.services.redis_guard import redis_guard


def hit(client: redis.Redis, key: str, limit: int, window_seconds: int, message: str) -> None:
    """Count one request; raise 429 once `limit` requests happened inside the window."""
    with redis_guard():
        pipe = client.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)  # window starts at the first request
        pipe.ttl(key)
        count, _, ttl = pipe.execute()
    if count > limit:
        retry_after = max(1, ttl)
        raise TooManyRequestsError(
            message.format(minutes=math.ceil(retry_after / 60)), retry_after_seconds=retry_after
        )
