from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, enum_column
from app.models.enums import MessageType
from app.models.product import Product
from app.models.user import User


class ChatRoom(TimestampMixin, Base):
    """One room per (product, buyer). The seller is denormalized for fast inbox queries."""

    __tablename__ = "chat_rooms"
    __table_args__ = (
        UniqueConstraint("product_id", "buyer_id"),
        CheckConstraint("buyer_id <> seller_id", name="buyer_not_seller"),
        Index("ix_chat_rooms_buyer_id_last_message_at", "buyer_id", "last_message_at"),
        Index("ix_chat_rooms_seller_id_last_message_at", "seller_id", "last_message_at"),
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
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime)

    product: Mapped[Product] = relationship()
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id])
    seller: Mapped[User] = relationship(foreign_keys=[seller_id])
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(CreatedAtMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        # Cursor pagination within a room: WHERE room_id = ? AND id < ? ORDER BY id DESC
        Index("ix_chat_messages_room_id_id", "room_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    message_type: Mapped[MessageType] = mapped_column(
        enum_column(MessageType, "message_type"), nullable=False, server_default=MessageType.TEXT.value
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))

    room: Mapped[ChatRoom] = relationship(back_populates="messages")
    sender: Mapped[User] = relationship()
