from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict

from app.core.storage import get_storage


def _as_utc(value: datetime) -> datetime:
    # DB stores naive UTC (connection time_zone='+00:00'); make it explicit in responses.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]


def _media_url(key: str) -> str:
    return get_storage().url(key)


# DB holds storage keys; responses expose public URLs built from the current storage settings.
MediaUrl = Annotated[str, AfterValidator(_media_url)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int
    has_next: bool
