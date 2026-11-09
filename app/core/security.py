"""Password hashing (Argon2id) and JWT access/refresh tokens.

Pure crypto/encoding only — revocation state lives in Redis (app/services/token_store.py).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

TokenType = Literal["access", "refresh"]

_hasher = PasswordHasher()  # Argon2id with library-recommended parameters
# Used when the email doesn't exist, so login takes the same time either way
# (prevents discovering registered emails by response timing).
_DUMMY_HASH = _hasher.hash("specgrid-timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


class TokenError(Exception):
    """Token is missing, malformed, expired, or of the wrong type."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    type: TokenType
    jti: str
    expires_at: datetime
    generation: int  # must match the user's current generation in Redis ("logout everywhere")

    def seconds_left(self) -> int:
        return max(1, int((self.expires_at - datetime.now(UTC)).total_seconds()) + 1)


def create_token(user_id: int, token_type: TokenType, generation: int = 0) -> tuple[str, TokenClaims]:
    now = datetime.now(UTC)
    lifetime = (
        timedelta(minutes=settings.access_token_expire_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_expire_days)
    )
    claims = TokenClaims(user_id, token_type, uuid.uuid4().hex, now + lifetime, generation)
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": token_type,
            "iat": now,
            "exp": claims.expires_at,
            "jti": claims.jti,
            "gen": generation,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, claims


def decode_token(token: str, expected_type: TokenType) -> TokenClaims:
    """Verify signature/expiry/type. Raises TokenError. Does NOT check revocation."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],  # pinned: blocks alg=none / alg-confusion
            options={"require": ["sub", "type", "exp", "iat", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise TokenError("wrong token type")
    try:
        return TokenClaims(
            user_id=int(payload["sub"]),
            type=expected_type,
            jti=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            generation=int(payload.get("gen", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise TokenError("invalid claims") from exc
