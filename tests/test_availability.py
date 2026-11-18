"""Signup "중복 확인": GET /auth/availability for email / nickname."""

import pytest

from app.core.config import settings
from tests.conftest import API, signup_and_login

URL = f"{API}/auth/availability"


def check(client, **params):
    return client.get(URL, params=params)


def test_free_email_and_nickname(client):
    r = check(client, email="new@specgrid.kr")
    assert r.status_code == 200
    assert r.json() == {"field": "email", "available": True, "message": "사용할 수 있는 이메일입니다."}
    assert check(client, nickname="새닉네임").json()["available"] is True


def test_taken_email_is_case_insensitive(client):
    signup_and_login(client, "seller@specgrid.kr", "판매자1")
    body = check(client, email="  SELLER@SpecGrid.kr ").json()
    assert body["available"] is False and "이미 가입된" in body["message"]


def test_taken_nickname(client):
    signup_and_login(client, "seller@specgrid.kr", "판매자1")
    body = check(client, nickname="판매자1").json()
    assert body["available"] is False and "이미 사용 중" in body["message"]


@pytest.mark.parametrize(
    "params, message_part",
    [
        ({"email": "not-an-email"}, "이메일 형식"),
        ({"nickname": "a"}, "2~30자"),
        ({"nickname": "bad name!"}, "한글, 영문, 숫자, _"),
    ],
)
def test_invalid_format_is_reported_not_available(client, params, message_part):
    r = check(client, **params)
    assert r.status_code == 200
    assert r.json()["available"] is False and message_part in r.json()["message"]


@pytest.mark.parametrize("params", [{}, {"email": "a@b.kr", "nickname": "닉네임"}])
def test_exactly_one_field_required(client, params):
    assert check(client, **params).status_code == 400


def test_result_matches_signup(client):
    """If the check says 'available', signup with that value must succeed (and vice versa)."""
    assert check(client, email="x@specgrid.kr").json()["available"]
    signup_and_login(client, "x@specgrid.kr", "엑스")
    assert not check(client, email="x@specgrid.kr").json()["available"]
    assert not check(client, nickname="엑스").json()["available"]


def test_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "availability_checks_per_ip", 3)
    for i in range(3):
        assert check(client, email=f"u{i}@specgrid.kr").status_code == 200
    r = check(client, email="u9@specgrid.kr")
    assert r.status_code == 429 and r.json()["code"] == "too_many_requests"
