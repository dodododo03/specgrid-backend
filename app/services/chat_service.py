"""1:1 chat between a buyer and the seller of a product.

One room per (product, buyer). Only the two participants can see a room; to everyone else it
looks like it doesn't exist (404), so room ids can't be probed.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import ChatMessage, ChatRoom, Product, User
from app.models.enums import MessageType, ProductStatus, UserStatus
from app.schemas.chat import MessageListParams, RoomListParams

ROOM_NOT_FOUND = "채팅방을 찾을 수 없습니다."


def _now() -> datetime:
    # Naive UTC, second precision: matches what the DATETIME column stores.
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _room_query():
    return select(ChatRoom).options(
        joinedload(ChatRoom.product), joinedload(ChatRoom.buyer), joinedload(ChatRoom.seller)
    )


def _participant(user: User):
    return or_(ChatRoom.buyer_id == user.id, ChatRoom.seller_id == user.id)


# ------------------------------------------------------------------ rooms


def open_room(db: Session, buyer: User, product_id: int) -> tuple[ChatRoom, bool]:
    """Get the buyer's room for this product, creating it if needed. Returns (room, created)."""
    existing = db.scalar(
        _room_query().where(ChatRoom.product_id == product_id, ChatRoom.buyer_id == buyer.id)
    )
    if existing is not None:
        return existing, False

    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.deleted_at.is_(None),
            Product.status != ProductStatus.HIDDEN,
        )
    )
    if product is None:
        raise NotFoundError("상품을 찾을 수 없습니다.")
    if product.seller_id == buyer.id:
        raise AppError("본인 상품에는 채팅을 시작할 수 없습니다.")
    if product.status == ProductStatus.SOLD:
        raise ConflictError("판매 완료된 상품입니다.")

    room = ChatRoom(product_id=product.id, buyer_id=buyer.id, seller_id=product.seller_id)
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        # Same buyer double-tapped "채팅하기": the other request created the room first.
        db.rollback()
        existing = db.scalar(
            _room_query().where(ChatRoom.product_id == product_id, ChatRoom.buyer_id == buyer.id)
        )
        if existing is None:
            raise
        return existing, False
    return get_room(db, room.id, buyer), True


def get_room(db: Session, room_id: int, user: User) -> ChatRoom:
    room = db.scalar(
        _room_query()
        .where(ChatRoom.id == room_id, _participant(user))
        .execution_options(populate_existing=True)
    )
    if room is None:
        raise NotFoundError(ROOM_NOT_FOUND)
    return room


def list_rooms(db: Session, user: User, params: RoomListParams) -> tuple[list[ChatRoom], int]:
    """Inbox: rooms with messages first, most recent conversation on top."""
    base = select(ChatRoom).where(_participant(user))
    total = db.scalar(select(func.count()).select_from(base.with_only_columns(ChatRoom.id).subquery()))
    rooms = db.scalars(
        base.options(joinedload(ChatRoom.product), joinedload(ChatRoom.buyer), joinedload(ChatRoom.seller))
        .order_by(
            func.coalesce(ChatRoom.last_message_at, ChatRoom.created_at).desc(),
            ChatRoom.id.desc(),
        )
        .limit(params.size)
        .offset((params.page - 1) * params.size)
    ).all()
    return list(rooms), total or 0


def last_messages(db: Session, room_ids: list[int]) -> dict[int, ChatMessage]:
    """Latest message of each room in one query (uses the (room_id, id) index)."""
    if not room_ids:
        return {}
    latest_ids = (
        select(func.max(ChatMessage.id))
        .where(ChatMessage.room_id.in_(room_ids))
        .group_by(ChatMessage.room_id)
    )
    messages = db.scalars(select(ChatMessage).where(ChatMessage.id.in_(latest_ids))).all()
    return {m.room_id: m for m in messages}


def unread_counts(db: Session, user: User, room_ids: list[int]) -> dict[int, int]:
    if not room_ids:
        return {}
    rows = db.execute(
        select(ChatMessage.room_id, func.count())
        .where(
            ChatMessage.room_id.in_(room_ids),
            ChatMessage.sender_id != user.id,
            ChatMessage.is_read.is_(False),
        )
        .group_by(ChatMessage.room_id)
    ).all()
    return {room_id: count for room_id, count in rows}


def total_unread(db: Session, user: User) -> int:
    """Badge count across all of the user's rooms."""
    count = db.scalar(
        select(func.count())
        .select_from(ChatMessage)
        .join(ChatRoom, ChatRoom.id == ChatMessage.room_id)
        .where(
            _participant(user),
            ChatMessage.sender_id != user.id,
            ChatMessage.is_read.is_(False),
        )
    )
    return count or 0


# ------------------------------------------------------------------ messages


def list_messages(
    db: Session, room_id: int, user: User, params: MessageListParams
) -> tuple[list[ChatMessage], bool]:
    """Cursor pagination by message id.

    - neither cursor: newest `limit` messages (opening the room)
    - before_id: older messages (scrolling up)
    - after_id: messages newer than what the client already has (polling for new ones)
    Items are always returned oldest-first so the client can append them directly.
    """
    if params.before_id is not None and params.after_id is not None:
        raise AppError("before_id와 after_id는 함께 쓸 수 없습니다.")
    get_room(db, room_id, user)  # access check

    stmt = select(ChatMessage).where(ChatMessage.room_id == room_id)
    if params.after_id is not None:
        rows = db.scalars(
            stmt.where(ChatMessage.id > params.after_id).order_by(ChatMessage.id.asc()).limit(params.limit + 1)
        ).all()
        has_more = len(rows) > params.limit
        return list(rows[: params.limit]), has_more

    if params.before_id is not None:
        stmt = stmt.where(ChatMessage.id < params.before_id)
    rows = db.scalars(stmt.order_by(ChatMessage.id.desc()).limit(params.limit + 1)).all()
    has_more = len(rows) > params.limit
    return list(reversed(rows[: params.limit])), has_more


def send_message(db: Session, room_id: int, sender: User, content: str) -> ChatMessage:
    # Lock the room so last_message_at always moves forward with the newest message.
    room = db.scalar(
        select(ChatRoom).where(ChatRoom.id == room_id, _participant(sender)).with_for_update()
    )
    if room is None:
        raise NotFoundError(ROOM_NOT_FOUND)
    partner_id = room.seller_id if room.buyer_id == sender.id else room.buyer_id
    partner = db.get(User, partner_id)
    if partner is None or partner.status != UserStatus.ACTIVE:
        db.rollback()
        raise ConflictError("탈퇴했거나 이용이 제한된 사용자에게는 메시지를 보낼 수 없습니다.")

    now = _now()
    message = ChatMessage(
        room_id=room.id, sender_id=sender.id, message_type=MessageType.TEXT, content=content,
        is_read=False, created_at=now,
    )
    db.add(message)
    room.last_message_at = now
    db.commit()
    return message


def mark_read(db: Session, room_id: int, user: User) -> int:
    """Mark everything the partner sent in this room as read. Returns how many changed."""
    get_room(db, room_id, user)
    result = db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.room_id == room_id,
            ChatMessage.sender_id != user.id,
            ChatMessage.is_read.is_(False),
        )
        .values(is_read=True)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount
