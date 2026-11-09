"""Import every model here so Base.metadata is complete (Alembic autogenerate relies on it)."""

from app.db.base import Base
from app.models.activity import UserActivityLog
from app.models.chat import ChatMessage, ChatRoom
from app.models.product import Product, ProductSpec
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Product",
    "ProductSpec",
    "ChatRoom",
    "ChatMessage",
    "UserActivityLog",
]
