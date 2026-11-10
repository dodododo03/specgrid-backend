"""Real-time chat events over Redis Pub/Sub.

Every WebSocket connection subscribes to its user's channel; the REST endpoints publish to it
after the DB commit. Because delivery goes through Redis, it works no matter which server
process (uvicorn worker / machine) holds the recipient's socket.

Delivery is best-effort: the DB is the source of truth. If Redis is down the message is still
saved, and clients catch up with GET /chat/rooms/{id}/messages?after_id=<last id they have>.

Events (JSON):
  {"type": "message", "room_id": 5, "message": {...MessageOut...}}   -> both participants
  {"type": "read", "room_id": 5, "reader_id": 9}                     -> the other participant
"""

import json
import logging
from collections.abc import Iterable
from typing import Any

import redis

logger = logging.getLogger(__name__)


def user_channel(redis_db: int, user_id: int) -> str:
    # Pub/Sub channels are server-wide (not per Redis db), so the db number is part of the name:
    # the test suite (db 15) can never deliver events to sockets of the dev server (db 0).
    return f"specgrid:{redis_db}:chat:user:{user_id}"


def redis_db_of(client: Any) -> int:
    return int(client.connection_pool.connection_kwargs.get("db", 0))


class ChatEvents:
    def __init__(self, client: redis.Redis) -> None:
        self.r = client
        self.db = redis_db_of(client)

    def publish(self, user_ids: Iterable[int], event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        try:
            pipe = self.r.pipeline(transaction=False)
            for user_id in set(user_ids):
                pipe.publish(user_channel(self.db, user_id), payload)
            pipe.execute()
        except redis.RedisError:
            logger.warning("chat event not delivered (Redis unavailable): %s", event.get("type"), exc_info=True)
