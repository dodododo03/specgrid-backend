"""Purchase flow: request -> accept/reject -> complete, with cancel along the way.

  requested --accept (seller)--> accepted --complete (seller)--> completed
      |                              |
      |--reject (seller)--> rejected |--cancel (buyer or seller)--> canceled (product back on sale)
      |--cancel (buyer)---> canceled

Product status follows the trade: accept -> reserved, complete -> sold, cancel an accepted
trade -> on_sale. When a trade completes, every other open request for that product is
rejected automatically.

Every state change runs under the product's Redis lock and locks the product row
(SELECT ... FOR UPDATE) before touching trades, always in that order, so concurrent
requests on one product are serialized and can't deadlock each other.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.models import Product, Trade, User
from app.models.enums import ACTIVE_TRADE_STATUSES, ProductStatus, TradeStatus, UserStatus
from app.schemas.trade import TradeListParams, TradeRole
from app.services.product_lock import ProductLock

TRADE_NOT_FOUND = "거래를 찾을 수 없습니다."
PRODUCT_NOT_FOUND = "상품을 찾을 수 없습니다."


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _trade_query():
    return select(Trade).options(
        joinedload(Trade.product), joinedload(Trade.buyer), joinedload(Trade.seller)
    )


def _participant(user: User):
    return or_(Trade.buyer_id == user.id, Trade.seller_id == user.id)


def _lock_product_row(db: Session, product_id: int) -> Product | None:
    return db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _lock_trade_row(db: Session, trade_id: int) -> Trade:
    return db.scalar(
        select(Trade).where(Trade.id == trade_id).with_for_update().execution_options(populate_existing=True)
    )


def _end_read_snapshot(db: Session) -> None:
    """Close the transaction opened by earlier plain reads (auth, trade lookup) before locking.

    MariaDB 11.6+ (innodb_snapshot_isolation=ON) pins a REPEATABLE READ snapshot at the first
    read. If another request changes the product while we wait for the lock, a later
    SELECT ... FOR UPDATE in that same old transaction fails with error 1020. Starting a fresh
    transaction after acquiring the lock means we always lock and read the latest data.
    (expire_on_commit=False, so already-loaded objects such as the current user stay usable.)
    """
    db.commit()


def get_trade(db: Session, trade_id: int, user: User) -> Trade:
    """Only the buyer and the seller can see a trade; to anyone else it doesn't exist (404)."""
    trade = db.scalar(
        _trade_query()
        .where(Trade.id == trade_id, _participant(user))
        .execution_options(populate_existing=True)
    )
    if trade is None:
        raise NotFoundError(TRADE_NOT_FOUND)
    return trade


def list_trades(db: Session, user: User, params: TradeListParams) -> tuple[list[Trade], int]:
    if params.role == TradeRole.BUYER:
        stmt = select(Trade).where(Trade.buyer_id == user.id)
    elif params.role == TradeRole.SELLER:
        stmt = select(Trade).where(Trade.seller_id == user.id)
    else:
        stmt = select(Trade).where(_participant(user))
    if params.status:
        stmt = stmt.where(Trade.status == params.status)
    if params.product_id:
        stmt = stmt.where(Trade.product_id == params.product_id)

    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Trade.id).subquery()))
    items = db.scalars(
        stmt.options(joinedload(Trade.product), joinedload(Trade.buyer), joinedload(Trade.seller))
        .order_by(Trade.created_at.desc(), Trade.id.desc())
        .limit(params.size)
        .offset((params.page - 1) * params.size)
    ).all()
    return list(items), total or 0


# ------------------------------------------------------------------ 1. request


