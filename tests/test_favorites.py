"""찜: add/remove (idempotent), counters, heart state on product responses, my list, ranking."""

from sqlalchemy import select

from app.models import Product, UserActivityLog
from app.models.enums import ActivityType
from tests.conftest import API, signup_and_login
from tests.test_chat import buyer, product, stranger  # noqa: F401 — fixtures
from tests.test_products import create


def heart(client, headers, pid, expected=200):
    r = client.put(f"{API}/products/{pid}/favorite", headers=headers)
    assert r.status_code == expected, r.text
    return r.json()


def unheart(client, headers, pid, expected=200):
    r = client.delete(f"{API}/products/{pid}/favorite", headers=headers)
    assert r.status_code == expected, r.text
    return r.json()


def my_favorites(client, headers, **params):
    r = client.get(f"{API}/users/me/favorites", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ add / remove


def test_add_and_remove(client, buyer, product):
    assert heart(client, buyer, product["id"]) == {"product_id": product["id"], "favorited": True, "favorite_count": 1}
    assert unheart(client, buyer, product["id"]) == {"product_id": product["id"], "favorited": False, "favorite_count": 0}


def test_idempotent(client, buyer, product):
    heart(client, buyer, product["id"])
    assert heart(client, buyer, product["id"])["favorite_count"] == 1  # double tap: still 1
    unheart(client, buyer, product["id"])
    assert unheart(client, buyer, product["id"])["favorite_count"] == 0  # never negative


def test_count_across_users(client, buyer, stranger, product):
    heart(client, buyer, product["id"])
    assert heart(client, stranger, product["id"])["favorite_count"] == 2
    assert unheart(client, buyer, product["id"])["favorite_count"] == 1


def test_requires_login(client, product):
    assert client.put(f"{API}/products/{product['id']}/favorite").status_code == 401
    assert client.get(f"{API}/users/me/favorites").status_code == 401


def test_cannot_heart_own_missing_hidden_or_sold(client, auth_headers, buyer, product):
    heart(client, auth_headers, product["id"], expected=400)
    heart(client, buyer, 999999999, expected=404)
    hidden = create(client, auth_headers)
    client.patch(f"{API}/products/{hidden['id']}/status", json={"status": "hidden"}, headers=auth_headers)
    heart(client, buyer, hidden["id"], expected=404)
    sold = create(client, auth_headers)
    client.patch(f"{API}/products/{sold['id']}/status", json={"status": "sold"}, headers=auth_headers)
    heart(client, buyer, sold["id"], expected=409)


def test_can_unheart_after_product_sold(client, auth_headers, buyer, product):
    heart(client, buyer, product["id"])
    client.patch(f"{API}/products/{product['id']}/status", json={"status": "sold"}, headers=auth_headers)
    assert unheart(client, buyer, product["id"])["favorite_count"] == 0
    unheart(client, buyer, 999999999, expected=404)


def test_counter_matches_rows(client, db, buyer, stranger, product):
    heart(client, buyer, product["id"])
    heart(client, stranger, product["id"])
    unheart(client, stranger, product["id"])
    heart(client, buyer, product["id"])
    assert db.scalar(select(Product.favorite_count).where(Product.id == product["id"])) == 1


def test_activity_logged(client, db, buyer, product):
    heart(client, buyer, product["id"])
    heart(client, buyer, product["id"])  # no-op, not logged
    unheart(client, buyer, product["id"])
    rows = db.scalars(
        select(UserActivityLog).where(UserActivityLog.activity_type == ActivityType.FAVORITE).order_by(UserActivityLog.id)
    ).all()
    assert [r.detail["action"] for r in rows][-2:] == ["add", "remove"]


# ------------------------------------------------------------------ heart state on product responses


def test_is_favorited_on_detail_and_search(client, auth_headers, buyer, stranger, product):
    other = create(client, auth_headers, title="다른 상품")
    heart(client, buyer, product["id"])

    def detail(headers=None):
        return client.get(f"{API}/products/{product['id']}", headers=headers or {}).json()

    assert detail(buyer)["is_favorited"] is True and detail(buyer)["favorite_count"] == 1
    assert detail(stranger)["is_favorited"] is False
    assert detail()["is_favorited"] is None  # anonymous: unknown, not "false"

    items = client.get(f"{API}/products", headers=buyer).json()["items"]
    state = {i["id"]: i["is_favorited"] for i in items}
    assert state[product["id"]] is True and state[other["id"]] is False


# ------------------------------------------------------------------ my list


def test_my_favorites_newest_first(client, auth_headers, buyer):
    first = create(client, auth_headers, title="첫 번째")
    second = create(client, auth_headers, title="두 번째")
    heart(client, buyer, first["id"])
    heart(client, buyer, second["id"])
    page = my_favorites(client, buyer)
    assert page["total"] == 2
    assert [i["id"] for i in page["items"]] == [second["id"], first["id"]]
    assert all(i["is_favorited"] is True for i in page["items"])
    assert my_favorites(client, buyer, size=1)["has_next"] is True


def test_my_favorites_hide_deleted_and_hidden_keep_sold(client, auth_headers, buyer):
    ids = [create(client, auth_headers, title=f"상품{i}")["id"] for i in range(3)]
    for pid in ids:
        heart(client, buyer, pid)
    client.delete(f"{API}/products/{ids[0]}", headers=auth_headers)
    client.patch(f"{API}/products/{ids[1]}/status", json={"status": "hidden"}, headers=auth_headers)
    client.patch(f"{API}/products/{ids[2]}/status", json={"status": "sold"}, headers=auth_headers)
    items = my_favorites(client, buyer)["items"]
    assert [(i["id"], i["status"]) for i in items] == [(ids[2], "sold")]


def test_my_favorites_only_mine(client, buyer, stranger, product):
    heart(client, buyer, product["id"])
    assert my_favorites(client, stranger)["total"] == 0


# ------------------------------------------------------------------ ranking


def test_most_favorited_ranking(client, auth_headers, buyer, stranger):
    a = create(client, auth_headers, title="인기 상품")["id"]
    b = create(client, auth_headers, title="보통 상품")["id"]
    third = signup_and_login(client, email="third@specgrid.kr", nickname="세번째")
    for who in (buyer, stranger, third):
        heart(client, who, a)
    heart(client, buyer, b)

    for period in ("week", "all"):
        r = client.get(f"{API}/rankings/products", params={"metric": "favorites", "period": period})
        assert r.status_code == 200
        assert [(i["product"]["id"], i["count"]) for i in r.json()["items"]] == [(a, 3), (b, 1)]
        assert r.json()["metric"] == "favorites"
