from pydantic import BaseModel, Field

from app.models.enums import ProductCategory
from app.schemas.common import UTCDateTime
from app.schemas.product import ProductSummary
from app.services.ranking_service import Period


class KeywordRankParams(BaseModel):
    period: Period = Field(default=Period.DAY, description="day=최근 24시간, week=7일, month=30일 (all은 상품 순위 전용)")
    limit: int = Field(default=10, ge=1, le=50)


class ProductRankParams(BaseModel):
    period: Period = Field(default=Period.WEEK, description="day / week / month = 해당 기간 조회수, all = 누적 조회수")
    category: ProductCategory | None = None
    include_sold: bool = Field(default=False, description="예약중·판매완료 상품도 포함")
    limit: int = Field(default=10, ge=1, le=50)


class KeywordRank(BaseModel):
    rank: int
    keyword: str
    count: int = Field(description="기간 내 검색 횟수 (같은 사람의 10분 내 반복 검색은 1회)")


class ProductRank(BaseModel):
    rank: int
    views: int = Field(description="기간 내 조회수 (같은 사람의 30분 내 반복 조회는 1회)")
    product: ProductSummary


class KeywordRanking(BaseModel):
    period: Period
    items: list[KeywordRank]
    generated_at: UTCDateTime = Field(description="집계 시각 (최대 60초 캐시)")


class ProductRanking(BaseModel):
    period: Period
    category: ProductCategory | None
    items: list[ProductRank]
    generated_at: UTCDateTime
