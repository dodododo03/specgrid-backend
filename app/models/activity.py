from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, enum_column
from app.models.enums import ActivityType


class UserActivityLog(CreatedAtMixin, Base):
    """Append-only log of views / searches / chats / trade attempts.

    user_id is nullable so anonymous visitors can be tracked via session_id.
    Chat *content* is never stored here — only minimal metadata in `detail`.
    """

    __tablename__ = "user_activity_logs"
    __table_args__ = (
        Index("ix_user_activity_logs_user_id_created_at", "user_id", "created_at"),
        Index("ix_user_activity_logs_activity_type_created_at", "activity_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    session_id: Mapped[str | None] = mapped_column(String(128), index=True)
    activity_type: Mapped[ActivityType] = mapped_column(
        enum_column(ActivityType, "activity_type"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    search_keyword: Mapped[str | None] = mapped_column(String(200))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))  # fits IPv6
    user_agent: Mapped[str | None] = mapped_column(String(512))
