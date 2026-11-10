from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_column
from app.models.enums import TradeStatus
from app.models.product import Product
from app.models.user import User


class Trade(TimestampMixin, Base):
    """A buyer's purchase request for a product and its lifecycle.

    requested -> accepted -> completed          (product: on_sale -> reserved -> sold)
              -> rejected / canceled            (accepted -> canceled puts the product back on sale)

    Concurrency is guarded in three layers:
      1. Redis lock per product (app/services/product_lock.py) serializes trade actions across servers
      2. SELECT ... FOR UPDATE on the product row inside the transaction
      3. the unique indexes below, the last line of defense if both of the above were bypassed
    """

    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("buyer_id <> seller_id", name="buyer_not_seller"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        # A buyer has at most one open (requested/accepted) request per product.
        Index("uq_trades_product_id_active_buyer_id", "product_id", "active_buyer_id", unique=True),
        # A product has at most one accepted trade at a time.
        Index("uq_trades_accepted_product_id", "accepted_product_id", unique=True),
        Index("ix_trades_buyer_id_created_at", "buyer_id", "created_at"),
        Index("ix_trades_seller_id_created_at", "seller_id", "created_at"),
        Index("ix_trades_product_id_status", "product_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    buyer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # snapshot at request time
    status: Mapped[TradeStatus] = mapped_column(
        enum_column(TradeStatus, "trade_status"),
        nullable=False,
        server_default=TradeStatus.REQUESTED.value,
    )
    message: Mapped[str | None] = mapped_column(String(200))  # buyer's note to the seller
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)  # accepted / rejected
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Generated columns (NULL when not applicable; UNIQUE ignores NULLs) back the indexes above.
    active_buyer_id: Mapped[int | None] = mapped_column(
        BigInteger, Computed("IF(status IN ('requested','accepted'), buyer_id, NULL)", persisted=True)
    )
    accepted_product_id: Mapped[int | None] = mapped_column(
        BigInteger, Computed("IF(status = 'accepted', product_id, NULL)", persisted=True)
    )

    product: Mapped[Product] = relationship()
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id])
    seller: Mapped[User] = relationship(foreign_keys=[seller_id])
