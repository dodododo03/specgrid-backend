"""Server-side JWT state in Redis.

Keys (all expire on their own, except the generation counter):
  specgrid:auth:refresh:{jti}  -> user_id   allow-list of unused refresh tokens (one-time use)
  specgrid:auth:revoked:{jti}  -> 1         access tokens revoked by logout, until they expire
  specgrid:auth:gen:{user_id}  -> int       bumped by "logout everywhere"; older tokens are rejected
"""

import redis

from app.core.security import TokenClaims
from app.services.redis_guard import redis_guard

_PREFIX = "specgrid:auth"


def _refresh_key(jti: str) -> str:
    return f"{_PREFIX}:refresh:{jti}"


def _revoked_key(jti: str) -> str:
    return f"{_PREFIX}:revoked:{jti}"


def _gen_key(user_id: int) -> str:
    return f"{_PREFIX}:gen:{user_id}"


class TokenStore:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client

    def current_generation(self, user_id: int) -> int:
        with redis_guard():
            return int(self.r.get(_gen_key(user_id)) or 0)

    def bump_generation(self, user_id: int) -> None:
        """Invalidate every token issued so far for this user (all devices)."""
        with redis_guard():
            self.r.incr(_gen_key(user_id))

    def register_refresh(self, claims: TokenClaims) -> None:
        with redis_guard():
            self.r.set(_refresh_key(claims.jti), claims.user_id, ex=claims.seconds_left())

    def consume_refresh(self, claims: TokenClaims) -> bool:
        """Atomically use up a refresh token. False = already used, revoked, or unknown."""
        with redis_guard():
            owner = self.r.getdel(_refresh_key(claims.jti))
        return owner is not None and int(owner) == claims.user_id

    def discard_refresh(self, claims: TokenClaims) -> None:
        with redis_guard():
            self.r.delete(_refresh_key(claims.jti))

    def revoke_access(self, claims: TokenClaims) -> None:
        with redis_guard():
            self.r.set(_revoked_key(claims.jti), 1, ex=claims.seconds_left())

    def is_access_token_active(self, claims: TokenClaims) -> bool:
        with redis_guard():
            revoked, generation = self.r.mget(_revoked_key(claims.jti), _gen_key(claims.user_id))
        return revoked is None and int(generation or 0) == claims.generation

    def is_generation_current(self, claims: TokenClaims) -> bool:
        return self.current_generation(claims.user_id) == claims.generation
