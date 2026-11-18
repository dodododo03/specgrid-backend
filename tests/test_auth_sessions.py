"""Redis-backed session security: logout, logout-all, refresh rotation/reuse, login rate limiting."""

import time

import pytest
import redis

from app.core.config import settings
from app.core.redis import get_redis
from app.main import app
from tests.conftest import API, CONSENT

USER = {"email": "sess@specgrid.kr", "password": "Passw0rd!", "nickname": "세션테스트", **CONSENT}


@pytest.fixture
def user(client):
    assert client.post(f"{API}/auth/signup", json=USER).status_code == 201
    return USER


def login(client, email=USER["email"], password=USER["password"]):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def me(client, access):
    return client.get(f"{API}/users/me", headers=bearer(access)).status_code


def refresh(client, token):
    return client.post(f"{API}/auth/refresh", json={"refresh_token": token})


# ------------------------------------------------------------------ logout


def test_logout_revokes_access_and_refresh(client, user):
    tokens = login(client).json()
    assert me(client, tokens["access_token"]) == 200

    r = client.post(f"{API}/auth/logout", json={"refresh_token": tokens["refresh_token"]},
                    headers=bearer(tokens["access_token"]))
    assert r.status_code == 204
    assert me(client, tokens["access_token"]) == 401          # access token dead immediately
    assert refresh(client, tokens["refresh_token"]).status_code == 401  # refresh token dead too


def test_logout_only_affects_that_session(client, user):
    phone = login(client).json()
    laptop = login(client).json()
    client.post(f"{API}/auth/logout", headers=bearer(phone["access_token"]))
    assert me(client, phone["access_token"]) == 401
    assert me(client, laptop["access_token"]) == 200


def test_logout_requires_valid_access_token(client, user):
    assert client.post(f"{API}/auth/logout").status_code == 401


def test_logout_ignores_garbage_or_foreign_refresh_token(client, user):
    other = {"email": "other@specgrid.kr", "password": "Passw0rd!", "nickname": "남의토큰", **CONSENT}
    client.post(f"{API}/auth/signup", json=other)
    other_tokens = login(client, other["email"], other["password"]).json()
    mine = login(client).json()

    r = client.post(f"{API}/auth/logout", json={"refresh_token": other_tokens["refresh_token"]},
                    headers=bearer(mine["access_token"]))
    assert r.status_code == 204
    assert refresh(client, other_tokens["refresh_token"]).status_code == 200  # not mine -> untouched

    again = login(client).json()
    assert client.post(f"{API}/auth/logout", json={"refresh_token": "garbage"},
                       headers=bearer(again["access_token"])).status_code == 204


def test_logout_all_kills_every_session(client, user):
    phone = login(client).json()
    laptop = login(client).json()
    assert client.post(f"{API}/auth/logout-all", headers=bearer(phone["access_token"])).status_code == 204

    for session in (phone, laptop):
        assert me(client, session["access_token"]) == 401
        assert refresh(client, session["refresh_token"]).status_code == 401

    fresh = login(client).json()  # logging in again works and is not affected
    assert me(client, fresh["access_token"]) == 200


# ------------------------------------------------------------------ refresh rotation


def test_refresh_rotates_and_old_token_is_single_use(client, user):
    first = login(client).json()
    second = refresh(client, first["refresh_token"]).json()
    assert second["refresh_token"] != first["refresh_token"]
    assert me(client, second["access_token"]) == 200
    assert refresh(client, second["refresh_token"]).status_code == 200  # the new one works once


def test_refresh_token_reuse_revokes_all_sessions(client, user):
    stolen = login(client).json()
    legit = refresh(client, stolen["refresh_token"]).json()   # real user rotates

    replay = refresh(client, stolen["refresh_token"])          # attacker replays the old token
    assert replay.status_code == 401
    assert "모든 기기" in replay.json()["message"]

    assert me(client, legit["access_token"]) == 401             # everything for that user is revoked
    assert refresh(client, legit["refresh_token"]).status_code == 401


# ------------------------------------------------------------------ login rate limit


def test_login_locks_after_max_failures_per_email(client, user):
    for _ in range(settings.login_max_attempts_per_email):
        assert login(client, password="Wrong123!").status_code == 401

    locked = login(client)  # even the correct password is refused while locked
    assert locked.status_code == 429
    assert locked.json()["code"] == "too_many_requests"
    assert 0 < int(locked.headers["Retry-After"]) <= settings.login_lock_minutes * 60


def test_lock_is_per_email(client, user):
    for _ in range(settings.login_max_attempts_per_email):
        login(client, email="victim@specgrid.kr", password="Wrong123!")
    assert login(client, email="victim@specgrid.kr", password="Wrong123!").status_code == 429
    assert login(client).status_code == 200  # a different account is not locked


def test_unknown_email_is_rate_limited_the_same_way(client):
    for _ in range(settings.login_max_attempts_per_email):
        assert login(client, email="nobody@specgrid.kr").status_code == 401
    assert login(client, email="nobody@specgrid.kr").status_code == 429


def test_success_resets_failure_counter(client, user):
    for _ in range(settings.login_max_attempts_per_email - 1):
        login(client, password="Wrong123!")
    assert login(client).status_code == 200
    for _ in range(settings.login_max_attempts_per_email - 1):
        assert login(client, password="Wrong123!").status_code == 401  # counter started over


def test_login_locks_per_ip_across_many_emails(client, monkeypatch):
    monkeypatch.setattr(settings, "login_max_attempts_per_ip", 3)
    for i in range(3):
        login(client, email=f"spray{i}@specgrid.kr", password="Wrong123!")
    assert login(client, email="fresh@specgrid.kr", password="Wrong123!").status_code == 429


def test_lock_window_expires(client, user, redis_client):
    for _ in range(settings.login_max_attempts_per_email):
        login(client, password="Wrong123!")
    assert login(client).status_code == 429
    for key in redis_client.scan_iter("specgrid:login_fail:*"):  # fast-forward the 15-minute window
        redis_client.pexpire(key, 50)
    time.sleep(0.2)
    assert login(client).status_code == 200


# ------------------------------------------------------------------ Redis outage


def test_fail_closed_when_redis_is_down(client, user):
    tokens = login(client).json()
    dead = redis.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    app.dependency_overrides[get_redis] = lambda: dead

    assert me(client, tokens["access_token"]) == 503      # can't prove it isn't revoked -> refuse
    r = login(client)
    assert r.status_code == 503 and r.json()["code"] == "service_unavailable"
    assert client.get(f"{API}/products").status_code == 200  # public browsing doesn't need Redis