def request_trade(db: Session, locks: ProductLock, buyer: User, product_id: int, message: str | None) -> Trade:
    _end_read_snapshot(db)
    with locks.hold(product_id):
        product = _lock_product_row(db, product_id)
        if product is None or product.status == ProductStatus.HIDDEN:
            db.rollback()
            raise NotFoundError(PRODUCT_NOT_FOUND)
        if product.seller_id == buyer.id:
            db.rollback()
            raise AppError("본인 상품은 구매 요청할 수 없습니다.")
        if product.status != ProductStatus.ON_SALE:
            db.rollback()
            raise ConflictError("예약중이거나 판매 완료된 상품입니다.")
        seller = db.get(User, product.seller_id)
        if seller is None or seller.status != UserStatus.ACTIVE:
            db.rollback()
            raise ConflictError("판매자가 탈퇴했거나 이용이 제한되어 거래할 수 없습니다.")
        open_request = db.scalar(
            select(Trade.id).where(
                Trade.product_id == product_id,
                Trade.buyer_id == buyer.id,
                Trade.status.in_(ACTIVE_TRADE_STATUSES),
            )
        )
        if open_request is not None:
            db.rollback()
            raise ConflictError("이미 이 상품에 진행 중인 구매 요청이 있습니다.")

        trade = Trade(
            product_id=product.id, buyer_id=buyer.id, seller_id=product.seller_id,
            price=product.price, status=TradeStatus.REQUESTED, message=message,
        )
        db.add(trade)
        try:
            db.commit()
        except IntegrityError:  # unique index caught a race the locks somehow missed
            db.rollback()
            raise ConflictError("이미 이 상품에 진행 중인 구매 요청이 있습니다.") from None
    return get_trade(db, trade.id, buyer)


# ------------------------------------------------------------------ 2-4. state changes


def _load_for_change(db: Session, trade_id: int, product_id: int) -> tuple[Trade, Product]:
    """Lock product row, then trade row (fixed order). Caller must already hold the Redis lock."""
    product = db.scalar(
        select(Product).where(Product.id == product_id).with_for_update().execution_options(populate_existing=True)
    )
    trade = _lock_trade_row(db, trade_id)
    return trade, product


def _product_id_of(db: Session, trade_id: int, user: User) -> int:
    product_id = db.scalar(select(Trade.product_id).where(Trade.id == trade_id, _participant(user)))
    if product_id is None:
        raise NotFoundError(TRADE_NOT_FOUND)
    return product_id


def _require_seller(trade: Trade, user: User, action: str) -> None:
    if trade.seller_id != user.id:
        raise PermissionDeniedError(f"판매자만 {action}할 수 있습니다.")


def _require_status(trade: Trade, *allowed: TradeStatus) -> None:
    if trade.status not in allowed:
        raise ConflictError(f"현재 상태({trade.status.value})에서는 할 수 없는 작업입니다.")


def accept_trade(db: Session, locks: ProductLock, trade_id: int, seller: User) -> Trade:
    """Seller accepts one request: the product becomes reserved for that buyer."""
    product_id = _product_id_of(db, trade_id, seller)  # immutable, safe to read before locking
    _end_read_snapshot(db)
    with locks.hold(product_id):
        try:
            trade, product = _load_for_change(db, trade_id, product_id)
            _require_seller(trade, seller, "수락")
            _require_status(trade, TradeStatus.REQUESTED)
            if product.deleted_at is not None:
                raise ConflictError("삭제된 상품입니다.")
            if product.status != ProductStatus.ON_SALE:
                # reserved = another request was already accepted (or the seller reserved it manually)
                raise ConflictError("판매중인 상품만 수락할 수 있습니다. 이미 예약중인 거래가 있으면 먼저 완료하거나 취소해 주세요.")
            buyer = db.get(User, trade.buyer_id)
            if buyer is None or buyer.status != UserStatus.ACTIVE:
                raise ConflictError("구매자가 탈퇴했거나 이용이 제한되어 수락할 수 없습니다.")

            trade.status = TradeStatus.ACCEPTED
            trade.responded_at = _now()
            product.status = ProductStatus.RESERVED
            db.commit()
        except (AppError, IntegrityError) as exc:
            db.rollback()
            if isinstance(exc, IntegrityError):
                raise ConflictError("이미 예약중인 거래가 있습니다.") from None
            raise
    return get_trade(db, trade_id, seller)


