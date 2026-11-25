"""Validate and normalize uploaded product and profile photos.

Never trust the filename, extension or Content-Type: the bytes are decoded with Pillow and
re-encoded from pixels. Re-encoding (1) drops EXIF — including the GPS location of the
seller's home in phone photos, (2) neutralizes polyglot/malicious payloads, and
(3) gives consistently sized WebP files.
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.exceptions import InvalidImageError

ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}  # MPO = multi-picture JPEG many phones (Galaxy, iPhone) save
MAX_PIXELS = 40_000_000          # ~40MP: larger is almost certainly a decompression bomb
MAIN_MAX_SIDE = 1600
THUMB_MAX_SIDE = 400
AVATAR_SIDE = 400
WEBP_QUALITY = 82

Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # Pillow raises DecompressionBombError above 2x this


@dataclass(frozen=True)
class ProcessedImage:
    main: bytes
    thumb: bytes
    width: int
    height: int


def _encode(image: Image.Image, max_side: int) -> tuple[bytes, tuple[int, int]]:
    copy = image.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)  # keeps aspect ratio, never upscales
    out = io.BytesIO()
    copy.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)  # no exif/icc passed -> stripped
    return out.getvalue(), copy.size


def _decode(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format not in ALLOWED_FORMATS:
                raise InvalidImageError("JPG, PNG, WebP 이미지만 업로드할 수 있습니다.")
            if img.width * img.height > MAX_PIXELS:
                raise InvalidImageError("이미지 해상도가 너무 큽니다.")
            img.seek(0)  # animated WebP/PNG: first frame only
            img.load()
            image = ImageOps.exif_transpose(img)  # apply phone rotation before EXIF is dropped
    except InvalidImageError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise InvalidImageError("이미지 파일을 읽을 수 없습니다.") from exc
    return image


def process_image(data: bytes) -> ProcessedImage:
    image = _decode(data)
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    image = image.convert("RGBA" if has_alpha else "RGB")

    main, (width, height) = _encode(image, MAIN_MAX_SIDE)
    thumb, _ = _encode(image, THUMB_MAX_SIDE)
    return ProcessedImage(main=main, thumb=thumb, width=width, height=height)


def process_avatar(data: bytes) -> bytes:
    """Profile photo: same validation/EXIF stripping, center-cropped to an AVATAR_SIDE square.

    Transparency is flattened onto white so avatars look the same on any background.
    """
    image = _decode(data)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, (255, 255, 255))
        image.paste(rgba, mask=rgba.getchannel("A"))
    else:
        image = image.convert("RGB")
    side = min(AVATAR_SIDE, image.width, image.height)  # crop to square, never upscale tiny images
    square = ImageOps.fit(image, (side, side), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    out = io.BytesIO()
    square.save(out, format="WEBP", quality=WEBP_QUALITY, method=4)
    return out.getvalue()
