from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.product import MyProductParams, ProductSummary, product_page
from app.schemas.user import UserMe
from app.services import product_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe, summary="내 정보")
def read_me(user: CurrentUser):
    return user


@router.get("/me/products", response_model=Page[ProductSummary], summary="내 판매 상품 (숨김·판매완료 포함)")
def my_products(params: Annotated[MyProductParams, Query()], user: CurrentUser, db: DbSession):
    items, total = product_service.list_my_products(db, user, params)
    return product_page(items, total, params.page, params.size)
