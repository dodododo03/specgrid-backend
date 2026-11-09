"""Product photo upload: validation, privacy (EXIF), normalization, consistency, ownership."""

import io
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.config import settings
from app.models import ProductImage
from tests.conftest import API, signup_and_login
from tests.test_products import create

MEDIA = Path(settings.media_root)


# ------------------------------------------------------------------ image factories


def image_bytes(fmt="JPEG", size=(800, 600), color=(200, 30, 30), exif=None) -> bytes:
    out = io.BytesIO()
    img = Image.new("RGB", size, color)
    kwargs = {"exif": exif} if exif is not None else {}
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


def jpeg_with_gps_and_rotation(size=(200, 100), orientation=6) -> bytes:
    exif = Image.Exif()
    exif[0x0112] = orientation                                   # Orientation: rotate 90° CW
    exif[0x010F] = "SpecGridPhone"                               # Make
    exif[0x8825] = {1: "N", 2: (37.0, 33.0, 0.0), 3: "E", 4: (126.0, 58.0, 0.0)}  # GPSInfo (Seoul)
    return image_bytes("JPEG", size, exif=exif.tobytes())


def png_bomb(width=20000, height=20000) -> bytes:
    """A tiny valid-looking PNG whose header claims 400 megapixels."""
    small = image_bytes("PNG", (1, 1))
    ihdr_start = 8 + 4 + 4  # signature + length + 'IHDR'
    data = bytearray(small)
    data[ihdr_start:ihdr_start + 8] = struct.pack(">II", width, height)
    crc = zlib.crc32(bytes(data[12:ihdr_start + 13]))
    data[ihdr_start + 13:ihdr_start + 17] = struct.pack(">I", crc)
    return bytes(data)


def upload(client, headers, pid, *files):
    payload = [("files", (name, data, mime)) for name, data, mime in files]
    return client.post(f"{API}/products/{pid}/images", files=payload, headers=headers)


def jpg(data=None, name="photo.jpg"):
    return (name, data or image_bytes(), "image/jpeg")


def media_files() -> set[Path]:
    return {p for p in MEDIA.rglob("*") if p.is_file()}


def stored_path(url: str) -> Path:
    return MEDIA / url.split("/media/", 1)[1]


@pytest.fixture
def product(client, auth_headers):
    return create(client, auth_headers, spec=None)


def image_rows(db, pid):
    return db.scalar(select(func.count()).where(ProductImage.product_id == pid))


# ------------------------------------------------------------------ happy path


def test_upload_multiple_and_cover(client, auth_headers, product):
    r = upload(client, auth_headers, product["id"], jpg(), ("b.png", image_bytes("PNG"), "image/png"))
    assert r.status_code == 201, r.text
    images = r.json()["images"]
    assert len(images) == 2 and [i["sort_order"] for i in images] == [1, 2]
    assert r.json()["thumbnail_url"] == images[0]["thumbnail_url"]   # first photo is the cover

    for img in images:
        assert img["url"].startswith(settings.media_base_url) and img["url"].endswith(".webp")
        for url in (img["url"], img["thumbnail_url"]):
            with Image.open(stored_path(url)) as saved:
                assert saved.format == "WEBP"

    listed = client.get(f"{API}/products", params={"q": product["title"]}).json()["items"][0]
    assert listed["thumbnail_url"] == images[0]["thumbnail_url"]


def test_uploaded_file_is_served(client, auth_headers, product):
    url = upload(client, auth_headers, product["id"], jpg()).json()["images"][0]["url"]
    r = client.get("/media/" + url.split("/media/", 1)[1])
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"


def test_gps_exif_is_stripped_and_rotation_applied(client, auth_headers, product):
    img = upload(client, auth_headers, product["id"], jpg(jpeg_with_gps_and_rotation())).json()["images"][0]
    with Image.open(stored_path(img["url"])) as saved:
        assert not saved.getexif()                      # no GPS, no camera model, nothing
        assert "exif" not in saved.info
        assert saved.size == (100, 200)                 # 200x100 rotated by Orientation=6
    assert (img["width"], img["height"]) == (100, 200)


def test_large_image_is_resized(client, auth_headers, product):
    img = upload(client, auth_headers, product["id"], jpg(image_bytes(size=(3000, 1000)))).json()["images"][0]
    assert (img["width"], img["height"]) == (1600, 533)
    with Image.open(stored_path(img["thumbnail_url"])) as thumb:
        assert max(thumb.size) == 400


def test_user_filename_is_never_used(client, auth_headers, product):
    img = upload(client, auth_headers, product["id"], jpg(name="../../evil.php")).json()["images"][0]
    assert "evil" not in img["url"] and ".." not in img["url"]


