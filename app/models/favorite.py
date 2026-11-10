from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin
from app.models.product import Product


class Favorite(CreatedAtMixin, Base):
    """찜: one row per (user, product). products.favorite_count mirrors the number of rows."""

    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id"),  # double-tapping the heart can't create two rows
        Index("ix_favorites_user_id_created_at", "user_id", "created_at"),        # "내 찜 목록", newest first
        Index("ix_favorites_product_id_created_at", "product_id", "created_at"),  # ranking by period
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    product: Mapped[Product] = relationship()
