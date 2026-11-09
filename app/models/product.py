from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_column
from app.models.enums import ProductCategory, ProductCondition, ProductStatus
from app.models.user import User


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("view_count >= 0", name="view_count_non_negative"),
        # Main listing query: category tab + on-sale + newest first
        Index("ix_products_category_status_created_at", "category", "status", "created_at"),
        Index("ix_products_status_price", "status", "price"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category: Mapped[ProductCategory] = mapped_column(
        enum_column(ProductCategory, "product_category"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[ProductCondition] = mapped_column(
        enum_column(ProductCondition, "product_condition"), nullable=False
    )
    status: Mapped[ProductStatus] = mapped_column(
        enum_column(ProductStatus, "product_status"),
        nullable=False,
        server_default=ProductStatus.ON_SALE.value,
    )
    is_hot_deal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048))
    trade_location: Mapped[str | None] = mapped_column(String(100))
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # soft delete

    seller: Mapped[User] = relationship(back_populates="products")
    spec: Mapped[ProductSpec | None] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} title={self.title!r}>"


class ProductSpec(Base):
    """1:1 structured hardware specs used by the precision filters (CPU/RAM/GPU/VRAM/...)."""

    __tablename__ = "product_specs"
    __table_args__ = (
        Index("ix_product_specs_ram_gb", "ram_gb"),
        Index("ix_product_specs_vram_gb", "vram_gb"),
        Index("ix_product_specs_gpu_model", "gpu_model"),
        Index("ix_product_specs_cpu_model", "cpu_model"),
        Index("ix_product_specs_manufacturer", "manufacturer"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    model_name: Mapped[str | None] = mapped_column(String(150))
    cpu_model: Mapped[str | None] = mapped_column(String(120))
    cpu_cores: Mapped[int | None] = mapped_column(SmallInteger)
    ram_gb: Mapped[int | None] = mapped_column(Integer)
    gpu_model: Mapped[str | None] = mapped_column(String(120))
    vram_gb: Mapped[int | None] = mapped_column(SmallInteger)
    storage_gb: Mapped[int | None] = mapped_column(Integer)
    storage_type: Mapped[str | None] = mapped_column(String(20))  # e.g. NVMe, SATA SSD, HDD
    # Category-specific extras (e.g. keyboard switch, monitor refresh rate)
    extra_specs: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    product: Mapped[Product] = relationship(back_populates="spec")
