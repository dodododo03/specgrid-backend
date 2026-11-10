import pytest
from sqlalchemy import update

from app.models import Product
from app.models.enums import ProductStatus
from tests.conftest import API, signup_and_login

GPU_4080 = {
    "category": "gpu", "title": "RTX 4080 FE 풀박스", "description": "채굴 X, 게임용으로만 사용했습니다.",
    "price": 1_200_000, "condition": "like_new", "trade_location": "서울 용산구",
    "spec": {"manufacturer": "NVIDIA", "gpu_model": "GeForce RTX 4080", "vram_gb": 16, "extra_specs": {"tdp_w": 320}},
}


def create(client, headers, **overrides):
    body = {**GPU_4080, **overrides}
    r = client.post(f"{API}/products", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ create


def test_create_requires_login(client):
    assert client.post(f"{API}/products", json=GPU_4080).status_code == 401


def test_create_product_with_spec(client, auth_headers):
    p = create(client, auth_headers)
    assert p["status"] == "on_sale" and p["view_count"] == 0 and p["is_hot_deal"] is False
    assert p["seller"]["nickname"] == "판매자1"
    assert "email" not in p["seller"]  # seller's private info is not exposed
    assert p["spec"]["vram_gb"] == 16 and p["spec"]["extra_specs"] == {"tdp_w": 320}


def test_create_without_spec(client, auth_headers):
    p = create(client, auth_headers, category="server", spec=None)
    assert p["spec"] is None


@pytest.mark.parametrize(
    "override",
    [
        {"price": -1},
        {"price": 1_000_000_001},
        {"title": "a"},
        {"description": "짧음"},
        {"category": "car"},
        {"condition": "brand_new"},
        {"spec": {"vram_gb": 0}},
        {"is_hot_deal": True, "price": -5},
    ],
)
def test_create_validation(client, auth_headers, override):
    r = client.post(f"{API}/products", json={**GPU_4080, **override}, headers=auth_headers)
    assert r.status_code == 422


def test_seller_cannot_self_promote_to_hot_deal(client, auth_headers):
    p = create(client, auth_headers, is_hot_deal=True)  # unknown field is ignored
    assert p["is_hot_deal"] is False


# ------------------------------------------------------------------ detail


def visit(client, pid, visitor="browser-1"):
    """Anonymous visitors are told apart by IP + User-Agent; vary the UA to simulate different people."""
    return client.get(f"{API}/products/{pid}", headers={"User-Agent": visitor})


def test_detail_increments_view_count(client, auth_headers):
    pid = create(client, auth_headers)["id"]
    assert visit(client, pid, "a").json()["view_count"] == 1
    assert visit(client, pid, "b").json()["view_count"] == 2


def test_repeat_views_by_same_visitor_count_once(client, auth_headers):
    pid = create(client, auth_headers)["id"]
    for _ in range(5):
        r = visit(client, pid, "refresh-spammer")
    assert r.json()["view_count"] == 1


def test_seller_own_views_do_not_count(client, auth_headers):
    pid = create(client, auth_headers)["id"]
    assert client.get(f"{API}/products/{pid}", headers=auth_headers).json()["view_count"] == 0


def test_invalid_token_on_public_detail_is_just_anonymous(client, auth_headers):
    pid = create(client, auth_headers)["id"]
    r = client.get(f"{API}/products/{pid}", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 200 and r.json()["view_count"] == 1


def test_detail_404_for_missing_hidden_or_deleted(client, auth_headers, db):
    assert client.get(f"{API}/products/999999999").status_code == 404
    hidden = create(client, auth_headers)["id"]
    deleted = create(client, auth_headers)["id"]
    db.execute(update(Product).where(Product.id == hidden).values(status=ProductStatus.HIDDEN))
    db.execute(update(Product).where(Product.id == deleted).values(deleted_at=Product.created_at))
    assert client.get(f"{API}/products/{hidden}").status_code == 404
    assert client.get(f"{API}/products/{deleted}").status_code == 404


# ------------------------------------------------------------------ search


@pytest.fixture
def catalog(client, auth_headers, db):
    """A small catalog covering every filter. Returns {name: id}."""
    items = {
        "4080": create(client, auth_headers),
        "4070": create(client, auth_headers, title="RTX 4070 SUPER", price=700_000, condition="lightly_used",
                       spec={"manufacturer": "MSI", "gpu_model": "GeForce RTX 4070 SUPER", "vram_gb": 12}),
        "macbook": create(client, auth_headers, category="laptop", title="MacBook Pro 14 M3 Pro", price=2_500_000,
                          spec={"manufacturer": "Apple", "cpu_model": "Apple M3 Pro", "cpu_cores": 12,
                                "ram_gb": 36, "storage_gb": 1024}),
        "thinkpad": create(client, auth_headers, category="laptop", title="ThinkPad X1 Carbon", price=1_800_000,
                           condition="used", spec={"manufacturer": "Lenovo", "cpu_model": "Intel Core Ultra 7 155H",
                                                   "cpu_cores": 16, "ram_gb": 32, "storage_gb": 1024}),
        "server": create(client, auth_headers, category="server", title="Dell R740 랙서버", price=3_000_000, spec=None),
        "keyboard": create(client, auth_headers, category="keyboard", title="100% 풀배열 키보드", price=150_000,
                           spec=None),
    }
    ids = {k: v["id"] for k, v in items.items()}
    db.execute(update(Product).where(Product.id == ids["thinkpad"]).values(status=ProductStatus.SOLD))
    db.execute(update(Product).where(Product.id == ids["4070"]).values(is_hot_deal=True))
    return ids


def search(client, **params):
    r = client.get(f"{API}/products", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def names(result, catalog):
    by_id = {v: k for k, v in catalog.items()}
    return [by_id[i["id"]] for i in result["items"]]


def test_default_search_hides_sold(client, catalog):
    result = search(client)
    assert result["total"] == 5
    assert "thinkpad" not in names(result, catalog)


@pytest.mark.parametrize(
    "params, expected",
    [
        ({"category": "gpu"}, {"4080", "4070"}),
        ({"min_vram_gb": 16}, {"4080"}),
        ({"gpu": "4070"}, {"4070"}),
        ({"gpu": "rtx"}, {"4080", "4070"}),                        # case-insensitive partial match
        ({"manufacturer": "apple"}, {"macbook"}),
        ({"min_ram_gb": 32}, {"macbook"}),                         # thinkpad is sold
        ({"min_ram_gb": 32, "include_sold": True}, {"macbook", "thinkpad"}),
        ({"cpu": "intel", "include_sold": True}, {"thinkpad"}),
        ({"min_cores": 12, "min_storage_gb": 1000}, {"macbook"}),
        ({"min_price": 1_000_000, "max_price": 2_500_000}, {"4080", "macbook"}),
        ({"condition": ["like_new", "lightly_used"], "category": "gpu"}, {"4080", "4070"}),
        ({"condition": "lightly_used"}, {"4070"}),
        ({"hot_only": True}, {"4070"}),
        ({"q": "rtx 40"}, {"4080", "4070"}),
        ({"q": "100%"}, {"keyboard"}),
        ({"q": "%"}, {"keyboard"}),                                # '%' is literal, not a wildcard
        ({"q": "_"}, set()),                                       # '_' is literal, not a wildcard
        ({"min_vram_gb": 1, "category": "server"}, set()),         # spec filter excludes products without spec
    ],
)
def test_filters(client, catalog, params, expected):
    assert set(names(search(client, **params), catalog)) == expected


def test_sort_and_pagination(client, catalog):
    asc = names(search(client, sort="price_asc"), catalog)
    assert asc == ["keyboard", "4070", "4080", "macbook", "server"]
    assert names(search(client, sort="price_desc"), catalog) == list(reversed(asc))

    page1 = search(client, sort="price_asc", size=2, page=1)
    page3 = search(client, sort="price_asc", size=2, page=3)
    assert names(page1, catalog) == ["keyboard", "4070"] and page1["has_next"] is True
    assert names(page3, catalog) == ["server"] and page3["has_next"] is False
    assert page1["total"] == page3["total"] == 5


def test_popular_sort_uses_view_count(client, catalog):
    for who in ("a", "b", "c"):
        visit(client, catalog["server"], who)
    visit(client, catalog["keyboard"], "a")
    assert names(search(client, sort="popular"), catalog)[:2] == ["server", "keyboard"]


@pytest.mark.parametrize(
    "params",
    [{"min_price": 10, "max_price": 5}, {"size": 51}, {"page": 0}, {"sort": "random"}, {"category": "car"}],
)
def test_search_validation(client, params):
    assert client.get(f"{API}/products", params=params).status_code == 422
