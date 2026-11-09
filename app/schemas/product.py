from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator, model_validator

from app.core.storage import get_storage
from app.models.enums import ProductCategory, ProductCondition, ProductStatus
from app.schemas.common import ORMModel, Page, UTCDateTime
from app.schemas.user import UserPublic

def Str(max_len: int, min_len: int = 1) -> Any:  # noqa: N802 — reads like a type in annotations
    """Trimmed string with length limits."""
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=min_len, max_length=max_len)]


def _media_url(key: str) -> str:
    return get_storage().url(key)


# DB holds storage keys; responses expose public URLs built from the current storage settings.
MediaUrl = Annotated[str, AfterValidator(_media_url)]

MAX_PRICE = 1_000_000_000  # 10억원 — sanity cap, well within INT range


class ProductSpecIn(BaseModel):
    manufacturer: Str(100) | None = None
    model_name: Str(150) | None = None
    cpu_model: Str(120) | None = None
    cpu_cores: int | None = Field(default=None, ge=1, le=1024)
    ram_gb: int | None = Field(default=None, ge=1, le=65536)
    gpu_model: Str(120) | None = None
    vram_gb: int | None = Field(default=None, ge=1, le=1024)
    storage_gb: int | None = Field(default=None, ge=1, le=10_000_000)
    storage_type: Str(20) | None = None
    extra_specs: dict[str, Any] | None = None

    @field_validator("extra_specs")
    @classmethod
    def _limit_extra(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and len(value) > 30:
            raise ValueError("추가 스펙은 최대 30개까지 입력할 수 있습니다.")
        return value


class ProductCreate(BaseModel):
    category: ProductCategory
    title: Str(100, 2)
    description: Str(5000, 10)
    price: int = Field(ge=0, le=MAX_PRICE)
    condition: ProductCondition
    trade_location: Str(100) | None = None
    spec: ProductSpecIn | None = None


class ProductUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed.

    - trade_location may be set to null to clear it. Photos are managed via /products/{id}/images.
    - spec: send an object to update only the given spec fields, or null to remove all specs.
    """

    title: Str(100, 2) | None = None
    description: Str(5000, 10) | None = None
    price: int | None = Field(default=None, ge=0, le=MAX_PRICE)
    condition: ProductCondition | None = None
    trade_location: Str(100) | None = None
    spec: ProductSpecIn | None = None

    @model_validator(mode="after")
    def _validate(self) -> "ProductUpdate":
        if not self.model_fields_set:
            raise ValueError("수정할 항목을 하나 이상 입력해 주세요.")
        required = {"title", "description", "price", "condition"}
        nulled = sorted(f for f in required & self.model_fields_set if getattr(self, f) is None)
        if nulled:
            raise ValueError(f"다음 항목은 비울 수 없습니다: {', '.join(nulled)}")
        return self


class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductSpecOut(ORMModel):
    manufacturer: str | None
    model_name: str | None
    cpu_model: str | None
    cpu_cores: int | None
    ram_gb: int | None
    gpu_model: str | None
    vram_gb: int | None
    storage_gb: int | None
    storage_type: str | None
    extra_specs: dict[str, Any] | None


class ProductImageOut(ORMModel):
    id: int
    url: MediaUrl = Field(validation_alias="storage_key")
    thumbnail_url: MediaUrl = Field(validation_alias="thumb_key")
    width: int
    height: int
    sort_order: int


class ImageOrderUpdate(BaseModel):
    image_ids: list[int] = Field(min_length=1, max_length=50, description="원하는 순서대로 모든 이미지 id")


class ProductSummary(ORMModel):
    """List item: enough for a card in search results."""

    id: int
    category: ProductCategory
    title: str
    price: int
    condition: ProductCondition
    status: ProductStatus
    is_hot_deal: bool
    thumbnail_url: MediaUrl | None = Field(validation_alias="thumbnail_key", description="첫 번째 사진의 썸네일")
    trade_location: str | None
    view_count: int
    created_at: UTCDateTime
    spec: ProductSpecOut | None


class ProductDetail(ProductSummary):
    description: str
    images: list[ProductImageOut]
    updated_at: UTCDateTime
    seller: UserPublic


def product_page(items: list[Any], total: int, page: int, size: int) -> Page[ProductSummary]:
    return Page[ProductSummary](
        items=[ProductSummary.model_validate(p) for p in items],
        total=total,
        page=page,
        size=size,
        has_next=page * size < total,
    )


class ProductSort(StrEnum):
    LATEST = "latest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    POPULAR = "popular"


class MyProductParams(BaseModel):
    status: ProductStatus | None = Field(default=None, description="비우면 전체 (숨김·판매완료 포함)")
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)


class ProductSearchParams(BaseModel):
    """Query-string filters for GET /products (all optional, combined with AND)."""

    q: Str(100) | None = Field(default=None, description="제목 키워드")
    category: ProductCategory | None = None
    condition: list[ProductCondition] | None = Field(default=None, description="여러 개 지정 가능")
    min_price: int | None = Field(default=None, ge=0)
    max_price: int | None = Field(default=None, ge=0)
    manufacturer: Str(100) | None = Field(default=None, description="제조사 (부분 일치)")
    cpu: Str(120) | None = Field(default=None, description="CPU 모델 (부분 일치)")
    gpu: Str(120) | None = Field(default=None, description="GPU 모델 (부분 일치)")
    min_cores: int | None = Field(default=None, ge=1)
    min_ram_gb: int | None = Field(default=None, ge=1)
    min_vram_gb: int | None = Field(default=None, ge=1)
    min_storage_gb: int | None = Field(default=None, ge=1)
    hot_only: bool = False
    include_sold: bool = Field(default=False, description="판매완료·예약중 포함")
    sort: ProductSort = ProductSort.LATEST
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def _price_range(self) -> "ProductSearchParams":
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("최소 가격이 최대 가격보다 클 수 없습니다.")
        return self
