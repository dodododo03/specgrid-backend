from fastapi import APIRouter, Response, status

from app.api.deps import ClientIp, CurrentAuth, DbSession, LoginLimiterDep, TokenStoreDep
from app.schemas.user import LoginRequest, LogoutRequest, RefreshRequest, SignupRequest, TokenResponse, UserMe
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserMe, status_code=status.HTTP_201_CREATED, summary="회원가입")
def signup(data: SignupRequest, db: DbSession):
    return auth_service.signup(db, data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인 (access/refresh 토큰 발급)",
    description="같은 이메일로 5회, 같은 IP에서 30회 실패하면 15분간 429를 반환합니다.",
)
def login(data: LoginRequest, db: DbSession, store: TokenStoreDep, limiter: LoginLimiterDep, ip: ClientIp):
    return auth_service.login(db, data, store, limiter, ip)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 재발급 (refresh 토큰은 1회용)",
    description="이미 사용한 refresh 토큰을 다시 보내면 탈취로 간주해 모든 기기에서 로그아웃됩니다.",
)
def refresh(data: RefreshRequest, db: DbSession, store: TokenStoreDep):
    return auth_service.refresh(db, data.refresh_token, store)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃 (현재 기기)")
def logout(auth: CurrentAuth, store: TokenStoreDep, data: LogoutRequest | None = None) -> Response:
    auth_service.logout(store, auth.claims, data.refresh_token if data else None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, summary="모든 기기에서 로그아웃")
def logout_all(auth: CurrentAuth, store: TokenStoreDep) -> Response:
    auth_service.logout_all(store, auth.user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
