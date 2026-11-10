"""Purchase flow: request -> accept/reject -> complete/cancel, product status sync, locking."""

import threading
import time

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Trade
from app.models.enums import TradeStatus
from app.services import product_lock
from app.services.product_lock import ProductLock, lock_key
from tests.conftest import API, signup_and_login
from tests.test_chat import buyer, product, stranger  # noqa: F401 — fixtures
from tests.test_products import create


@pytest.fixture
def buyer2(client):
    return signup_and_login(client, email="buyer2@specgrid.kr", nickname="구매자2")


def request(client, headers, product_id, **extra):
    r = client.post(f"{API}/trades", json={"product_id": product_id, **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def act(client, headers, trade_id, action, expected=200):
    r = client.post(f"{API}/trades/{trade_id}/{action}", headers=headers)
    assert r.status_code == expected, r.text
    return r.json()


def product_status(client, product_id):
    r = client.get(f"{API}/products/{product_id}")
    return r.json()["status"] if r.status_code == 200 else None


@pytest.fixture
def trade(client, buyer, product):
    return request(client, buyer, product["id"], message="  오늘 저녁 직거래 가능할까요?  ")


# ------------------------------------------------------------------ 1. request


def test_request(trade, product):
    assert trade["status"] == "requested"
    assert trade["price"] == product["price"]
    assert trade["message"] == "오늘 저녁 직거래 가능할까요?"  # trimmed
    assert trade["buyer"]["nickname"] == "구매자1" and trade["seller"]["nickname"] == "판매자1"
    assert trade["product"]["id"] == product["id"]
    assert trade["responded_at"] is None and trade["created_at"].endswith("Z")


def test_request_requires_login(client, product):
    assert client.post(f"{API}/trades", json={"product_id": product["id"]}).status_code == 401


def test_cannot_request_own_product(client, auth_headers, product):
    r = client.post(f"{API}/trades", json={"product_id": product["id"]}, headers=auth_headers)
    assert r.status_code == 400


def test_duplicate_open_request_rejected(client, buyer, product, trade):
    r = client.post(f"{API}/trades", json={"product_id": product["id"]}, headers=buyer)
    assert r.status_code == 409


def test_can_request_again_after_cancel(client, buyer, product, trade):
    act(client, buyer, trade["id"], "cancel")
    again = request(client, buyer, product["id"])
    assert again["id"] != trade["id"]


def test_many_buyers_can_request_same_product(client, buyer, buyer2, product, trade):
    other = request(client, buyer2, product["id"])
    assert other["status"] == "requested"
    assert product_status(client, product["id"]) == "on_sale"  # requests alone don't reserve


def test_cannot_request_reserved_sold_hidden_or_missing(client, auth_headers, buyer, product):
    pid = product["id"]
    for status_, code in [("reserved", 409), ("sold", 409), ("hidden", 404)]:
        client.patch(f"{API}/products/{pid}/status", json={"status": status_}, headers=auth_headers)
        assert client.post(f"{API}/trades", json={"product_id": pid}, headers=buyer).status_code == code
    assert client.post(f"{API}/trades", json={"product_id": 999999999}, headers=buyer).status_code == 404


def test_message_too_long(client, buyer, product):
    r = client.post(f"{API}/trades", json={"product_id": product["id"], "message": "x" * 201}, headers=buyer)
    assert r.status_code == 422


def test_price_is_snapshot(client, auth_headers, buyer, product, trade):
    client.patch(f"{API}/products/{product['id']}", json={"price": 1}, headers=auth_headers)
    r = client.get(f"{API}/trades/{trade['id']}", headers=buyer)
    assert r.json()["price"] == product["price"]


# ------------------------------------------------------------------ 2. accept / reject


def test_accept_reserves_product(client, auth_headers, product, trade):
    accepted = act(client, auth_headers, trade["id"], "accept")
    assert accepted["status"] == "accepted" and accepted["responded_at"] is not None
    assert product_status(client, product["id"]) == "reserved"


def test_only_seller_can_accept_reject_complete(client, buyer, trade):
    for action in ("accept", "reject", "complete"):
        act(client, buyer, trade["id"], action, expected=403)


def test_stranger_sees_nothing(client, stranger, trade):
    assert client.get(f"{API}/trades/{trade['id']}", headers=stranger).status_code == 404
    for action in ("accept", "reject", "complete", "cancel"):
        act(client, stranger, trade["id"], action, expected=404)


def test_only_one_request_can_be_accepted(client, auth_headers, buyer2, product, trade):
    other = request(client, buyer2, product["id"])
    act(client, auth_headers, trade["id"], "accept")
    act(client, auth_headers, other["id"], "accept", expected=409)  # product already reserved
    assert client.get(f"{API}/trades/{other['id']}", headers=buyer2).json()["status"] == "requested"


def test_reject(client, auth_headers, buyer, product, trade):
    rejected = act(client, auth_headers, trade["id"], "reject")
    assert rejected["status"] == "rejected"
    assert product_status(client, product["id"]) == "on_sale"
    act(client, auth_headers, trade["id"], "accept", expected=409)  # final state
    request(client, buyer, product["id"])  # rejected buyer may ask again


# ------------------------------------------------------------------ 3. complete


def test_complete_sells_and_rejects_others(client, auth_headers, buyer2, product, trade):
    other = request(client, buyer2, product["id"])
    act(client, auth_headers, trade["id"], "accept")
    done = act(client, auth_headers, trade["id"], "complete")
    assert done["status"] == "completed" and done["completed_at"] is not None
    assert product_status(client, product["id"]) == "sold"
    assert client.get(f"{API}/trades/{other['id']}", headers=buyer2).json()["status"] == "rejected"


def test_cannot_complete_before_accept(client, auth_headers, trade):
    act(client, auth_headers, trade["id"], "complete", expected=409)


def test_completed_trade_is_final(client, auth_headers, buyer, trade):
    act(client, auth_headers, trade["id"], "accept")
    act(client, auth_headers, trade["id"], "complete")
    act(client, buyer, trade["id"], "cancel", expected=409)
    act(client, auth_headers, trade["id"], "cancel", expected=409)


# ------------------------------------------------------------------ cancel


def test_buyer_cancels_pending(client, buyer, product, trade):
    assert act(client, buyer, trade["id"], "cancel")["status"] == "canceled"
    assert product_status(client, product["id"]) == "on_sale"


def test_cancel_accepted_puts_product_back_on_sale(client, auth_headers, buyer, buyer2, product):
    for canceller in ("buyer", "seller"):
        t = request(client, buyer, product["id"])
        act(client, auth_headers, t["id"], "accept")
        assert product_status(client, product["id"]) == "reserved"
        act(client, buyer if canceller == "buyer" else auth_headers, t["id"], "cancel")
        assert product_status(client, product["id"]) == "on_sale"

    # ...and the seller can now accept someone else
    other = request(client, buyer2, product["id"])
    act(client, auth_headers, other["id"], "accept")


def test_seller_rejects_pending_instead_of_cancel(client, auth_headers, trade):
    act(client, auth_headers, trade["id"], "cancel", expected=409)


# ------------------------------------------------------------------ product status stays in sync


def test_manual_status_change_blocked_while_reserved(client, auth_headers, product, trade):
    pid = product["id"]
    act(client, auth_headers, trade["id"], "accept")
    for s in ("on_sale", "sold", "hidden"):
        r = client.patch(f"{API}/products/{pid}/status", json={"status": s}, headers=auth_headers)
        assert r.status_code == 409
    assert client.delete(f"{API}/products/{pid}", headers=auth_headers).status_code == 409


def test_deleting_product_rejects_pending_requests(client, auth_headers, buyer, product, trade):
    assert client.delete(f"{API}/products/{product['id']}", headers=auth_headers).status_code == 204
    t = client.get(f"{API}/trades/{trade['id']}", headers=buyer).json()
    assert t["status"] == "rejected" and t["product"]["is_deleted"] is True


# ------------------------------------------------------------------ listing


def test_list_by_role_and_status(client, auth_headers, buyer, product, trade):
    mine = client.get(f"{API}/trades", params={"role": "buyer"}, headers=buyer).json()
    assert [t["id"] for t in mine["items"]] == [trade["id"]] and mine["total"] == 1

    incoming = client.get(f"{API}/trades", params={"role": "seller", "status": "requested"}, headers=auth_headers)
    assert [t["id"] for t in incoming.json()["items"]] == [trade["id"]]

    assert client.get(f"{API}/trades", params={"role": "buyer"}, headers=auth_headers).json()["total"] == 0
    other_product = create(client, auth_headers)
    r = client.get(f"{API}/trades", params={"product_id": other_product["id"]}, headers=auth_headers)
    assert r.json()["total"] == 0


# ------------------------------------------------------------------ concurrency guards


def test_busy_lock_returns_409(client, buyer, product, redis_client, monkeypatch):
    monkeypatch.setattr(product_lock, "LOCK_WAIT_SECONDS", 0.2)
    redis_client.set(lock_key(product["id"]), "someone-else", px=5000)  # another request holds it
    r = client.post(f"{API}/trades", json={"product_id": product["id"]}, headers=buyer)
    assert r.status_code == 409 and "잠시 후" in r.json()["message"]


def test_lock_released_after_request(client, buyer, product, redis_client, trade):
    assert redis_client.exists(lock_key(product["id"])) == 0


def test_product_lock_is_mutually_exclusive(redis_client):
    """20 threads fight for one product: never more than one inside the lock at a time."""
    locks = ProductLock(redis_client)
    inside = 0
    max_inside = 0
    guard = threading.Lock()
    errors: list[Exception] = []

    def worker():
        nonlocal inside, max_inside
        try:
            with locks.hold(424242):
                with guard:
                    inside += 1
                    max_inside = max(max_inside, inside)
                time.sleep(0.01)
                with guard:
                    inside -= 1
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and max_inside == 1


def test_db_unique_index_blocks_second_accepted_trade(client, db, auth_headers, buyer, buyer2, product, trade):
    """Last line of defense: even bypassing the service, MariaDB refuses two accepted trades."""
    other = request(client, buyer2, product["id"])
    act(client, auth_headers, trade["id"], "accept")
    row = db.get(Trade, other["id"])
    row.status = TradeStatus.ACCEPTED
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_db_unique_index_blocks_duplicate_open_request(client, db, buyer, product, trade):
    first = db.get(Trade, trade["id"])
    db.add(Trade(product_id=first.product_id, buyer_id=first.buyer_id, seller_id=first.seller_id,
                 price=first.price, status=TradeStatus.REQUESTED))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
