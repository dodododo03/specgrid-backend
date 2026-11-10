import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Path, Query, Response, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketState

from app.api.deps import (
    Activity,
    AuthContext,
    CurrentViewer,
    CurrentUser,
    DbSession,
    RedisClient,
    TokenStoreDep,
    authenticate_access_token,
)
from app.core.config import settings
from app.core.exceptions import AppError, AuthenticationError
from app.models import ChatMessage, ChatRoom, User
from app.models.enums import ActivityType
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
from app.services.chat_events import ChatEvents, redis_db_of, user_channel
from app.services.token_store import TokenStore

router = APIRouter(prefix="/chat", tags=["chat"])

RoomId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def get_chat_events(client: RedisClient) -> ChatEvents:
    return ChatEvents(client)


ChatEventsDep = Annotated[ChatEvents, Depends(get_chat_events)]


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
def open_room(
    data: ChatRoomCreate, user: CurrentUser, db: DbSession, response: Response,
    viewer: CurrentViewer, activity: Activity,
):
    room, created = chat_service.open_room(db, user, data.product_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    if created:
        activity.record(ActivityType.CHAT, viewer, product_id=room.product_id, detail={"room_id": room.id})
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
def send_message(room_id: RoomId, data: MessageCreate, user: CurrentUser, db: DbSession, events: ChatEventsDep):
    message = chat_service.send_message(db, room_id, user, data.content)
    out = MessageOut.model_validate(message)
    room = message.room
    # Both sides: the partner sees it arrive, the sender's other devices stay in sync.
    events.publish(
        [room.buyer_id, room.seller_id],
        {"type": "message", "room_id": room.id, "message": out.model_dump(mode="json")},
    )
    return out


@router.post("/rooms/{room_id}/read", response_model=ReadResult, summary="상대 메시지 모두 읽음 처리")
def mark_read(room_id: RoomId, user: CurrentUser, db: DbSession, events: ChatEventsDep):
    room, marked = chat_service.mark_read(db, room_id, user)
    if marked:
        # Lets the sender flip their messages to "읽음" without refetching.
        events.publish(
            [chat_service.partner_id(room, user.id)],
            {"type": "read", "room_id": room.id, "reader_id": user.id},
        )
    return ReadResult(marked_read=marked)


# ------------------------------------------------------------------ WebSocket

WS_AUTH_TIMEOUT_SECONDS = 10
WS_REVALIDATE_SECONDS = 60.0  # how often an open socket re-checks logout / expiry
CLOSE_AUTH_FAILED = 4401      # application close codes live in 4000-4999
CLOSE_TRY_AGAIN = 1013


@router.websocket("/ws")
async def chat_socket(websocket: WebSocket, db: DbSession, store: TokenStoreDep):
    """Real-time push for the logged-in user's chats (receive only; send via POST .../messages).

    1. connect to ws://<host>/api/v1/chat/ws
    2. within 10 s send {"type": "auth", "token": "<access_token>"}
       (not a query string, so tokens never end up in access logs)
    3. server replies {"type": "ready", "user_id": ...}, then pushes "message" / "read" events
    4. optional keep-alive: send {"type": "ping"} -> {"type": "pong"}
    Closes with 4401 when the token is invalid, expires, or the user logs out.
    """
    await websocket.accept()
    try:
        auth = await _handshake(websocket, db, store)
    finally:
        db.close()  # don't hold a pooled DB connection for the lifetime of the socket
    if auth is None:
        return
    await _relay(websocket, auth, store)


async def _handshake(websocket: WebSocket, db: Session, store: TokenStore) -> AuthContext | None:
    try:
        first = await asyncio.wait_for(websocket.receive_json(), WS_AUTH_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        return None
    except (TimeoutError, ValueError):
        await websocket.close(CLOSE_AUTH_FAILED, "auth message required")
        return None

    token = first.get("token") if isinstance(first, dict) and first.get("type") == "auth" else None
    if not isinstance(token, str) or not token:
        await websocket.close(CLOSE_AUTH_FAILED, "auth message required")
        return None
    try:
        return await run_in_threadpool(authenticate_access_token, db, store, token)
    except AuthenticationError:
        await websocket.close(CLOSE_AUTH_FAILED, "invalid or expired token")
    except AppError:  # Redis down -> can't verify the token (fail closed)
        await websocket.close(CLOSE_TRY_AGAIN, "try again later")
    return None


async def _relay(websocket: WebSocket, auth: AuthContext, store: TokenStore) -> None:
    client = aioredis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3)
    pubsub = client.pubsub()
    try:
        try:
            await pubsub.subscribe(user_channel(redis_db_of(client), auth.user.id))
        except RedisError:
            await websocket.close(CLOSE_TRY_AGAIN, "try again later")
            return
        await websocket.send_json({"type": "ready", "user_id": auth.user.id})

        tasks = [
            asyncio.create_task(_forward_events(websocket, pubsub)),
            asyncio.create_task(_read_client(websocket)),
            asyncio.create_task(_watch_token(auth, store)),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

        close_code = next(iter(done)).result()  # None = client went away
        if close_code is not None and websocket.application_state == WebSocketState.CONNECTED:
            reason = "invalid or expired token" if close_code == CLOSE_AUTH_FAILED else "try again later"
            await websocket.close(close_code, reason)
    finally:
        try:
            await pubsub.aclose()
            await client.aclose()
        except RedisError:
            pass


async def _forward_events(websocket: WebSocket, pubsub) -> int | None:
    try:
        async for item in pubsub.listen():
            if item["type"] == "message":
                await websocket.send_text(item["data"])
    except RedisError:
        return CLOSE_TRY_AGAIN  # client reconnects and catches up with ?after_id=
    except (WebSocketDisconnect, RuntimeError):
        return None
    return CLOSE_TRY_AGAIN


async def _read_client(websocket: WebSocket) -> int | None:
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                msg = None
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json(
                    {"type": "error", "message": "메시지 전송은 POST /api/v1/chat/rooms/{room_id}/messages 를 사용하세요."}
                )
    except (WebSocketDisconnect, RuntimeError):
        return None


async def _watch_token(auth: AuthContext, store: TokenStore) -> int:
    """Close the socket when the access token expires or is revoked (logout / logout-all)."""
    while True:
        left = (auth.claims.expires_at - datetime.now(UTC)).total_seconds()
        if left <= 0:
            return CLOSE_AUTH_FAILED
        await asyncio.sleep(min(WS_REVALIDATE_SECONDS, left))
        if auth.claims.expires_at <= datetime.now(UTC):
            return CLOSE_AUTH_FAILED
        try:
            active = await run_in_threadpool(store.is_access_token_active, auth.claims)
        except AppError:
            return CLOSE_TRY_AGAIN
        if not active:
            return CLOSE_AUTH_FAILED
