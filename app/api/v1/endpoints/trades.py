from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status

from app.api.deps import Activity, CurrentUser, CurrentViewer, DbSession, RedisClient
from app.models import Trade
from app.models.enums import ActivityType
from app.schemas.common import Page
from app.schemas.trade import TradeCreate, TradeListParams, TradeOut
from app.services import trade_service
from app.services.chat_events import ChatEvents
from app.services.product_lock import ProductLock

router = APIRouter(prefix="/trades", tags=["trades"])

TradeId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def get_product_lock(client: RedisClient) -> ProductLock:
    return ProductLock(client)


def get_events(client: RedisClient) -> ChatEvents:
    return ChatEvents(client)


Locks = Annotated[ProductLock, Depends(get_product_lock)]
Events = Annotated[ChatEvents, Depends(get_events)]


def _log(activity, viewer, trade: Trade, action: str) -> None:
    activity.record(ActivityType.TRADE, viewer, product_id=trade.product_id,
                    detail={"trade_id": trade.id, "action": action})


def _notify(events: ChatEvents, trade: Trade) -> TradeOut:
    """Push the new state to both sides over the chat WebSocket (best-effort)."""
    out = TradeOut.model_validate(trade)
    events.publish([trade.buyer_id, trade.seller_id], {"type": "trade", "trade": out.model_dump(mode="json")})
    return out


@router.post(
    "",
    response_model=TradeOut,
    status_code=status.HTTP_201_CREATED,
    summary="1. 구매 요청",
    description="판매중(on_sale)인 상품에만 요청할 수 있고, 같은 상품에 진행 중인 요청은 1개까지입니다.",
)
def request_trade(
    data: TradeCreate, user: CurrentUser, db: DbSession,
    locks: Locks, events: Events, viewer: CurrentViewer, activity: Activity,
):
    trade = trade_service.request_trade(db, locks, user, data.product_id, data.message)
    _log(activity, viewer, trade, "request")
    return _notify(events, trade)


@router.get("", response_model=Page[TradeOut], summary="내 거래 목록 (최신순)")
def list_trades(params: Annotated[TradeListParams, Query()], user: CurrentUser, db: DbSession):
    items, total = trade_service.list_trades(db, user, params)
    return Page[TradeOut](
        items=[TradeOut.model_validate(t) for t in items],
        total=total,
        page=params.page,
        size=params.size,
        has_next=params.page * params.size < total,
    )


@router.get("/{trade_id}", response_model=TradeOut, summary="거래 상세 (구매자·판매자만)")
def get_trade(trade_id: TradeId, user: CurrentUser, db: DbSession):
    return trade_service.get_trade(db, trade_id, user)


@router.post(
    "/{trade_id}/accept",
    response_model=TradeOut,
    summary="2. 수락 (판매자) → 상품 예약중",
    description="동시에 여러 요청을 수락해도 한 건만 성공하고 나머지는 409입니다.",
)
def accept_trade(
    trade_id: TradeId, user: CurrentUser, db: DbSession,
    locks: Locks, events: Events, viewer: CurrentViewer, activity: Activity,
):
    trade = trade_service.accept_trade(db, locks, trade_id, user)
    _log(activity, viewer, trade, "accept")
    return _notify(events, trade)


@router.post("/{trade_id}/reject", response_model=TradeOut, summary="2. 거절 (판매자)")
def reject_trade(
    trade_id: TradeId, user: CurrentUser, db: DbSession,
    locks: Locks, events: Events, viewer: CurrentViewer, activity: Activity,
):
    trade = trade_service.reject_trade(db, locks, trade_id, user)
    _log(activity, viewer, trade, "reject")
    return _notify(events, trade)


@router.post(
    "/{trade_id}/complete",
    response_model=TradeOut,
    summary="3. 거래 완료 (판매자) → 상품 판매완료",
    description="같은 상품의 다른 대기 중 요청은 자동으로 거절됩니다.",
)
def complete_trade(
    trade_id: TradeId, user: CurrentUser, db: DbSession,
    locks: Locks, events: Events, viewer: CurrentViewer, activity: Activity,
):
    trade, auto_rejected = trade_service.complete_trade(db, locks, trade_id, user)
    _log(activity, viewer, trade, "complete")
    for other_id in auto_rejected:
        other = db.get(Trade, other_id, populate_existing=True)
        if other is not None:
            _notify(events, other)
    return _notify(events, trade)


@router.post(
    "/{trade_id}/cancel",
    response_model=TradeOut,
    summary="거래 취소",
    description="구매자: 대기·예약 중 취소 가능. 판매자: 예약(수락) 후에만 취소 가능 (대기 중이면 거절 사용). "
    "예약을 취소하면 상품은 다시 판매중이 됩니다.",
)
def cancel_trade(
    trade_id: TradeId, user: CurrentUser, db: DbSession,
    locks: Locks, events: Events, viewer: CurrentViewer, activity: Activity,
):
    trade = trade_service.cancel_trade(db, locks, trade_id, user)
    _log(activity, viewer, trade, "cancel")
    return _notify(events, trade)
