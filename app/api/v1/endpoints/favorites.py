from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field

from app.api.deps import Activity, CurrentUser, CurrentViewer, DbSession
from app.models.enums import ActivityType
from app.schemas.common import Page
from app.schemas.product import ProductSummary, product_page
from app.services import favorite_service

router = APIRouter(tags=["favorites"])

ProductId = Annotated[int, Path(ge=1, le=2**63 - 1)]


class FavoriteResult(BaseModel):
    product_id: int
    favorited: bool = Field(description="요청 후 내가 찜한 상태인지")
    favorite_count: int = Field(description="이 상품의 찜 수")


class FavoriteListParams(BaseModel):
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)


@router.put(
    "/products/{product_id}/favorite",
    response_model=FavoriteResult,
    summary="찜하기 ♥",
    description="이미 찜한 상품에 다시 보내도 에러 없이 그대로입니다. 본인 상품(400)·판매완료 상품(409)은 찜할 수 없습니다.",
)
def add_favorite(product_id: ProductId, user: CurrentUser, db: DbSession, viewer: CurrentViewer, activity: Activity):
    added, count = favorite_service.add(db, user, product_id)
    if added:
        activity.record(ActivityType.FAVORITE, viewer, product_id=product_id, detail={"action": "add"})
    return FavoriteResult(product_id=product_id, favorited=True, favorite_count=count)


@router.delete(
    "/products/{product_id}/favorite",
    response_model=FavoriteResult,
    summary="찜 취소 ♡",
    description="찜하지 않은 상품에 보내도 에러 없이 그대로입니다.",
)
def remove_favorite(product_id: ProductId, user: CurrentUser, db: DbSession, viewer: CurrentViewer, activity: Activity):
    removed, count = favorite_service.remove(db, user, product_id)
    if removed:
        activity.record(ActivityType.FAVORITE, viewer, product_id=product_id, detail={"action": "remove"})
    return FavoriteResult(product_id=product_id, favorited=False, favorite_count=count)


@router.get(
    "/users/me/favorites",
    response_model=Page[ProductSummary],
    summary="내 찜 목록 (최근 찜한 순)",
    description="삭제·숨김된 상품은 빠지고, 판매완료 상품은 표시됩니다.",
)
def my_favorites(params: Annotated[FavoriteListParams, Query()], user: CurrentUser, db: DbSession):
    items, total = favorite_service.list_mine(db, user, params.page, params.size)
    return product_page(items, total, params.page, params.size, {p.id for p in items})
