from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import MessageType, ProductStatus
from app.schemas.common import ORMModel, UTCDateTime
from app.schemas.product import MediaUrl
from app.schemas.user import UserPublic

MessageContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ChatRoomCreate(BaseModel):
    product_id: int = Field(ge=1, le=2**63 - 1, description="문의할 상품 id")


class MessageCreate(BaseModel):
    content: MessageContent


class MessageOut(ORMModel):
    id: int
    room_id: int
    sender_id: int
    message_type: MessageType
    content: str
    is_read: bool
    created_at: UTCDateTime


class ChatProduct(ORMModel):
    """Just enough of the product to draw the header of a chat room."""

    id: int
    title: str
    price: int
    status: ProductStatus
    thumbnail_url: MediaUrl | None = Field(validation_alias="thumbnail_key")
    is_deleted: bool


class ChatRoomOut(BaseModel):
    id: int
    product: ChatProduct
    my_role: str = Field(description="buyer 또는 seller")
    partner: UserPublic = Field(description="대화 상대")
    last_message: MessageOut | None
    unread_count: int = Field(description="상대가 보냈고 내가 아직 안 읽은 메시지 수")
    last_message_at: UTCDateTime | None
    created_at: UTCDateTime


class ChatRoomList(BaseModel):
    items: list[ChatRoomOut]
    total: int
    page: int
    size: int
    has_next: bool


class RoomListParams(BaseModel):
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)


class MessageListParams(BaseModel):
    before_id: int | None = Field(default=None, ge=1, description="이 id보다 오래된 메시지 (위로 스크롤)")
    after_id: int | None = Field(default=None, ge=0, description="이 id 이후의 새 메시지 (새 메시지 확인)")
    limit: int = Field(default=30, ge=1, le=100)


class MessagePage(BaseModel):
    items: list[MessageOut] = Field(description="오래된 순 (id 오름차순)")
    has_more: bool = Field(description="같은 방향으로 더 불러올 메시지가 있는지")


class ReadResult(BaseModel):
    marked_read: int


class UnreadTotal(BaseModel):
    unread_count: int
