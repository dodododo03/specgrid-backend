from dataclasses import dataclass
from typing import Annotated

import redis
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.core.redis import get_redis
from app.core.security import TokenClaims, TokenError, decode_token
from app.db.session import get_db
from app.models import User
from app.models.enums import UserStatus
from app.services.login_limiter import LoginLimiter
from app.services.token_store import TokenStore

DbSession = Annotated[Session, Depends(get_db)]
RedisClient = Annotated[redis.Redis, Depends(get_redis)]


def get_token_store(client: RedisClient) -> TokenStore:
    return TokenStore(client)


def get_login_limiter(client: RedisClient) -> LoginLimiter:
    return LoginLimiter(client)


TokenStoreDep = Annotated[TokenStore, Depends(get_token_store)]
LoginLimiterDep = Annotated[LoginLimiter, Depends(get_login_limiter)]


def get_client_ip(request: Request) -> str:
    # Behind a reverse proxy, run uvicorn with --proxy-headers --forwarded-allow-ips=<proxy ip>
    # so request.client reflects the real client instead of the proxy.
    return request.client.host if request.client else "unknown"


ClientIp = Annotated[str, Depends(get_client_ip)]

# auto_error=False so we return our own 401 body instead of FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False, description="POST /auth/login 으로 받은 access_token")
_INVALID = "인증이 만료되었거나 올바르지 않습니다."


@dataclass(frozen=True)
class AuthContext:
    user: User
    claims: TokenClaims


def get_auth_context(
    db: DbSession,
    store: TokenStoreDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None:
        raise AuthenticationError("로그인이 필요합니다.")
    return authenticate_access_token(db, store, credentials.credentials)


def authenticate_access_token(db: Session, store: TokenStore, token: str) -> AuthContext:
    """Shared by the HTTP bearer dependency and the chat WebSocket handshake."""
    try:
        claims = decode_token(token, "access")
    except TokenError as exc:
        raise AuthenticationError(_INVALID) from exc
    if not store.is_access_token_active(claims):  # logged out, or "logout everywhere" happened
        raise AuthenticationError(_INVALID)
    user = db.get(User, claims.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError(_INVALID)
    return AuthContext(user=user, claims=claims)


def get_current_user(auth: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return auth.user


CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]
CurrentUser = Annotated[User, Depends(get_current_user)]
