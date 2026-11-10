from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import TradeStatus
from app.schemas.chat import ChatProduct
from app.schemas.common import ORMModel, UTCDateTime
from app.schemas.user import UserPublic

TradeMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TradeCreate(BaseModel):
    product_id: int = Field(ge=1, le=2**63 - 1, description="구매할 상품 id")
    message: TradeMessage | None = Field(default=None, description="판매자에게 남길 말 (선택, 200자)")


class TradeOut(ORMModel):
    id: int
    product: ChatProduct
    buyer: UserPublic
    seller: UserPublic
    price: int = Field(description="요청 시점의 상품 가격")
    status: TradeStatus
    message: str | None
    created_at: UTCDateTime
    updated_at: UTCDateTime
    responded_at: UTCDateTime | None = Field(description="판매자가 수락/거절한 시각")
    completed_at: UTCDateTime | None


class TradeRole(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"


class TradeListParams(BaseModel):
    role: TradeRole | None = Field(default=None, description="buyer=내 구매 요청, seller=내 상품에 들어온 요청, 비우면 둘 다")
    status: TradeStatus | None = None
    product_id: int | None = Field(default=None, ge=1, le=2**63 - 1)
    page: int = Field(default=1, ge=1, le=1000)
    size: int = Field(default=20, ge=1, le=50)
