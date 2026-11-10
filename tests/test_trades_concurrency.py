"""Real concurrency: many simultaneous HTTP requests with real commits (no shared test transaction).

The other tests run inside one rolled-back transaction, which can't show races between
connections. Here every request gets its own DB session, exactly like production, and the
rows are deleted afterwards.
"""

import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.redis import get_redis
from app.db.session import SessionLocal
from app.main import app
from app.models import Product, Trade, User, UserActivityLog
from tests.conftest import API, signup_and_login
from tests.test_products import GPU_4080

N = 20


@pytest.fixture
def live(redis_client):
    """TestClient with the real per-request DB session (commits for real) + test Redis."""
    app.dependency_overrides[get_redis] = lambda: redis_client
    tag = uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        yield c, tag
    app.dependency_overrides.clear()

    with SessionLocal() as s:  # clean up everything this test created
        user_ids = list(s.scalars(select(User.id).where(User.email.like(f"%{tag}%"))))
        if user_ids:
            s.execute(delete(UserActivityLog).where(UserActivityLog.user_id.in_(user_ids)))
            s.execute(delete(Trade).where(Trade.seller_id.in_(user_ids)))
            s.execute(delete(Product).where(Product.seller_id.in_(user_ids)))
            s.execute(delete(User).where(User.id.in_(user_ids)))
            s.commit()


def _setup(client, tag, buyers):
    seller = signup_and_login(client, email=f"s{tag}@specgrid.kr", nickname=f"s{tag}")
    r = client.post(f"{API}/products", json=GPU_4080, headers=seller)
    assert r.status_code == 201, r.text
    heads = [signup_and_login(client, email=f"b{i}{tag}@specgrid.kr", nickname=f"b{i}{tag}") for i in range(buyers)]
    return seller, r.json()["id"], heads


def _parallel(fn, args):
    with ThreadPoolExecutor(max_workers=N) as pool:
        return list(pool.map(fn, args))


def test_same_buyer_spamming_request_creates_one_trade(live):
    client, tag = live
    _, pid, (buyer,) = _setup(client, tag, 1)

    codes = _parallel(
        lambda _: client.post(f"{API}/trades", json={"product_id": pid}, headers=buyer).status_code, range(N)
    )
    assert Counter(codes) == {201: 1, 409: N - 1}
    with SessionLocal() as s:
        assert len(s.scalars(select(Trade.id).where(Trade.product_id == pid)).all()) == 1


def test_accepting_many_requests_at_once_reserves_for_exactly_one(live):
    client, tag = live
    seller, pid, buyers = _setup(client, tag, 5)
    trade_ids = [
        client.post(f"{API}/trades", json={"product_id": pid}, headers=b).json()["id"] for b in buyers
    ]

    codes = _parallel(
        lambda tid: client.post(f"{API}/trades/{tid}/accept", headers=seller).status_code, trade_ids * 4
    )
    assert codes.count(200) == 1  # one winner; every other attempt is 409
    assert set(codes) == {200, 409}
    with SessionLocal() as s:
        statuses = Counter(s.scalars(select(Trade.status).where(Trade.product_id == pid)))
        assert statuses == {"accepted": 1, "requested": 4}
        assert s.scalar(select(Product.status).where(Product.id == pid)) == "reserved"
