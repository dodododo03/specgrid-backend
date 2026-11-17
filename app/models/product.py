from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, enum_column
from app.models.enums import ProductCategory, ProductCondition, ProductStatus
from app.models.user import User


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        CheckConstraint("view_count >= 0", name="view_count_non_negative"),
        CheckConstraint("favorite_count >= 0", name="favorite_count_non_negative"),
        # A map pin is a (lat, lng) pair: both set or both empty.
        CheckConstraint("(trade_lat IS NULL) = (trade_lng IS NULL)", name="trade_point_pair"),
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
    trade_location: Mapped[str | None] = mapped_column(String(100))
    # Map pin for trade_location (WGS84, picked on the Kakao map). Empty = text-only location.
    trade_lat: Mapped[float | None] = mapped_column(Double)
    trade_lng: Mapped[float | None] = mapped_column(Double)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Denormalized COUNT(*) of favorites, kept in sync in the same transaction (cheap for list cards).
    favorite_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)  # soft delete

    seller: Mapped[User] = relationship(back_populates="products")
    spec: Mapped[ProductSpec | None] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    # selectin: one extra query per page of products, not one per product
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="(ProductImage.sort_order, ProductImage.id)",
        lazy="selectin",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def trade_point(self) -> dict[str, float] | None:
        if self.trade_lat is None or self.trade_lng is None:
            return None
        return {"lat": self.trade_lat, "lng": self.trade_lng}

    @property
    def thumbnail_key(self) -> str | None:
        """The first image is the cover shown in listings."""
        return self.images[0].thumb_key if self.images else None

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


class ProductImage(CreatedAtMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (Index("ix_product_images_product_id_sort_order", "product_id", "sort_order"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    # Storage keys (not URLs): the public URL is derived from settings at response time.
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    thumb_key: Mapped[str] = mapped_column(String(255), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    product: Mapped[Product] = relationship(back_populates="images")
