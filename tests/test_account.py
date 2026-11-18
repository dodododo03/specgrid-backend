"""Signup consent (필수 동의) and 회원 탈퇴."""

import pytest
from sqlalchemy import select

from app.models import Favorite, ProductImage, Trade, User
from app.models.enums import TradeStatus, UserStatus
from tests.conftest import API, CONSENT, signup_and_login
from tests.test_chat import buyer, product, stranger  # noqa: F401 — fixtures
from tests.test_product_images import jpg, stored_path, upload
from tests.test_products import create
from tests.test_profile_image import put_avatar
from tests.test_trades import act, request

SELLER = {"email": "seller@specgrid.kr", "password": "Passw0rd!"}  # auth_headers' account
WITHDRAW = f"{API}/users/me/withdraw"


def withdraw(client, headers, password="Passw0rd!"):
    return client.post(WITHDRAW, json={"password": password}, headers=headers)


# ------------------------------------------------------------------ consent


@pytest.mark.parametrize("missing", ["agree_terms", "agree_privacy", "over_14"])
@pytest.mark.parametrize("value", [False, None])
def test_signup_requires_every_consent(client, missing, value):
    body = {"email": "c@specgrid.kr", "password": "Passw0rd!", "nickname": "동의테스트", **CONSENT}
    if value is None:
        del body[missing]
    else:
        body[missing] = value
    r = client.post(f"{API}/auth/signup", json=body)
    assert r.status_code == 422


def test_consent_message_is_korean(client):
    body = {"email": "c@specgrid.kr", "password": "Passw0rd!", "nickname": "동의테스트", **CONSENT, "over_14": False}
    assert "14세" in client.post(f"{API}/auth/signup", json=body).text


def test_consent_time_is_recorded(client, db):
    signup_and_login(client, "c@specgrid.kr", "동의테스트")
    user = db.scalar(select(User).where(User.email == "c@specgrid.kr"))
    assert user.terms_agreed_at is not None and user.privacy_agreed_at is not None


# ------------------------------------------------------------------ withdrawal


def test_withdraw_destroys_personal_data_and_logs_out(client, auth_headers, db):
    avatar = put_avatar(client, auth_headers).json()["profile_image_url"]
    me = client.get(f"{API}/users/me", headers=auth_headers).json()

    r = withdraw(client, auth_headers)
    assert r.status_code == 204, r.text

    user = db.get(User, me["id"])
    db.refresh(user)
    assert user.status == UserStatus.WITHDRAWN and user.withdrawn_at is not None
    assert user.email.endswith("@withdrawn.invalid") and "seller" not in user.email
    assert user.nickname == f"탈퇴회원#{me['id']}"
    assert user.password_hash is None and user.profile_image_key is None
    assert not stored_path(avatar).exists()

    assert client.get(f"{API}/users/me", headers=auth_headers).status_code == 401  # every session is gone
    assert client.post(f"{API}/auth/login", json=SELLER).status_code == 401


def test_same_email_and_nickname_can_sign_up_again(client, auth_headers):
    assert withdraw(client, auth_headers).status_code == 204
    signup_and_login(client, "seller@specgrid.kr", "판매자1")  # conftest's defaults for auth_headers


def test_wrong_password_is_400_not_401(client, auth_headers):
    r = withdraw(client, auth_headers, "WrongPass1")
    assert r.status_code == 400 and r.json()["code"] == "wrong_password"
    assert client.get(f"{API}/users/me", headers=auth_headers).status_code == 200  # still a member


def test_wrong_password_attempts_are_rate_limited(client, auth_headers):
    for _ in range(5):
        assert withdraw(client, auth_headers, "WrongPass1").status_code == 400
    assert withdraw(client, auth_headers).status_code == 429


def test_requires_login(client):
    assert client.post(WITHDRAW, json={"password": "Passw0rd!"}).status_code == 401


def test_listings_photos_and_pending_trades(client, auth_headers, buyer, product, db):
    img = upload(client, auth_headers, product["id"], jpg()).json()["images"][0]
    other = create(client, buyer, title="구매자의 상품")
    asked = request(client, buyer, product["id"])            # buyer -> my product (pending)
    mine = request(client, auth_headers, other["id"])        # me -> buyer's product (pending)

    assert withdraw(client, auth_headers).status_code == 204

    assert client.get(f"{API}/products/{product['id']}").status_code == 404   # listing gone
    assert not stored_path(img["url"]).exists()
    assert db.scalar(select(ProductImage).where(ProductImage.product_id == product["id"])) is None
    assert db.get(Trade, asked["id"]).status == TradeStatus.REJECTED
    assert db.get(Trade, mine["id"]).status == TradeStatus.CANCELED
    assert client.get(f"{API}/products/{other['id']}").status_code == 200    # others' listings untouched


def test_refused_while_a_trade_is_reserved(client, auth_headers, buyer, product):
    trade = request(client, buyer, product["id"])
    act(client, auth_headers, trade["id"], "accept")
    for who in (auth_headers, buyer):  # seller or buyer of the reserved deal
        r = withdraw(client, who)
        assert r.status_code == 409 and "예약중" in r.json()["message"]
    act(client, auth_headers, trade["id"], "complete")
    assert withdraw(client, buyer).status_code == 204  # completed trades don't block


def test_favorites_removed_and_counts_fixed(client, auth_headers, buyer, product, db):
    client.put(f"{API}/products/{product['id']}/favorite", headers=buyer)
    assert client.get(f"{API}/products/{product['id']}").json()["favorite_count"] == 1
    assert withdraw(client, buyer).status_code == 204
    assert client.get(f"{API}/products/{product['id']}").json()["favorite_count"] == 0
    assert db.scalar(select(Favorite).where(Favorite.product_id == product["id"])) is None


def test_chat_history_stays_for_the_other_party(client, auth_headers, buyer, product):
    room = client.post(f"{API}/chat/rooms", json={"product_id": product["id"]}, headers=buyer).json()
    client.post(f"{API}/chat/rooms/{room['id']}/messages", json={"content": "안녕하세요"}, headers=buyer)
    assert withdraw(client, buyer).status_code == 204

    rooms = client.get(f"{API}/chat/rooms", headers=auth_headers).json()
    partner = rooms[0]["partner"] if isinstance(rooms, list) else rooms["items"][0]["partner"]
    assert partner["nickname"].startswith("탈퇴회원#") and partner["profile_image_url"] is None
    msgs = client.get(f"{API}/chat/rooms/{room['id']}/messages", headers=auth_headers).json()
    items = msgs if isinstance(msgs, list) else msgs["items"]
    assert any(m["content"] == "안녕하세요" for m in items)
    # and nobody can message the withdrawn member any more
    r = client.post(f"{API}/chat/rooms/{room['id']}/messages", json={"content": "계세요?"}, headers=auth_headers)
    assert r.status_code == 409
