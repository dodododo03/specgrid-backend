from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import Activity, CurrentUser, DbSession, OptionalUser, ViewerDep
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductDetail,
    ProductSearchParams,
    ProductStatusUpdate,
    ProductSummary,
    ProductUpdate,
    product_page,
    with_favorite,
)
from app.services import favorite_service, product_service

router = APIRouter(prefix="/products", tags=["products"])

ProductId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED, summary="상품 등록")
def create_product(data: ProductCreate, user: CurrentUser, db: DbSession):
    return product_service.create_product(db, user, data)


@router.get("", response_model=Page[ProductSummary], summary="상품 검색 (스펙 필터)")
def search_products(
    params: Annotated[ProductSearchParams, Query()], db: DbSession, viewer: ViewerDep, activity: Activity,
    user: OptionalUser,
):
    items, total = product_service.search_products(db, params)
    if params.q and params.page == 1:  # paging through results isn't a new search
        activity.record_search(params.q, viewer, {"category": params.category, "total": total})
    favorited = favorite_service.favorited_ids(db, user, [p.id for p in items]) if user else None
    return product_page(items, total, params.page, params.size, favorited)


@router.get(
    "/{product_id}",
    response_model=ProductDetail,
    summary="상품 상세 (조회수 +1)",
    description="같은 사람이 30분 안에 다시 보거나 판매자 본인이 보면 조회수가 오르지 않습니다.",
)
def get_product(product_id: ProductId, db: DbSession, viewer: ViewerDep, activity: Activity, user: OptionalUser):
    product = product_service.get_public_product(db, product_id)
    if activity.record_view(product, viewer):
        product = product_service.increment_view_count(db, product_id)
    favorited = favorite_service.favorited_ids(db, user, [product.id]) if user else None
    return with_favorite(ProductDetail.model_validate(product), favorited)


@router.patch("/{product_id}", response_model=ProductDetail, summary="상품 수정 (보낸 항목만 변경)")
def update_product(product_id: ProductId, data: ProductUpdate, user: CurrentUser, db: DbSession):
    return product_service.update_product(db, product_id, user, data)


@router.patch("/{product_id}/status", response_model=ProductDetail, summary="판매 상태 변경")
def change_status(product_id: ProductId, data: ProductStatusUpdate, user: CurrentUser, db: DbSession):
    return product_service.change_status(db, product_id, user, data)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT, summary="상품 삭제")
def delete_product(product_id: ProductId, user: CurrentUser, db: DbSession) -> Response:
    product_service.delete_product(db, product_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