def reject_trade(db: Session, locks: ProductLock, trade_id: int, seller: User) -> Trade:
    product_id = _product_id_of(db, trade_id, seller)  # immutable, safe to read before locking
    _end_read_snapshot(db)
    with locks.hold(product_id):
        try:
            trade, _ = _load_for_change(db, trade_id, product_id)
            _require_seller(trade, seller, "거절")
            _require_status(trade, TradeStatus.REQUESTED)
            trade.status = TradeStatus.REJECTED
            trade.responded_at = _now()
            db.commit()
        except AppError:
            db.rollback()
            raise
    return get_trade(db, trade_id, seller)


def complete_trade(db: Session, locks: ProductLock, trade_id: int, seller: User) -> tuple[Trade, list[int]]:
    """Seller marks the reserved trade as done: product -> sold, other open requests -> rejected.

    Returns (trade, ids of the trades that were auto-rejected) so callers can notify those buyers.
    """
    product_id = _product_id_of(db, trade_id, seller)  # immutable, safe to read before locking
    _end_read_snapshot(db)
    with locks.hold(product_id):
        try:
            trade, product = _load_for_change(db, trade_id, product_id)
            _require_seller(trade, seller, "거래 완료")
            _require_status(trade, TradeStatus.ACCEPTED)

            now = _now()
            others = list(db.scalars(
                select(Trade.id).where(
                    Trade.product_id == product.id,
                    Trade.id != trade.id,
                    Trade.status == TradeStatus.REQUESTED,
                )
            ))
            if others:
                db.execute(
                    update(Trade)
                    .where(Trade.id.in_(others))
                    .values(status=TradeStatus.REJECTED, responded_at=now)
                    .execution_options(synchronize_session=False)
                )
            trade.status = TradeStatus.COMPLETED
            trade.completed_at = now
            product.status = ProductStatus.SOLD
            db.commit()
        except AppError:
            db.rollback()
            raise
    return get_trade(db, trade_id, seller), others


def cancel_trade(db: Session, locks: ProductLock, trade_id: int, user: User) -> Trade:
    """Buyer: cancel a pending or accepted request. Seller: cancel an accepted one (e.g. no-show).

    (A seller turns down a *pending* request with reject, not cancel.)
    Canceling an accepted trade puts the product back on sale.
    """
    product_id = _product_id_of(db, trade_id, user)  # immutable, safe to read before locking
    _end_read_snapshot(db)
    with locks.hold(product_id):
        try:
            trade, product = _load_for_change(db, trade_id, product_id)
            if trade.buyer_id == user.id:
                _require_status(trade, TradeStatus.REQUESTED, TradeStatus.ACCEPTED)
            else:
                if trade.status == TradeStatus.REQUESTED:
                    raise ConflictError("수락 전 요청은 취소가 아니라 거절해 주세요.")
                _require_status(trade, TradeStatus.ACCEPTED)

            was_accepted = trade.status == TradeStatus.ACCEPTED
            trade.status = TradeStatus.CANCELED
            if was_accepted and product.status == ProductStatus.RESERVED and product.deleted_at is None:
                product.status = ProductStatus.ON_SALE
            db.commit()
        except AppError:
            db.rollback()
            raise
    return get_trade(db, trade_id, user)


# ------------------------------------------------------------------ hooks for product_service


def has_accepted_trade(db: Session, product_id: int) -> bool:
    return db.scalar(
        select(Trade.id).where(Trade.product_id == product_id, Trade.status == TradeStatus.ACCEPTED)
    ) is not None


def reject_open_requests(db: Session, product_id: int) -> None:
    """Product is being deleted: close its pending requests (caller commits)."""
    db.execute(
        update(Trade)
        .where(Trade.product_id == product_id, Trade.status == TradeStatus.REQUESTED)
        .values(status=TradeStatus.REJECTED, responded_at=_now())
        .execution_options(synchronize_session=False)
    )
