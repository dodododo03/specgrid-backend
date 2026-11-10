"""Import every model here so Base.metadata is complete (Alembic autogenerate relies on it)."""

from app.db.base import Base
from app.models.activity import UserActivityLog
from app.models.chat import ChatMessage, ChatRoom
from app.models.favorite import Favorite
from app.models.product import Product, ProductImage, ProductSpec
from app.models.trade import Trade
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Product",
    "ProductSpec",
    "ProductImage",
    "ChatRoom",
    "ChatMessage",
    "Favorite",
    "Trade",
    "UserActivityLog",
]
