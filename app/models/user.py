from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_column
from app.models.enums import UserRole, UserStatus

if TYPE_CHECKING:
    from app.models.product import Product


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Nullable so social-login (OAuth) accounts can exist without a local password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    # Storage key (e.g. "users/9/ab12...cd.webp"); the public URL is built at response time.
    profile_image_key: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, "user_role"), nullable=False, server_default=UserRole.USER.value
    )
    status: Mapped[UserStatus] = mapped_column(
        enum_column(UserStatus, "user_status"), nullable=False, server_default=UserStatus.ACTIVE.value
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    products: Mapped[list[Product]] = relationship(back_populates="seller")

    def __repr__(self) -> str:
        return f"<User id={self.id} nickname={self.nickname!r}>"
