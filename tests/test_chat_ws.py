"""Real-time chat: WebSocket auth handshake and Redis Pub/Sub delivery."""

from contextlib import contextmanager

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.v1.endpoints import chat as chat_endpoints
from tests.conftest import API, CONSENT
from tests.test_chat import buyer, product, room, send, stranger  # noqa: F401 — fixtures

WS = f"{API}/chat/ws"


def token_of(headers):
    return headers["Authorization"].removeprefix("Bearer ")


@contextmanager
def connect(client, headers):
    """Open an authenticated socket and wait until the server has subscribed."""
    with client.websocket_connect(WS) as sock:
        sock.send_json({"type": "auth", "token": token_of(headers)})
        ready = sock.receive_json()
        assert ready["type"] == "ready"
        yield sock


def expect_close(sock, code):
    with pytest.raises(WebSocketDisconnect) as exc:
        sock.receive_json()
    assert exc.value.code == code


# ------------------------------------------------------------------ handshake


def test_auth_required(client):
    with client.websocket_connect(WS) as sock:
        sock.send_json({"type": "hello"})
        expect_close(sock, 4401)


def test_invalid_token_rejected(client):
    with client.websocket_connect(WS) as sock:
        sock.send_json({"type": "auth", "token": "not-a-jwt"})
        expect_close(sock, 4401)


def test_refresh_token_rejected(client):
    r = client.post(f"{API}/auth/signup", json={"email": "r@specgrid.kr", "password": "Passw0rd!", "nickname": "리프", **CONSENT})
    tokens = client.post(f"{API}/auth/login", json={"email": "r@specgrid.kr", "password": "Passw0rd!"}).json()
    assert r.status_code == 201
    with client.websocket_connect(WS) as sock:
        sock.send_json({"type": "auth", "token": tokens["refresh_token"]})
        expect_close(sock, 4401)


def test_ready_and_ping(client, buyer):
    with connect(client, buyer) as sock:
        sock.send_json({"type": "ping"})
        assert sock.receive_json() == {"type": "pong"}
        sock.send_json({"type": "message", "content": "hi"})  # sending over WS isn't supported
        assert sock.receive_json()["type"] == "error"


# ------------------------------------------------------------------ delivery


def test_message_pushed_to_both_participants(client, auth_headers, buyer, room):
    with connect(client, auth_headers) as seller_sock, connect(client, buyer) as buyer_sock:
        sent = send(client, buyer, room["id"], "실시간 테스트")

        event = seller_sock.receive_json()
        assert event["type"] == "message" and event["room_id"] == room["id"]
        assert event["message"]["id"] == sent["id"] and event["message"]["content"] == "실시간 테스트"
        assert event["message"]["created_at"].endswith("Z")

        echo = buyer_sock.receive_json()  # sender's own devices stay in sync too
        assert echo["message"]["id"] == sent["id"]


def test_read_event_goes_to_sender(client, auth_headers, buyer, room):
    send(client, buyer, room["id"], "읽어주세요")
    with connect(client, buyer) as buyer_sock:
        client.post(f"{API}/chat/rooms/{room['id']}/read", headers=auth_headers)
        event = buyer_sock.receive_json()
        assert event["type"] == "read" and event["room_id"] == room["id"]
        assert event["reader_id"] == room["partner"]["id"]  # the buyer's partner (seller) read it


def test_stranger_receives_nothing(client, buyer, stranger, room):
    with connect(client, stranger) as sock:
        send(client, buyer, room["id"], "비밀 메시지")
        sock.send_json({"type": "ping"})
        assert sock.receive_json() == {"type": "pong"}  # the chat message never arrived first


# ------------------------------------------------------------------ token lifetime


def test_socket_closed_after_logout(client, buyer, monkeypatch):
    monkeypatch.setattr(chat_endpoints, "WS_REVALIDATE_SECONDS", 0.05)
    with connect(client, buyer) as sock:
        assert client.post(f"{API}/auth/logout", json={}, headers=buyer).status_code in (200, 204)
        expect_close(sock, 4401)
