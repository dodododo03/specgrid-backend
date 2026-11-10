"""Distributed lock per product (Redis), so trade actions on one product run one at a time
across every API process / server.

Why both this and SELECT ... FOR UPDATE? The DB row lock alone is correct, but under a burst
(e.g. 50 people pressing "구매 요청" on a hot deal) every request would grab a DB connection and
queue inside MariaDB. The Redis lock queues them before they touch the DB, keeps the wait short
and bounded (LOCK_WAIT_SECONDS), and fails fast with 409 instead of piling up connections.
The DB lock + unique indexes stay as the safety net in case the Redis lock expires mid-request.

Key: specgrid:lock:product:{product_id}  (value = random token; released only by its owner, via Lua)
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import redis
from redis.exceptions import LockError

from app.core.exceptions import ConflictError
from app.services.redis_guard import redis_guard

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 10   # auto-release if the holder crashes
LOCK_WAIT_SECONDS = 3   # how long a request waits for its turn before giving up
LOCK_RETRY_SECONDS = 0.02  # polling interval while waiting (redis-py default 0.1s is sluggish)

BUSY = "다른 거래 요청을 처리하는 중입니다. 잠시 후 다시 시도해 주세요."


def lock_key(product_id: int) -> str:
    return f"specgrid:lock:product:{product_id}"


class ProductLock:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client

    @contextmanager
    def hold(self, product_id: int) -> Iterator[None]:
        lock = self.r.lock(
            lock_key(product_id), timeout=LOCK_TTL_SECONDS, blocking_timeout=LOCK_WAIT_SECONDS,
            sleep=LOCK_RETRY_SECONDS,
        )
        with redis_guard():  # Redis down -> 503 (fail closed: no unguarded trades)
            acquired = lock.acquire()
        if not acquired:
            raise ConflictError(BUSY)
        try:
            yield
        finally:
            try:
                lock.release()
            except LockError:
                # TTL ran out before we finished; the DB lock still kept the data consistent.
                logger.warning("product lock %s expired before release", product_id)
            except redis.RedisError:
                logger.warning("could not release product lock %s (expires in %ss)",
                               product_id, LOCK_TTL_SECONDS, exc_info=True)
