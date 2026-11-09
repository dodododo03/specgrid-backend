"""Brute-force protection for /auth/login using Redis counters with a fixed window.

- per email: stops password guessing against one account
- per IP:    stops one client spraying many accounts
Emails are hashed in key names so Redis never holds raw addresses.
"""

import hashlib
import math

import redis

from app.core.config import settings
from app.core.exceptions import TooManyRequestsError
from app.services.redis_guard import redis_guard

_PREFIX = "specgrid:login_fail"


def _email_key(email: str) -> str:
    return f"{_PREFIX}:email:{hashlib.sha256(email.encode()).hexdigest()}"


def _ip_key(ip: str) -> str:
    return f"{_PREFIX}:ip:{ip}"


class LoginLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client
        self.window_seconds = settings.login_lock_minutes * 60

    def ensure_allowed(self, email: str, ip: str) -> None:
        checks = [
            (_email_key(email), settings.login_max_attempts_per_email),
            (_ip_key(ip), settings.login_max_attempts_per_ip),
        ]
        with redis_guard():
            counts = self.r.mget([key for key, _ in checks])
            for (key, limit), count in zip(checks, counts, strict=True):
                if count is not None and int(count) >= limit:
                    retry_after = max(1, self.r.ttl(key))
                    raise TooManyRequestsError(
                        f"로그인 시도가 너무 많습니다. {math.ceil(retry_after / 60)}분 후 다시 시도해 주세요.",
                        retry_after_seconds=retry_after,
                    )

    def record_failure(self, email: str, ip: str) -> None:
        with redis_guard():
            pipe = self.r.pipeline(transaction=True)
            for key in (_email_key(email), _ip_key(ip)):
                pipe.incr(key)
                pipe.expire(key, self.window_seconds, nx=True)  # window starts at the first failure
            pipe.execute()

    def reset(self, email: str) -> None:
        """Successful login clears the per-email counter (the per-IP one keeps counting down)."""
        with redis_guard():
            self.r.delete(_email_key(email))
