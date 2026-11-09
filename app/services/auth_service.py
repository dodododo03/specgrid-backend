from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    TokenClaims,
    TokenError,
    create_token,
    decode_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models import User
from app.models.enums import UserStatus
from app.schemas.user import LoginRequest, SignupRequest, TokenResponse
from app.services.login_limiter import LoginLimiter
from app.services.token_store import TokenStore

INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다."
RELOGIN_REQUIRED = "다시 로그인해 주세요."


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def signup(db: Session, data: SignupRequest) -> User:
    email = _normalize_email(data.email)
    existing = db.execute(
        select(User.email, User.nickname).where(or_(User.email == email, User.nickname == data.nickname))
    ).first()
    if existing:
        field = "이메일" if existing.email == email else "닉네임"
        raise ConflictError(f"이미 사용 중인 {field}입니다.")

    user = User(email=email, password_hash=hash_password(data.password), nickname=data.nickname)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # Two signups with the same email/nickname racing past the check above.
        db.rollback()
        raise ConflictError("이미 사용 중인 이메일 또는 닉네임입니다.") from exc
    db.refresh(user)
    return user


def _issue_tokens(store: TokenStore, user_id: int) -> TokenResponse:
    generation = store.current_generation(user_id)
    access_token, _ = create_token(user_id, "access", generation)
    refresh_token, refresh_claims = create_token(user_id, "refresh", generation)
    store.register_refresh(refresh_claims)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


def login(db: Session, data: LoginRequest, store: TokenStore, limiter: LoginLimiter, client_ip: str) -> TokenResponse:
    email = _normalize_email(data.email)
    limiter.ensure_allowed(email, client_ip)  # 429 before we even look at the password

    user = db.scalar(select(User).where(User.email == email))
    # verify_password runs a full hash check even when user is None (timing-safe).
    if not verify_password(data.password, user.password_hash if user else None):
        limiter.record_failure(email, client_ip)
        raise AuthenticationError(INVALID_CREDENTIALS)
    assert user is not None
    if user.status != UserStatus.ACTIVE:
        raise AuthenticationError("이용이 제한된 계정입니다.")

    limiter.reset(email)
    if password_needs_rehash(user.password_hash):  # hashing params upgraded since signup
        user.password_hash = hash_password(data.password)
    user.last_login_at = func.now()  # DB clock, UTC session time zone
    db.commit()
    return _issue_tokens(store, user.id)


def refresh(db: Session, refresh_token: str, store: TokenStore) -> TokenResponse:
    """Rotate: the presented refresh token is used up and a new pair is issued.

    A validly-signed refresh token that was already used means it was copied
    (stolen) or replayed — every session of that user is revoked.
    """
    try:
        claims = decode_token(refresh_token, "refresh")
    except TokenError as exc:
        raise AuthenticationError(RELOGIN_REQUIRED) from exc

    if not store.consume_refresh(claims):
        store.bump_generation(claims.user_id)
        raise AuthenticationError("보안을 위해 모든 기기에서 로그아웃되었습니다. 다시 로그인해 주세요.")
    if not store.is_generation_current(claims):
        raise AuthenticationError(RELOGIN_REQUIRED)

    user = db.get(User, claims.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError(RELOGIN_REQUIRED)
    return _issue_tokens(store, user.id)


def logout(store: TokenStore, access_claims: TokenClaims, refresh_token: str | None) -> None:
    store.revoke_access(access_claims)
    if refresh_token:
        try:
            refresh_claims = decode_token(refresh_token, "refresh")
        except TokenError:
            return  # logout must still succeed; an invalid refresh token is useless anyway
        if refresh_claims.user_id == access_claims.user_id:  # can't revoke someone else's token
            store.discard_refresh(refresh_claims)


def logout_all(store: TokenStore, user_id: int) -> None:
    store.bump_generation(user_id)
