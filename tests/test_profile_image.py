"""Profile photo: upload/replace/delete, privacy (EXIF), square crop, visibility to other users."""

import pytest
from PIL import Image

from app.core.config import settings
from tests.conftest import API, signup_and_login
from tests.test_product_images import image_bytes, jpeg_with_gps_and_rotation, media_files, png_bomb, stored_path
from tests.test_products import create

URL = f"{API}/users/me/profile-image"


def put_avatar(client, headers, data=None, name="me.jpg", mime="image/jpeg"):
    return client.put(URL, files={"file": (name, data or image_bytes(size=(800, 600)), mime)}, headers=headers)


def test_default_is_none(client, auth_headers):
    assert client.get(f"{API}/users/me", headers=auth_headers).json()["profile_image_url"] is None


def test_upload_crops_to_square_webp(client, auth_headers):
    r = put_avatar(client, auth_headers)
    assert r.status_code == 200, r.text
    url = r.json()["profile_image_url"]
    assert url.startswith(settings.media_base_url) and url.endswith(".webp")
    with Image.open(stored_path(url)) as saved:
        assert saved.format == "WEBP" and saved.size == (400, 400)
    assert client.get(f"{API}/users/me", headers=auth_headers).json()["profile_image_url"] == url
    served = client.get("/media/" + url.split("/media/", 1)[1])
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"


def test_small_image_is_not_upscaled(client, auth_headers):
    url = put_avatar(client, auth_headers, image_bytes(size=(120, 90))).json()["profile_image_url"]
    with Image.open(stored_path(url)) as saved:
        assert saved.size == (90, 90)


def test_transparent_png_is_flattened(client, auth_headers):
    import io
    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buf, format="PNG")
    url = put_avatar(client, auth_headers, buf.getvalue(), "a.png", "image/png").json()["profile_image_url"]
    with Image.open(stored_path(url)) as saved:
        assert saved.mode == "RGB" and saved.getpixel((10, 10)) == (255, 255, 255)


def test_gps_exif_is_stripped(client, auth_headers):
    url = put_avatar(client, auth_headers, jpeg_with_gps_and_rotation()).json()["profile_image_url"]
    with Image.open(stored_path(url)) as saved:
        assert not saved.getexif() and "exif" not in saved.info


def test_replace_deletes_old_file(client, auth_headers):
    first = put_avatar(client, auth_headers).json()["profile_image_url"]
    second = put_avatar(client, auth_headers, image_bytes(color=(0, 0, 255))).json()["profile_image_url"]
    assert first != second
    assert not stored_path(first).exists() and stored_path(second).exists()


def test_delete(client, auth_headers):
    url = put_avatar(client, auth_headers).json()["profile_image_url"]
    r = client.delete(URL, headers=auth_headers)
    assert r.status_code == 200 and r.json()["profile_image_url"] is None
    assert not stored_path(url).exists()
    assert client.delete(URL, headers=auth_headers).status_code == 200  # idempotent


def test_user_filename_is_never_used(client, auth_headers):
    url = put_avatar(client, auth_headers, name="../../evil.php").json()["profile_image_url"]
    assert "evil" not in url and ".." not in url


@pytest.mark.parametrize(
    "name, data, mime",
    [
        ("fake.jpg", b"<?php system($_GET['c']); ?>", "image/jpeg"),
        ("anim.gif", image_bytes("GIF"), "image/gif"),
        ("x.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "image/svg+xml"),
        ("bomb.png", png_bomb(), "image/png"),
    ],
    ids=["php-as-jpg", "gif", "svg", "decompression-bomb"],
)
def test_rejects_bad_files_and_keeps_old_photo(client, auth_headers, name, data, mime):
    old = put_avatar(client, auth_headers).json()["profile_image_url"]
    before = media_files()
    r = put_avatar(client, auth_headers, data, name, mime)
    assert r.status_code == 422 and r.json()["code"] == "invalid_image"
    assert media_files() == before
    assert client.get(f"{API}/users/me", headers=auth_headers).json()["profile_image_url"] == old


def test_too_large(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "max_image_upload_mb", 0)
    r = put_avatar(client, auth_headers)
    assert r.status_code == 413


def test_requires_login(client):
    assert put_avatar(client, {}).status_code == 401
    assert client.delete(URL).status_code == 401


def test_other_users_see_seller_photo(client, auth_headers):
    url = put_avatar(client, auth_headers).json()["profile_image_url"]
    product = create(client, auth_headers, spec=None)
    detail = client.get(f"{API}/products/{product['id']}").json()
    assert detail["seller"]["profile_image_url"] == url

    buyer = signup_and_login(client, "buyer@specgrid.kr", "구매자1")
    assert client.get(f"{API}/users/me", headers=buyer).json()["profile_image_url"] is None
