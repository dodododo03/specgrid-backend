from collections.abc import Iterator
from contextlib import contextmanager

import redis

from app.core.exceptions import ServiceUnavailableError


@contextmanager
def redis_guard() -> Iterator[None]:
    """Fail closed: if Redis is unreachable we cannot prove a token isn't revoked
    or that a login isn't rate-limited, so the request is rejected with 503."""
    try:
        yield
    except redis.RedisError as exc:
        raise ServiceUnavailableError("일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.") from exc
