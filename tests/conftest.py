"""Tests run against a real MariaDB test database (specgrid_test), never the dev DB.

Each test runs inside a transaction that is rolled back afterwards, so tests are
isolated and leave no data behind even though the app code calls commit().
"""

import os

os.environ["DB_NAME"] = "specgrid_test"  # must be set before app settings are imported
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # dev data lives in db 0

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.core.redis import get_redis, get_redis_client  # noqa: E402
from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402

assert engine.url.database == "specgrid_test", "refusing to run tests against a non-test database"
assert get_redis_client().connection_pool.connection_kwargs["db"] == 15, "refusing to flush a non-test Redis db"

API = "/api/v1"


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db() -> None:
    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def db() -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    # App commits become SAVEPOINT releases; the outer transaction is rolled back at the end.
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=False,
                      expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def redis_client():
    client = get_redis_client()
    client.flushdb()  # db 15 only (asserted above)
    yield client
    client.flushdb()


@pytest.fixture
def client(db: Session, redis_client) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_redis] = lambda: redis_client
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signup_and_login(client: TestClient, email: str = "seller@specgrid.kr", nickname: str = "판매자1",
                     password: str = "Passw0rd!") -> dict[str, str]:
    r = client.post(f"{API}/auth/signup", json={"email": email, "password": password, "nickname": nickname})
    assert r.status_code == 201, r.text
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return signup_and_login(client)