# ------------------------------------------------------------------ rejection


@pytest.mark.parametrize(
    "name, data, mime",
    [
        ("fake.jpg", b"<?php system($_GET['c']); ?>", "image/jpeg"),       # script disguised as jpg
        ("anim.gif", image_bytes("GIF"), "image/gif"),                     # format not allowed
        ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
        ("broken.jpg", image_bytes()[:200], "image/jpeg"),                  # truncated
        ("bomb.png", png_bomb(), "image/png"),                              # decompression bomb
    ],
    ids=["php-as-jpg", "gif", "svg", "truncated", "decompression-bomb"],
)
def test_rejects_bad_files(client, auth_headers, product, db, name, data, mime):
    r = upload(client, auth_headers, product["id"], (name, data, mime))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_image"
    assert image_rows(db, product["id"]) == 0


def test_all_or_nothing(client, auth_headers, product, db):
    before = media_files()
    r = upload(client, auth_headers, product["id"], jpg(), ("bad.jpg", b"not an image", "image/jpeg"))
    assert r.status_code == 422
    assert image_rows(db, product["id"]) == 0
    assert media_files() == before           # the valid photo was not written either


def test_file_too_large(client, auth_headers, product, monkeypatch):
    monkeypatch.setattr(settings, "max_image_upload_mb", 0)
    r = upload(client, auth_headers, product["id"], jpg())
    assert r.status_code == 413 and r.json()["code"] == "payload_too_large"


def test_max_images_per_product(client, auth_headers, product, monkeypatch):
    monkeypatch.setattr(settings, "max_images_per_product", 3)
    assert upload(client, auth_headers, product["id"], jpg(), jpg()).status_code == 201
    r = upload(client, auth_headers, product["id"], jpg(), jpg())
    assert r.status_code == 422 and "최대 3장" in r.json()["message"]
    assert upload(client, auth_headers, product["id"], jpg()).status_code == 201  # exactly 3 is fine


def test_db_failure_removes_written_files(client, auth_headers, product, db, monkeypatch):
    before = media_files()

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "commit", boom)
    with pytest.raises(RuntimeError):
        upload(client, auth_headers, product["id"], jpg(), jpg())
    assert media_files() == before


# ------------------------------------------------------------------ access control


def test_owner_only(client, auth_headers, product):
    other = signup_and_login(client, email="other@specgrid.kr", nickname="남의상품")
    assert upload(client, other, product["id"], jpg()).status_code == 403
    assert client.post(f"{API}/products/{product['id']}/images", files=[("files", jpg())]).status_code == 401
    assert upload(client, auth_headers, 999999999, jpg()).status_code == 404


# ------------------------------------------------------------------ delete / reorder


def test_delete_image_removes_files_and_moves_cover(client, auth_headers, product, db):
    first, second = upload(client, auth_headers, product["id"], jpg(), jpg()).json()["images"]
    r = client.delete(f"{API}/products/{product['id']}/images/{first['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["images"]] == [second["id"]]
    assert r.json()["thumbnail_url"] == second["thumbnail_url"]
    assert not stored_path(first["url"]).exists() and not stored_path(first["thumbnail_url"]).exists()

    r = client.delete(f"{API}/products/{product['id']}/images/{first['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_cannot_delete_image_via_another_product(client, auth_headers, product):
    img = upload(client, auth_headers, product["id"], jpg()).json()["images"][0]
    mine_too = create(client, auth_headers, spec=None)
    r = client.delete(f"{API}/products/{mine_too['id']}/images/{img['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_reorder_changes_cover(client, auth_headers, product):
    a, b, c = upload(client, auth_headers, product["id"], jpg(), jpg(), jpg()).json()["images"]
    r = client.put(f"{API}/products/{product['id']}/images/order",
                   json={"image_ids": [c["id"], a["id"], b["id"]]}, headers=auth_headers)
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["images"]] == [c["id"], a["id"], b["id"]]
    assert r.json()["thumbnail_url"] == c["thumbnail_url"]


@pytest.mark.parametrize("ids", ["missing-one", "duplicate", "foreign"])
def test_reorder_requires_exact_set(client, auth_headers, product, ids):
    a, b = upload(client, auth_headers, product["id"], jpg(), jpg()).json()["images"]
    body = {"missing-one": [a["id"]], "duplicate": [a["id"], a["id"]], "foreign": [a["id"], 999999]}[ids]
    r = client.put(f"{API}/products/{product['id']}/images/order", json={"image_ids": body}, headers=auth_headers)
    assert r.status_code == 400
