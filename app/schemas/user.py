import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.models.enums import UserRole
from app.schemas.common import ORMModel, UTCDateTime

_NICKNAME_RE = re.compile(r"^[가-힣A-Za-z0-9_]+$")


def _check_password(value: str) -> str:
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다.")
    return value


def _check_nickname(value: str) -> str:
    if not _NICKNAME_RE.fullmatch(value):
        raise ValueError("닉네임은 한글, 영문, 숫자, _만 사용할 수 있습니다.")
    return value


Password = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_check_password)]
Nickname = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30), AfterValidator(_check_nickname)
]


class SignupRequest(BaseModel):
    email: EmailStr
    password: Password
    nickname: Nickname


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=2048, description="함께 폐기할 refresh 토큰 (권장)")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime in seconds


class UserPublic(ORMModel):
    """Safe to show to other users (e.g. seller info on a product)."""

    id: int
    nickname: str
    profile_image_url: str | None


class UserMe(UserPublic):
    email: str
    role: UserRole
    created_at: UTCDateTime
    last_login_at: UTCDateTime | None
