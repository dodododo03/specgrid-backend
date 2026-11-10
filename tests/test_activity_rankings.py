"""Activity logging (what gets recorded, dedupe, privacy) and the rankings built on it."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import UserActivityLog
from app.models.enums import ActivityType
from app.services.activity_service import normalize_keyword
from tests.conftest import API
from tests.test_chat import buyer, product  # noqa: F401 — fixtures
from tests.test_products import create, visit


def logs(db, activity: ActivityType):
    return db.scalars(
        select(UserActivityLog).where(UserActivityLog.activity_type == activity).order_by(UserActivityLog.id)
    ).all()


def search(client, q, who="browser-1", **params):
    r = client.get(f"{API}/products", params={"q": q, **params}, headers={"User-Agent": who})
    assert r.status_code == 200, r.text
    return r.json()


def keywords(client, **params):
    r = client.get(f"{API}/rankings/keywords", params=params)
    assert r.status_code == 200, r.text
    return [(i["keyword"], i["count"]) for i in r.json()["items"]]


def product_ranking(client, **params):
    r = client.get(f"{API}/rankings/products", params=params)
    assert r.status_code == 200, r.text
    return [(i["product"]["id"], i["views"]) for i in r.json()["items"]]


# ------------------------------------------------------------------ logging


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("  RTX   4080 ", "rtx 4080"), ("Ryzen 7", "ryzen 7"), ("   ", None), ("", None), ("x" * 150, "x" * 100)],
)
def test_normalize_keyword(raw, expected):
    assert normalize_keyword(raw) == expected


def test_view_is_logged_with_viewer_info(client, db, buyer, product):
    client.get(f"{API}/products/{product['id']}", headers={**buyer, "User-Agent": "TestBrowser/1.0"})
    (row,) = logs(db, ActivityType.VIEW)
    assert row.product_id == product["id"] and row.user_id is not None
    assert row.user_agent == "TestBrowser/1.0" and row.ip_address


def test_anonymous_view_is_logged_without_user(client, db, product):
    visit(client, product["id"])
    (row,) = logs(db, ActivityType.VIEW)
    assert row.user_id is None


def test_search_logged_normalized_and_deduped(client, db, product):
    search(client, "  RTX   4080 ")
    search(client, "rtx 4080")            # same person, same keyword -> not counted again
    search(client, "rtx 4080", page=2)   # paging isn't a new search
    search(client, "rtx 4080", who="someone-else")
    rows = logs(db, ActivityType.SEARCH)
    assert [r.search_keyword for r in rows] == ["rtx 4080", "rtx 4080"]
    assert "total" in rows[0].detail  # result count is kept for "searches with no results" analysis


def test_filter_only_search_is_not_logged(client, db):
    client.get(f"{API}/products", params={"category": "gpu"})
    assert logs(db, ActivityType.SEARCH) == []


def test_chat_and_trade_logged_without_content(client, db, auth_headers, buyer, product):
    room = client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}, headers=buyer).json()
    client.post(f"{API}/chat/rooms/{room['id']}/messages", json={"content": "비밀 내용"}, headers=buyer)
    trade = client.post(f"{API}/trades", json={"product_id": product["id"]}, headers=buyer).json()
    client.post(f"{API}/trades/{trade['id']}/accept", headers=auth_headers)

    (chat,) = logs(db, ActivityType.CHAT)
    assert chat.detail == {"room_id": room["id"]} and chat.product_id == product["id"]
    assert [t.detail["action"] for t in logs(db, ActivityType.TRADE)] == ["request", "accept"]
    assert all("비밀" not in str(r.detail) for r in db.scalars(select(UserActivityLog)))


def test_logging_failure_never_breaks_the_request(client, product, monkeypatch):
    from app.services import activity_service

    def boom(*_args, **_kwargs):
        raise activity_service.SQLAlchemyError("disk full")

    monkeypatch.setattr(activity_service, "UserActivityLog", boom)
    r = visit(client, product["id"])
    assert r.status_code == 200


# ------------------------------------------------------------------ keyword ranking


def test_keyword_ranking(client):
    for who in ("a", "b", "c"):
        search(client, "RTX 4080", who=who)
    for who in ("a", "b"):
        search(client, "라이젠", who=who)
    search(client, "맥북", who="a")
    assert keywords(client) == [("rtx 4080", 3), ("라이젠", 2), ("맥북", 1)]
    assert keywords(client, limit=1) == [("rtx 4080", 3)]


def test_keyword_ranking_respects_period(client, db):
    search(client, "오래된검색")
    db.execute(update(UserActivityLog).values(created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=3)))
    db.commit()
    search(client, "새검색")
    assert keywords(client, period="day") == [("새검색", 1)]
    assert set(keywords(client, period="week")) == {("오래된검색", 1), ("새검색", 1)}


def test_keyword_ranking_rejects_all_period(client):
    assert client.get(f"{API}/rankings/keywords", params={"period": "all"}).status_code == 400


def test_keyword_ranking_is_cached(client):
    search(client, "캐시", who="a")
    assert keywords(client) == [("캐시", 1)]
    search(client, "캐시", who="b")
    assert keywords(client) == [("캐시", 1)]  # served from the 60s cache


# ------------------------------------------------------------------ product ranking


def test_product_ranking(client, auth_headers):
    gpu = create(client, auth_headers)["id"]
    kb = create(client, auth_headers, category="keyboard", title="키크론 Q1")["id"]
    for who in ("a", "b", "c"):
        visit(client, gpu, who)
    visit(client, kb, "a")
    visit(client, kb, "a")  # repeat view, not counted

    assert product_ranking(client) == [(gpu, 3), (kb, 1)]
    assert product_ranking(client, category="keyboard") == [(kb, 1)]
    assert product_ranking(client, period="all") == [(gpu, 3), (kb, 1)]


def test_product_ranking_hides_sold_hidden_and_deleted(client, auth_headers):
    ids = [create(client, auth_headers, title=f"상품{i}")["id"] for i in range(3)]
    for pid in ids:
        visit(client, pid)
    client.patch(f"{API}/products/{ids[0]}/status", json={"status": "sold"}, headers=auth_headers)
    client.patch(f"{API}/products/{ids[1]}/status", json={"status": "hidden"}, headers=auth_headers)
    assert [pid for pid, _ in product_ranking(client)] == [ids[2]]
    assert {pid for pid, _ in product_ranking(client, include_sold=True, limit=5)} == {ids[0], ids[2]}

    client.delete(f"{API}/products/{ids[2]}", headers=auth_headers)
    assert product_ranking(client, period="month") == []


def test_rankings_empty_when_no_data(client):
    assert keywords(client) == [] and product_ranking(client) == []
