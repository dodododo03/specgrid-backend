from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductDetail,
    ProductSearchParams,
    ProductStatusUpdate,
    ProductSummary,
    ProductUpdate,
    product_page,
)
from app.services import product_service

router = APIRouter(prefix="/products", tags=["products"])

ProductId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.post("", response_model=ProductDetail, status_code=status.HTTP_201_CREATED, summary="상품 등록")
def create_product(data: ProductCreate, user: CurrentUser, db: DbSession):
    return product_service.create_product(db, user, data)


@router.get("", response_model=Page[ProductSummary], summary="상품 검색 (스펙 필터)")
def search_products(params: Annotated[ProductSearchParams, Query()], db: DbSession):
    items, total = product_service.search_products(db, params)
    return product_page(items, total, params.page, params.size)


@router.get("/{product_id}", response_model=ProductDetail, summary="상품 상세 (조회수 +1)")
def get_product(product_id: ProductId, db: DbSession):
    return product_service.get_product(db, product_id)


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
