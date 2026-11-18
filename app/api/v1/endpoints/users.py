from typing import Annotated

from fastapi import APIRouter, File, Query, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.api.deps import ClientIp, CurrentUser, DbSession, LoginLimiterDep, TokenStoreDep
from app.api.v1.endpoints.product_images import StorageDep, read_limited
from app.schemas.common import Page
from app.schemas.product import MyProductParams, ProductSummary, product_page
from app.schemas.user import UserMe, WithdrawRequest
from app.services import account_service, product_service, profile_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe, summary="내 정보")
def read_me(user: CurrentUser):
    return user


@router.put(
    "/me/profile-image",
    response_model=UserMe,
    summary="프로필 사진 등록/변경",
    description=(
        "JPG/PNG/WebP, 10MB 이하. 가운데를 기준으로 정사각형(최대 400×400)으로 잘라 WebP로 저장하며 "
        "위치정보(EXIF)는 제거됩니다. 기존 사진은 새 사진으로 교체됩니다."
    ),
)
async def upload_profile_image(
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="프로필 이미지 파일")],
):
    data = await read_limited(file)
    return await run_in_threadpool(profile_service.set_profile_image, db, storage, user, data)


@router.delete("/me/profile-image", response_model=UserMe, summary="프로필 사진 삭제 (기본 아이콘으로)")
def delete_profile_image(user: CurrentUser, db: DbSession, storage: StorageDep):
    return profile_service.remove_profile_image(db, storage, user)


@router.get("/me/products", response_model=Page[ProductSummary], summary="내 판매 상품 (숨김·판매완료 포함)")
def my_products(params: Annotated[MyProductParams, Query()], user: CurrentUser, db: DbSession):
    items, total = product_service.list_my_products(db, user, params)
    return product_page(items, total, params.page, params.size)


@router.post(
    "/me/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="회원 탈퇴",
    description=(
        "현재 비밀번호로 본인 확인 후 탈퇴합니다. 이메일·비밀번호·프로필 사진은 즉시 삭제되고 닉네임은 "
        "'탈퇴회원#번호'로 바뀌며, 내 판매 상품과 사진·찜은 삭제되고 모든 기기에서 로그아웃됩니다. "
        "채팅과 완료된 거래 기록은 상대방의 기록이라 남습니다. 예약중(accepted)인 거래가 있으면 409. "
        "비밀번호가 틀리면 400(wrong_password), 로그인과 같은 횟수 제한(429)이 적용됩니다."
    ),
)
def withdraw(
    data: WithdrawRequest,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    store: TokenStoreDep,
    limiter: LoginLimiterDep,
    ip: ClientIp,
) -> Response:
    account_service.withdraw(db, storage, store, limiter, user, data.password, ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
