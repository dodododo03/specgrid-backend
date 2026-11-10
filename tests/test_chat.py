"""1:1 chat: opening rooms, sending/paging messages, read receipts, access control."""

from datetime import datetime

import pytest
from sqlalchemy import update

from app.models import ChatRoom, User
from app.models.enums import UserStatus
from tests.conftest import API, signup_and_login
from tests.test_products import create


@pytest.fixture
def buyer(client):
    return signup_and_login(client, email="buyer@specgrid.kr", nickname="구매자1")


@pytest.fixture
def stranger(client):
    return signup_and_login(client, email="stranger@specgrid.kr", nickname="제3자")


@pytest.fixture
def product(client, auth_headers):
    return create(client, auth_headers)


@pytest.fixture
def room(client, buyer, product):
    r = client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}, headers=buyer)
    assert r.status_code == 201, r.text
    return r.json()


def send(client, headers, room_id, content):
    r = client.post(f"{API}/chat/rooms/{room_id}/messages", json={"content": content}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def messages(client, headers, room_id, **params):
    r = client.get(f"{API}/chat/rooms/{room_id}/messages", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ rooms


def test_open_room(room, product):
    assert room["product"]["id"] == product["id"]
    assert room["product"]["title"] == product["title"] and room["product"]["is_deleted"] is False
    assert room["my_role"] == "buyer"
    assert room["partner"]["nickname"] == "판매자1"
    assert "email" not in room["partner"]
    assert room["last_message"] is None and room["unread_count"] == 0


def test_open_room_twice_returns_same_room(client, buyer, product, room):
    r = client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}, headers=buyer)
    assert r.status_code == 200
    assert r.json()["id"] == room["id"]


def test_cannot_chat_on_own_product(client, auth_headers, product):
    r = client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}, headers=auth_headers)
    assert r.status_code == 400


def test_cannot_open_room_for_sold_hidden_or_deleted(client, auth_headers, buyer, product):
    pid = product["id"]
    client.patch(f"{API}/products/{pid}/status", json={"status": "sold"}, headers=auth_headers)
    assert client.post(f"{API}/chat/rooms", json={"product_id": pid}, headers=buyer).status_code == 409

    client.patch(f"{API}/products/{pid}/status", json={"status": "hidden"}, headers=auth_headers)
    assert client.post(f"{API}/chat/rooms", json={"product_id": pid}, headers=buyer).status_code == 404

    other = create(client, auth_headers)
    client.delete(f"{API}/products/{other['id']}", headers=auth_headers)
    assert client.post(f"{API}/chat/rooms", json={"product_id": other["id"]}, headers=buyer).status_code == 404


def test_open_room_requires_login(client, product):
    assert client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}).status_code == 401


