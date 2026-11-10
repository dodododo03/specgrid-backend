"""Rankings computed from user_activity_logs with plain SQL aggregation (GROUP BY + COUNT).

  인기 검색어:  SELECT search_keyword, COUNT(*) FROM user_activity_logs
                WHERE activity_type='search' AND created_at >= :since
                GROUP BY search_keyword ORDER BY COUNT(*) DESC LIMIT :n
  많이 본 상품: same idea, GROUP BY product_id over 'view' rows, joined to visible products.

Both queries are served by covering indexes (activity_type, created_at, search_keyword / product_id),
so MariaDB reads only the index for the time window, never the whole table.
Results are cached in Redis for CACHE_SECONDS: rankings don't need to be real-time to the second,
and the cache keeps a popular landing page from re-running the aggregation on every visit.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Favorite, Product, UserActivityLog
from app.models.enums import ActivityType, ProductCategory, ProductStatus

logger = logging.getLogger(__name__)

CACHE_SECONDS = 60


class Period(StrEnum):
    DAY = "day"      # last 24 hours
    WEEK = "week"    # last 7 days
    MONTH = "month"  # last 30 days
    ALL = "all"      # products only: lifetime products.view_count


class Metric(StrEnum):
    VIEWS = "views"          # 많이 본 상품
    FAVORITES = "favorites"  # 찜 많은 상품


_WINDOWS = {Period.DAY: timedelta(days=1), Period.WEEK: timedelta(days=7), Period.MONTH: timedelta(days=30)}


def _since(period: Period) -> datetime:
    # created_at is naive UTC (the DB session runs with time_zone '+00:00')
    return datetime.now(UTC).replace(tzinfo=None) - _WINDOWS[period]


class RankingCache:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client

    def get(self, key: str) -> Any | None:
        try:
            raw = self.r.get(key)
        except redis.RedisError:
            return None  # fail open: just compute it
        return json.loads(raw) if raw else None

    def put(self, key: str, value: Any) -> None:
        try:
            self.r.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=CACHE_SECONDS)
        except redis.RedisError:
            logger.warning("ranking cache write failed", exc_info=True)


def popular_keywords(db: Session, period: Period, limit: int) -> list[tuple[str, int]]:
    count = func.count().label("cnt")
    rows = db.execute(
        select(UserActivityLog.search_keyword, count)
        .where(
            UserActivityLog.activity_type == ActivityType.SEARCH,
            UserActivityLog.created_at >= _since(period),
            UserActivityLog.search_keyword.is_not(None),
        )
        .group_by(UserActivityLog.search_keyword)
        .order_by(count.desc(), UserActivityLog.search_keyword)
        .limit(limit)
    ).all()
    return [(keyword, cnt) for keyword, cnt in rows]


def popular_products(
    db: Session, period: Period, limit: int, category: ProductCategory | None, include_sold: bool,
    metric: Metric = Metric.VIEWS,
) -> list[tuple[Product, int]]:
    visible = [Product.deleted_at.is_(None), Product.status != ProductStatus.HIDDEN]
    if not include_sold:
        visible.append(Product.status == ProductStatus.ON_SALE)
    if category:
        visible.append(Product.category == category)

    if period == Period.ALL:  # lifetime counters stored on the product row
        counter = Product.view_count if metric == Metric.VIEWS else Product.favorite_count
        products = db.scalars(
            select(Product)
            .options(joinedload(Product.spec))
            .where(*visible, counter > 0)
            .order_by(counter.desc(), Product.id.desc())
            .limit(limit)
        ).all()
        return [(p, p.view_count if metric == Metric.VIEWS else p.favorite_count) for p in products]

    if metric == Metric.VIEWS:
        id_col, created = UserActivityLog.product_id, UserActivityLog.created_at
        source = [UserActivityLog.activity_type == ActivityType.VIEW]
    else:  # favorites added in the window that still exist (un-hearted ones don't count)
        id_col, created = Favorite.product_id, Favorite.created_at
        source = []
    score = func.count().label("score")
    rows = db.execute(
        select(id_col, score)
        .join(Product, Product.id == id_col)
        .where(*source, created >= _since(period), *visible)
        .group_by(id_col)
        .order_by(score.desc(), id_col.desc())
        .limit(limit)
    ).all()
    if not rows:
        return []
    by_id = {
        p.id: p
        for p in db.scalars(
            select(Product).options(joinedload(Product.spec)).where(Product.id.in_([pid for pid, _ in rows]))
        ).unique()
    }
    return [(by_id[pid], cnt) for pid, cnt in rows if pid in by_id]
