"""Trade location map pin (trade_point) and the public client config used to load Kakao Maps."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import settings
from tests.conftest import API
from tests.test_products import create

GANGNAM = {"lat": 37.497952, "lng": 127.027619}
YONGSAN = {"lat": 37.529849, "lng": 126.964561}


def patch(client, headers, pid, body):
    return client.patch(f"{API}/products/{pid}", json=body, headers=headers)


# ------------------------------------------------------------------ create


def test_create_with_point_shows_in_detail(client, auth_headers):
    product = create(client, auth_headers, trade_location="강남역 11번 출구", trade_point=GANGNAM)
    assert product["trade_point"] == GANGNAM

    public = client.get(f"{API}/products/{product['id']}").json()
    assert public["trade_location"] == "강남역 11번 출구"
    assert public["trade_point"] == GANGNAM


def test_point_is_optional(client, auth_headers):
    assert create(client, auth_headers)["trade_point"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"trade_location": None, "trade_point": GANGNAM},        # pin without a place name
        {"trade_point": {"lat": 37.5}},                            # half a pin
        {"trade_point": {"lat": 40.7128, "lng": -74.0060}},        # New York: outside Korea
        {"trade_point": {"lat": 37.5, "lng": 200}},
        {"trade_point": {"lat": "abc", "lng": 127}},
    ],
)
def test_create_rejects_bad_points(client, auth_headers, overrides):
    from tests.test_products import GPU_4080

    r = client.post(f"{API}/products", json={**GPU_4080, **overrides}, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_list_items_stay_lean(client, auth_headers):
    create(client, auth_headers, trade_point=GANGNAM)
    item = client.get(f"{API}/products").json()["items"][0]
    assert "trade_point" not in item  # coordinates are only needed on the detail page


# ------------------------------------------------------------------ update


@pytest.fixture
def pinned(client, auth_headers):
    return create(client, auth_headers, trade_location="강남역", trade_point=GANGNAM)


def test_move_pin_with_new_place(client, auth_headers, pinned):
    r = patch(client, auth_headers, pinned["id"], {"trade_location": "용산역", "trade_point": YONGSAN})
    assert r.status_code == 200
    assert r.json()["trade_location"] == "용산역" and r.json()["trade_point"] == YONGSAN


def test_changing_place_name_without_pin_drops_old_pin(client, auth_headers, pinned):
    body = patch(client, auth_headers, pinned["id"], {"trade_location": "용산역"}).json()
    assert body["trade_location"] == "용산역" and body["trade_point"] is None


def test_clearing_place_clears_pin(client, auth_headers, pinned):
    body = patch(client, auth_headers, pinned["id"], {"trade_location": None}).json()
    assert body["trade_location"] is None and body["trade_point"] is None


def test_unrelated_update_keeps_pin(client, auth_headers, pinned):
    body = patch(client, auth_headers, pinned["id"], {"price": 999_000}).json()
    assert body["trade_point"] == GANGNAM


def test_resending_same_place_name_keeps_pin(client, auth_headers, pinned):
    body = patch(client, auth_headers, pinned["id"], {"trade_location": "강남역", "price": 1}).json()
    assert body["trade_point"] == GANGNAM


def test_remove_only_the_pin(client, auth_headers, pinned):
    body = patch(client, auth_headers, pinned["id"], {"trade_point": None}).json()
    assert body["trade_location"] == "강남역" and body["trade_point"] is None


def test_pin_update_requires_place_name(client, auth_headers, pinned):
    assert patch(client, auth_headers, pinned["id"], {"trade_point": YONGSAN}).status_code == 422


def test_db_rejects_half_a_pin(db, client, auth_headers, pinned):
    with pytest.raises((IntegrityError, OperationalError)):
        db.execute(text("UPDATE products SET trade_lng = NULL WHERE id = :id"), {"id": pinned["id"]})
    db.rollback()


# ------------------------------------------------------------------ client config


def test_client_config_exposes_kakao_key(client, monkeypatch):
    monkeypatch.setattr(settings, "kakao_js_key", "test-js-key")
    assert client.get(f"{API}/client-config").json() == {"kakao_js_key": "test-js-key"}


def test_client_config_without_key(client, monkeypatch):
    monkeypatch.setattr(settings, "kakao_js_key", "")
    assert client.get(f"{API}/client-config").json() == {"kakao_js_key": None}
