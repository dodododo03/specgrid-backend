"""Seller-side product management: update, status change, soft delete, my listings."""

import pytest
from sqlalchemy import text

from tests.conftest import API, signup_and_login
from tests.test_products import GPU_4080, create


@pytest.fixture
def other_headers(client):
    return signup_and_login(client, email="other@specgrid.kr", nickname="다른사람")


@pytest.fixture
def product(client, auth_headers):
    return create(client, auth_headers)


def patch(client, headers, pid, body, suffix=""):
    return client.patch(f"{API}/products/{pid}{suffix}", json=body, headers=headers)


# ------------------------------------------------------------------ update


def test_partial_update_changes_only_sent_fields(client, auth_headers, product):
    r = patch(client, auth_headers, product["id"], {"price": 1_050_000, "trade_location": None})
    assert r.status_code == 200
    body = r.json()
    assert body["price"] == 1_050_000
    assert body["trade_location"] is None                # explicitly cleared
    assert body["title"] == GPU_4080["title"]            # untouched
    assert body["spec"]["vram_gb"] == 16                 # untouched


def test_spec_fields_merge(client, auth_headers, product):
    r = patch(client, auth_headers, product["id"], {"spec": {"model_name": "RTX 4080 FE 16GB"}})
    spec = r.json()["spec"]
    assert spec["model_name"] == "RTX 4080 FE 16GB"
    assert spec["gpu_model"] == "GeForce RTX 4080" and spec["vram_gb"] == 16  # kept


def test_spec_can_be_removed_and_added_back(client, auth_headers, product):
    assert patch(client, auth_headers, product["id"], {"spec": None}).json()["spec"] is None
    r = patch(client, auth_headers, product["id"], {"spec": {"vram_gb": 12}})
    assert r.json()["spec"]["vram_gb"] == 12 and r.json()["spec"]["gpu_model"] is None


@pytest.mark.parametrize(
    "body",
    [
        {},                                    # nothing to update
        {"title": None},                       # required field cannot be cleared
        {"price": None},
        {"price": -1},
        {"thumbnail_url": "http://insecure.example.com/a.jpg"},
        {"category": "laptop"},                # category is immutable -> ignored -> body is empty
    ],
)
def test_update_validation(client, auth_headers, product, body):
    assert patch(client, auth_headers, product["id"], body).status_code == 422


def test_only_owner_can_update(client, other_headers, product):
    r = patch(client, other_headers, product["id"], {"price": 1})
    assert r.status_code == 403
    assert r.json()["code"] == "forbidden"


def test_update_requires_login(client, product):
    assert client.patch(f"{API}/products/{product['id']}", json={"price": 1}).status_code == 401


def test_update_missing_product(client, auth_headers):
    assert patch(client, auth_headers, 999999999, {"price": 1}).status_code == 404


# ------------------------------------------------------------------ status


def test_status_flow_and_search_visibility(client, auth_headers, product):
    pid = product["id"]

    def in_search(**params):
        return pid in [p["id"] for p in client.get(f"{API}/products", params=params).json()["items"]]

    assert in_search()
    assert patch(client, auth_headers, pid, {"status": "reserved"}, "/status").json()["status"] == "reserved"
    assert not in_search() and in_search(include_sold=True)

    patch(client, auth_headers, pid, {"status": "sold"}, "/status")
    assert not in_search() and in_search(include_sold=True)

    patch(client, auth_headers, pid, {"status": "hidden"}, "/status")
    assert not in_search(include_sold=True)                              # hidden: never public
    assert client.get(f"{API}/products/{pid}").status_code == 404

    patch(client, auth_headers, pid, {"status": "on_sale"}, "/status")  # owner can un-hide
    assert in_search()


def test_status_validation_and_ownership(client, auth_headers, other_headers, product):
    assert patch(client, auth_headers, product["id"], {"status": "deleted"}, "/status").status_code == 422
    assert patch(client, other_headers, product["id"], {"status": "sold"}, "/status").status_code == 403


# ------------------------------------------------------------------ delete


def test_soft_delete(client, auth_headers, other_headers, product, db):
    pid = product["id"]
    assert client.delete(f"{API}/products/{pid}", headers=other_headers).status_code == 403
    assert client.delete(f"{API}/products/{pid}", headers=auth_headers).status_code == 204

    assert client.get(f"{API}/products/{pid}").status_code == 404
    assert client.get(f"{API}/products", params={"include_sold": True}).json()["total"] == 0
    assert client.get(f"{API}/users/me/products", headers=auth_headers).json()["total"] == 0
    assert patch(client, auth_headers, pid, {"price": 1}).status_code == 404
    assert client.delete(f"{API}/products/{pid}", headers=auth_headers).status_code == 404  # already gone

    # Row is kept in the DB (for chat/activity history), only marked deleted.
    assert db.scalar(text("SELECT deleted_at IS NOT NULL FROM products WHERE id = :i"), {"i": pid}) == 1


# ------------------------------------------------------------------ my products


def test_my_products_includes_hidden_and_sold_but_not_others(client, auth_headers, other_headers):
    on_sale = create(client, auth_headers)["id"]
    sold = create(client, auth_headers)["id"]
    hidden = create(client, auth_headers)["id"]
    create(client, other_headers)  # someone else's
    patch(client, auth_headers, sold, {"status": "sold"}, "/status")
    patch(client, auth_headers, hidden, {"status": "hidden"}, "/status")

    mine = client.get(f"{API}/users/me/products", headers=auth_headers).json()
    assert {p["id"] for p in mine["items"]} == {on_sale, sold, hidden}
    assert mine["items"][0]["id"] == hidden  # newest first

    only_sold = client.get(f"{API}/users/me/products", params={"status": "sold"}, headers=auth_headers).json()
    assert [p["id"] for p in only_sold["items"]] == [sold]


def test_my_products_requires_login(client):
    assert client.get(f"{API}/users/me/products").status_code == 401
