import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.models.enums import UserRole
from app.schemas.common import MediaUrl, ORMModel, UTCDateTime

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


def _required_consent(message: str):
    def check(value: bool) -> bool:
        if value is not True:
            raise ValueError(message)
        return value
    return AfterValidator(check)


class SignupRequest(BaseModel):
    email: EmailStr
    password: Password
    nickname: Nickname
    # All three are required (필수 동의). Under-14s need a guardian's consent under 개인정보 보호법 §22-2,
    # which this service doesn't collect, so they can't sign up.
    agree_terms: Annotated[bool, _required_consent("이용약관에 동의해야 가입할 수 있습니다.")] = Field(
        description="이용약관 동의 (필수, true)")
    agree_privacy: Annotated[bool, _required_consent("개인정보 수집·이용에 동의해야 가입할 수 있습니다.")] = Field(
        description="개인정보 수집·이용 동의 (필수, true)")
    over_14: Annotated[bool, _required_consent("만 14세 이상만 가입할 수 있습니다.")] = Field(
        description="만 14세 이상 확인 (필수, true)")


class WithdrawRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128, description="본인 확인용 현재 비밀번호")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=2048)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=2048, description="함께 폐기할 refresh 토큰 (권장)")


class AvailabilityResponse(BaseModel):
    field: Literal["email", "nickname"]
    available: bool
    message: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime in seconds


class UserPublic(ORMModel):
    """Safe to show to other users (e.g. seller info on a product)."""

    id: int
    nickname: str
    profile_image_url: MediaUrl | None = Field(validation_alias="profile_image_key")


class UserMe(UserPublic):
    email: str
    role: UserRole
    created_at: UTCDateTime
    last_login_at: UTCDateTime | None
