from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, RedisClient
from app.core.exceptions import AppError
from app.schemas.product import ProductSummary
from app.schemas.ranking import (
    KeywordRank,
    KeywordRanking,
    KeywordRankParams,
    ProductRank,
    ProductRanking,
    ProductRankParams,
)
from app.services import ranking_service
from app.services.ranking_service import Period, RankingCache

router = APIRouter(prefix="/rankings", tags=["rankings"])


def get_cache(client: RedisClient) -> RankingCache:
    return RankingCache(client)


Cache = Annotated[RankingCache, Depends(get_cache)]


@router.get("/keywords", response_model=KeywordRanking, summary="인기 검색어 순위")
def keyword_ranking(params: Annotated[KeywordRankParams, Query()], db: DbSession, cache: Cache):
    if params.period == Period.ALL:
        raise AppError("인기 검색어는 day / week / month 중에서 선택해 주세요.")
    key = f"specgrid:ranking:keywords:{params.period}:{params.limit}"
    if (cached := cache.get(key)) is not None:
        return cached
    rows = ranking_service.popular_keywords(db, params.period, params.limit)
    result = KeywordRanking(
        period=params.period,
        items=[KeywordRank(rank=i, keyword=k, count=c) for i, (k, c) in enumerate(rows, start=1)],
        generated_at=datetime.now(UTC),
    )
    cache.put(key, result.model_dump(mode="json"))
    return result


@router.get("/products", response_model=ProductRanking, summary="많이 본 상품 순위")
def product_ranking(params: Annotated[ProductRankParams, Query()], db: DbSession, cache: Cache):
    key = (f"specgrid:ranking:products:{params.period}:{params.category or 'all'}:"
           f"{int(params.include_sold)}:{params.limit}")
    if (cached := cache.get(key)) is not None:
        return cached
    rows = ranking_service.popular_products(db, params.period, params.limit, params.category, params.include_sold)
    result = ProductRanking(
        period=params.period,
        category=params.category,
        items=[
            ProductRank(rank=i, views=v, product=ProductSummary.model_validate(p))
            for i, (p, v) in enumerate(rows, start=1)
        ],
        generated_at=datetime.now(UTC),
    )
    cache.put(key, result.model_dump(mode="json"))
    return result
