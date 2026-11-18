from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import update

from app.core.config import settings
from app.core.security import create_token
from app.models import User
from app.models.enums import UserStatus
from tests.conftest import API, CONSENT, signup_and_login

SIGNUP = {"email": "User@SpecGrid.kr", "password": "Passw0rd!", "nickname": "그래픽카드왕", **CONSENT}


def test_signup_returns_user_without_secrets(client):
    r = client.post(f"{API}/auth/signup", json=SIGNUP)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "user@specgrid.kr"  # normalized
    assert body["nickname"] == "그래픽카드왕"
    assert body["role"] == "user"
    assert body["created_at"].endswith("Z") or body["created_at"].endswith("+00:00")
    assert "password" not in str(body) and "password_hash" not in body


@pytest.mark.parametrize(
    "override, expected_message",
    [
        ({"nickname": "다른닉네임"}, "이메일"),
        ({"email": "other@specgrid.kr"}, "닉네임"),
    ],
)
def test_signup_duplicate_is_409(client, override, expected_message):
    assert client.post(f"{API}/auth/signup", json=SIGNUP).status_code == 201
    r = client.post(f"{API}/auth/signup", json={**SIGNUP, **override})
    assert r.status_code == 409
    assert r.json()["code"] == "conflict"
    assert expected_message in r.json()["message"]


@pytest.mark.parametrize(
    "override",
    [
        {"password": "short1"},           # too short
        {"password": "onlyletters"},      # no digit
        {"password": "12345678"},         # no letter
        {"email": "not-an-email"},
        {"nickname": "a"},                # too short
        {"nickname": "공백 포함"},          # invalid char
    ],
)
def test_signup_validation(client, override):
    assert client.post(f"{API}/auth/signup", json={**SIGNUP, **override}).status_code == 422


def test_login_and_me(client):
    headers = signup_and_login(client)
    r = client.get(f"{API}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "seller@specgrid.kr"
    assert r.json()["last_login_at"] is not None


def test_login_errors_do_not_reveal_which_part_was_wrong(client):
    client.post(f"{API}/auth/signup", json=SIGNUP)
    wrong_pw = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": "Wrong123!"})
    no_user = client.post(f"{API}/auth/login", json={"email": "nobody@specgrid.kr", "password": "Wrong123!"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()
    assert wrong_pw.headers["WWW-Authenticate"] == "Bearer"


def test_suspended_user_cannot_login(client, db):
    client.post(f"{API}/auth/signup", json=SIGNUP)
    db.execute(update(User).values(status=UserStatus.SUSPENDED))
    r = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]})
    assert r.status_code == 401


def test_refresh_issues_new_tokens(client):
    client.post(f"{API}/auth/signup", json=SIGNUP)
    tokens = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_access = r.json()["access_token"]
    assert client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200


def test_token_types_are_not_interchangeable(client):
    client.post(f"{API}/auth/signup", json=SIGNUP)
    tokens = client.post(f"{API}/auth/login", json={"email": SIGNUP["email"], "password": SIGNUP["password"]}).json()
    # refresh token must not work as an access token, and vice versa
    assert client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}).status_code == 401
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


def _forged(payload_overrides: dict, key: str | None = None, algorithm: str = "HS256") -> str:
    now = datetime.now(UTC)
    payload = {"sub": "1", "type": "access", "iat": now, "exp": now + timedelta(minutes=5), "jti": "x", "gen": 0,
               **payload_overrides}
    return jwt.encode(payload, key if key is not None else settings.jwt_secret_key, algorithm=algorithm)


@pytest.mark.parametrize(
    "token",
    [
        None,
        "not-a-jwt",
        _forged({"exp": datetime.now(UTC) - timedelta(seconds=1)}),             # expired
        _forged({}, key="x" * 64),                                              # wrong signature
        jwt.encode({"sub": "1", "type": "access", "jti": "x"}, key="", algorithm="none"),  # alg=none
        _forged({"sub": "999999999"}),                                          # user doesn't exist
    ],
    ids=["missing", "garbage", "expired", "bad-signature", "alg-none", "unknown-user"],
)
def test_me_rejects_invalid_tokens(client, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = client.get(f"{API}/users/me", headers=headers)
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_valid_token_for_deleted_user_is_rejected(client, db):
    headers = signup_and_login(client)
    user_id = client.get(f"{API}/users/me", headers=headers).json()["id"]
    db.execute(update(User).where(User.id == user_id).values(status=UserStatus.WITHDRAWN))
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401
    assert create_token(user_id, "access")  # sanity: token creation itself still works