def test_seller_sees_room_as_seller(client, auth_headers, room):
    r = client.get(f"{API}/chat/rooms/{room['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["my_role"] == "seller" and r.json()["partner"]["nickname"] == "구매자1"


def test_stranger_cannot_see_room(client, stranger, room):
    rid = room["id"]
    assert client.get(f"{API}/chat/rooms/{rid}", headers=stranger).status_code == 404
    assert client.get(f"{API}/chat/rooms/{rid}/messages", headers=stranger).status_code == 404
    r = client.post(f"{API}/chat/rooms/{rid}/messages", json={"content": "hi"}, headers=stranger)
    assert r.status_code == 404
    assert client.post(f"{API}/chat/rooms/{rid}/read", headers=stranger).status_code == 404


def test_existing_room_survives_product_deletion(client, auth_headers, buyer, product, room):
    client.delete(f"{API}/products/{product['id']}", headers=auth_headers)
    r = client.get(f"{API}/chat/rooms/{room['id']}", headers=buyer)
    assert r.status_code == 200 and r.json()["product"]["is_deleted"] is True
    send(client, buyer, room["id"], "아직 거래 가능하신가요?")


# ------------------------------------------------------------------ messages


def test_send_and_list_messages(client, auth_headers, buyer, room):
    rid = room["id"]
    m1 = send(client, buyer, rid, "  안녕하세요, 구매 가능할까요?  ")
    m2 = send(client, auth_headers, rid, "네 가능합니다")
    assert m1["content"] == "안녕하세요, 구매 가능할까요?"  # trimmed
    assert m1["message_type"] == "text" and m1["is_read"] is False

    page = messages(client, buyer, rid)
    assert [m["id"] for m in page["items"]] == [m1["id"], m2["id"]]  # oldest first
    assert page["has_more"] is False


@pytest.mark.parametrize("content", ["", "   ", "x" * 1001])
def test_message_validation(client, buyer, room, content):
    r = client.post(f"{API}/chat/rooms/{room['id']}/messages", json={"content": content}, headers=buyer)
    assert r.status_code == 422


def test_cursor_pagination(client, buyer, room):
    rid = room["id"]
    ids = [send(client, buyer, rid, f"메시지 {i}")["id"] for i in range(7)]

    newest = messages(client, buyer, rid, limit=3)
    assert [m["id"] for m in newest["items"]] == ids[4:] and newest["has_more"] is True

    older = messages(client, buyer, rid, limit=3, before_id=ids[4])
    assert [m["id"] for m in older["items"]] == ids[1:4] and older["has_more"] is True

    oldest = messages(client, buyer, rid, limit=3, before_id=ids[1])
    assert [m["id"] for m in oldest["items"]] == ids[:1] and oldest["has_more"] is False

    new = messages(client, buyer, rid, limit=3, after_id=ids[2])
    assert [m["id"] for m in new["items"]] == ids[3:6] and new["has_more"] is True
    assert messages(client, buyer, rid, after_id=ids[-1])["items"] == []


def test_before_and_after_together_rejected(client, buyer, room):
    r = client.get(f"{API}/chat/rooms/{room['id']}/messages", params={"before_id": 5, "after_id": 1},
                   headers=buyer)
    assert r.status_code == 400


def test_cannot_message_inactive_user(client, db, buyer, room):
    db.execute(update(User).where(User.nickname == "판매자1").values(status=UserStatus.WITHDRAWN))
    r = client.post(f"{API}/chat/rooms/{room['id']}/messages", json={"content": "hi"}, headers=buyer)
    assert r.status_code == 409


# ------------------------------------------------------------------ read / unread


def unread_total(client, headers):
    r = client.get(f"{API}/chat/unread-count", headers=headers)
    assert r.status_code == 200
    return r.json()["unread_count"]


def test_unread_and_mark_read(client, auth_headers, buyer, room):
    rid = room["id"]
    send(client, buyer, rid, "첫 번째")
    send(client, buyer, rid, "두 번째")
    send(client, auth_headers, rid, "판매자 답장")

    assert unread_total(client, auth_headers) == 2   # seller hasn't read the buyer's two messages
    assert unread_total(client, buyer) == 1
    assert client.get(f"{API}/chat/rooms/{rid}", headers=auth_headers).json()["unread_count"] == 2

    r = client.post(f"{API}/chat/rooms/{rid}/read", headers=auth_headers)
    assert r.status_code == 200 and r.json()["marked_read"] == 2
    assert unread_total(client, auth_headers) == 0
    assert unread_total(client, buyer) == 1          # reading doesn't touch the other side
    assert client.post(f"{API}/chat/rooms/{rid}/read", headers=auth_headers).json()["marked_read"] == 0

    items = messages(client, buyer, rid)["items"]
    assert [m["is_read"] for m in items] == [True, True, False]  # buyer sees "읽음" on own messages


# ------------------------------------------------------------------ inbox


def test_room_list_sorted_by_latest_message(client, db, auth_headers, buyer, stranger, product, room):
    other_product = create(client, auth_headers, title="RTX 3070 팝니다")
    r2 = client.post(f"{API}/chat/rooms", json={"product_id": other_product["id"]}, headers=stranger).json()

    send(client, buyer, room["id"], "4080 네고 되나요?")
    send(client, stranger, r2["id"], "3070 사고 싶어요")
    # Both messages land in the same second; push the first room's conversation clearly into the past.
    db.execute(update(ChatRoom).where(ChatRoom.id == room["id"])
               .values(last_message_at=datetime(2026, 1, 1)))

    r = client.get(f"{API}/chat/rooms", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and body["has_next"] is False
    assert [i["id"] for i in body["items"]] == [r2["id"], room["id"]]  # most recent conversation first
    first, second = body["items"]
    assert first["last_message"]["content"] == "3070 사고 싶어요" and first["partner"]["nickname"] == "제3자"
    assert second["last_message"]["content"] == "4080 네고 되나요?" and second["unread_count"] == 1

    # Each participant only sees their own rooms.
    assert [i["id"] for i in client.get(f"{API}/chat/rooms", headers=buyer).json()["items"]] == [room["id"]]
    assert unread_total(client, auth_headers) == 2
