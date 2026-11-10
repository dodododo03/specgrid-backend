from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models import ChatMessage, ChatRoom, User
from app.schemas.chat import (
    ChatProduct,
    ChatRoomCreate,
    ChatRoomList,
    ChatRoomOut,
    MessageCreate,
    MessageListParams,
    MessageOut,
    MessagePage,
    ReadResult,
    RoomListParams,
    UnreadTotal,
)
from app.schemas.user import UserPublic
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])

RoomId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def _room_out(room: ChatRoom, me: User, last: ChatMessage | None, unread: int) -> ChatRoomOut:
    is_buyer = room.buyer_id == me.id
    return ChatRoomOut(
        id=room.id,
        product=ChatProduct.model_validate(room.product),
        my_role="buyer" if is_buyer else "seller",
        partner=UserPublic.model_validate(room.seller if is_buyer else room.buyer),
        last_message=MessageOut.model_validate(last) if last else None,
        unread_count=unread,
        last_message_at=room.last_message_at,
        created_at=room.created_at,
    )


def _single_room_out(db: Session, room: ChatRoom, me: User) -> ChatRoomOut:
    last = chat_service.last_messages(db, [room.id]).get(room.id)
    unread = chat_service.unread_counts(db, me, [room.id]).get(room.id, 0)
    return _room_out(room, me, last, unread)


@router.post(
    "/rooms",
    response_model=ChatRoomOut,
    summary="상품 판매자와 채팅 시작 (이미 있으면 기존 방)",
    responses={201: {"description": "새 채팅방 생성"}, 200: {"description": "기존 채팅방 반환"}},
)
def open_room(data: ChatRoomCreate, user: CurrentUser, db: DbSession, response: Response):
    room, created = chat_service.open_room(db, user, data.product_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _single_room_out(db, room, user)


@router.get("/rooms", response_model=ChatRoomList, summary="내 채팅방 목록 (최근 대화순)")
def list_rooms(params: Annotated[RoomListParams, Query()], user: CurrentUser, db: DbSession):
    rooms, total = chat_service.list_rooms(db, user, params)
    ids = [r.id for r in rooms]
    lasts = chat_service.last_messages(db, ids)
    unread = chat_service.unread_counts(db, user, ids)
    return ChatRoomList(
        items=[_room_out(r, user, lasts.get(r.id), unread.get(r.id, 0)) for r in rooms],
        total=total,
        page=params.page,
        size=params.size,
        has_next=params.page * params.size < total,
    )


@router.get("/unread-count", response_model=UnreadTotal, summary="안 읽은 메시지 총 개수 (배지용)")
def unread_count(user: CurrentUser, db: DbSession):
    return UnreadTotal(unread_count=chat_service.total_unread(db, user))


@router.get("/rooms/{room_id}", response_model=ChatRoomOut, summary="채팅방 정보")
def get_room(room_id: RoomId, user: CurrentUser, db: DbSession):
    return _single_room_out(db, chat_service.get_room(db, room_id, user), user)


@router.get("/rooms/{room_id}/messages", response_model=MessagePage, summary="메시지 목록 (커서 페이지네이션)")
def list_messages(
    room_id: RoomId, params: Annotated[MessageListParams, Query()], user: CurrentUser, db: DbSession
):
    items, has_more = chat_service.list_messages(db, room_id, user, params)
    return MessagePage(items=[MessageOut.model_validate(m) for m in items], has_more=has_more)


@router.post(
    "/rooms/{room_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="메시지 보내기",
)
def send_message(room_id: RoomId, data: MessageCreate, user: CurrentUser, db: DbSession):
    return chat_service.send_message(db, room_id, user, data.content)


@router.post("/rooms/{room_id}/read", response_model=ReadResult, summary="상대 메시지 모두 읽음 처리")
def mark_read(room_id: RoomId, user: CurrentUser, db: DbSession):
    return ReadResult(marked_read=chat_service.mark_read(db, room_id, user))
