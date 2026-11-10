"""Activity logging (views, searches, chats, trades) — the raw data behind the rankings.

Rules:
- Best-effort: a logging failure is written to the server log and never fails the user's request.
- Repeats are dropped with short-lived Redis keys, so refresh-spamming can't game the rankings:
    same viewer + same product within 30 min  -> counted once (also for products.view_count)
    same viewer + same keyword within 10 min  -> counted once
  If Redis is down we count anyway (fail open: rankings get a bit noisier, nothing breaks).
- The seller's own views don't count.
- Chat *content* is never stored here, only ids.

Dedupe keys: specgrid:seen:view:{product_id}:{viewer}, specgrid:seen:search:{sha1(keyword)}:{viewer}
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import redis
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Product, UserActivityLog
from app.models.enums import ActivityType

logger = logging.getLogger(__name__)

VIEW_DEDUPE_SECONDS = 30 * 60
SEARCH_DEDUPE_SECONDS = 10 * 60
MAX_KEYWORD_LENGTH = 100


@dataclass(frozen=True)
class Viewer:
    """Who is doing something, for activity logs. Anonymous visitors are told apart by IP + browser."""

    user_id: int | None
    ip: str
    user_agent: str | None

    @property
    def key(self) -> str:
        if self.user_id is not None:
            return f"u{self.user_id}"
        ua = hashlib.sha1((self.user_agent or "").encode()).hexdigest()[:12]
        return f"a{self.ip}:{ua}"


def normalize_keyword(raw: str | None) -> str | None:
    """'  RTX   4080 ' and 'rtx 4080' are the same search for ranking purposes."""
    if not raw:
        return None
    keyword = " ".join(raw.split()).lower()[:MAX_KEYWORD_LENGTH]
    return keyword or None


class ActivityRecorder:
    def __init__(self, db: Session, client: redis.Redis) -> None:
        self.db = db
        self.r = client

    # ------------------------------------------------------------------ public API

    def record_view(self, product: Product, viewer: Viewer) -> bool:
        """Returns True if this view counts (then the caller also bumps products.view_count)."""
        if viewer.user_id is not None and viewer.user_id == product.seller_id:
            return False
        if not self._first_time(f"specgrid:seen:view:{product.id}:{viewer.key}", VIEW_DEDUPE_SECONDS):
            return False
        self._insert(ActivityType.VIEW, viewer, product_id=product.id)
        return True

    def record_search(self, raw_keyword: str | None, viewer: Viewer, detail: dict[str, Any]) -> None:
        keyword = normalize_keyword(raw_keyword)
        if keyword is None:
            return
        digest = hashlib.sha1(keyword.encode()).hexdigest()[:16]
        if not self._first_time(f"specgrid:seen:search:{digest}:{viewer.key}", SEARCH_DEDUPE_SECONDS):
            return
        self._insert(ActivityType.SEARCH, viewer, search_keyword=keyword, detail=detail)

    def record(self, activity: ActivityType, viewer: Viewer, *, product_id: int | None = None,
               detail: dict[str, Any] | None = None) -> None:
        """Chats / trades / favorites: every event is kept (no dedupe)."""
        self._insert(activity, viewer, product_id=product_id, detail=detail)

    # ------------------------------------------------------------------ internals

    def _first_time(self, key: str, ttl: int) -> bool:
        try:
            return bool(self.r.set(key, 1, nx=True, ex=ttl))
        except redis.RedisError:
            logger.warning("activity dedupe skipped (Redis unavailable)", exc_info=True)
            return True

    def _insert(self, activity: ActivityType, viewer: Viewer, *, product_id: int | None = None,
                search_keyword: str | None = None, detail: dict[str, Any] | None = None) -> None:
        try:
            self.db.add(UserActivityLog(
                user_id=viewer.user_id,
                activity_type=activity,
                product_id=product_id,
                search_keyword=search_keyword,
                detail=detail,
                ip_address=viewer.ip[:45],
                user_agent=viewer.user_agent,
            ))
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            logger.warning("activity log not saved: %s", activity.value, exc_info=True)
