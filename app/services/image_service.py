"""Product photo management: upload, delete, reorder (owner only).

Consistency between files and DB rows:
- upload: every file is validated first (all-or-nothing), files are written, then the DB
  commit happens; if the commit fails the just-written files are removed.
- delete: the DB row is removed first, then the files. A failed file delete leaves an
  orphan file (harmless, can be swept later) but never a row pointing at a missing file.
"""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, InvalidImageError, NotFoundError
from app.core.storage import Storage
from app.models import Product, ProductImage, User
from app.services.image_processing import process_image
from app.services.product_service import get_owned_for_update, load_detail

logger = logging.getLogger(__name__)


def _next_keys(product_id: int) -> tuple[str, str]:
    name = uuid.uuid4().hex
    return f"products/{product_id}/{name}.webp", f"products/{product_id}/{name}_thumb.webp"


def add_images(db: Session, storage: Storage, product_id: int, user: User, uploads: list[bytes]) -> Product:
    if not uploads:
        raise InvalidImageError("업로드할 이미지를 선택해 주세요.")
    product = get_owned_for_update(db, product_id, user)  # row lock serializes concurrent uploads

    existing = db.scalar(select(func.count()).where(ProductImage.product_id == product.id)) or 0
    if existing + len(uploads) > settings.max_images_per_product:
        raise InvalidImageError(
            f"이미지는 상품당 최대 {settings.max_images_per_product}장까지 등록할 수 있습니다. "
            f"(현재 {existing}장)"
        )
    next_order = (
        db.scalar(select(func.max(ProductImage.sort_order)).where(ProductImage.product_id == product.id)) or 0
    )

    processed = [process_image(data) for data in uploads]  # validate everything before writing anything

    written: list[str] = []
    try:
        for offset, image in enumerate(processed, start=1):
            main_key, thumb_key = _next_keys(product.id)
            storage.save(main_key, image.main, "image/webp")
            written.append(main_key)
            storage.save(thumb_key, image.thumb, "image/webp")
            written.append(thumb_key)
            db.add(ProductImage(
                product_id=product.id, storage_key=main_key, thumb_key=thumb_key,
                width=image.width, height=image.height, size_bytes=len(image.main),
                sort_order=next_order + offset,
            ))
        db.commit()
    except Exception:
        db.rollback()
        for key in written:
            storage.delete(key)
        raise
    return load_detail(db, product.id, public_only=False)


def delete_image(db: Session, storage: Storage, product_id: int, image_id: int, user: User) -> Product:
    product = get_owned_for_update(db, product_id, user)
    image = db.scalar(select(ProductImage).where(ProductImage.id == image_id, ProductImage.product_id == product.id))
    if image is None:
        raise NotFoundError("이미지를 찾을 수 없습니다.")
    keys = (image.storage_key, image.thumb_key)
    db.delete(image)
    db.commit()
    for key in keys:
        try:
            storage.delete(key)
        except OSError:
            logger.warning("orphaned media file left behind: %s", key)
    return load_detail(db, product.id, public_only=False)


def reorder_images(db: Session, product_id: int, user: User, image_ids: list[int]) -> Product:
    product = get_owned_for_update(db, product_id, user)
    images = {img.id: img for img in db.scalars(select(ProductImage).where(ProductImage.product_id == product.id))}
    if len(image_ids) != len(set(image_ids)) or set(image_ids) != set(images):
        raise AppError("현재 등록된 모든 이미지 id를 한 번씩 보내 주세요.")
    for position, image_id in enumerate(image_ids, start=1):
        images[image_id].sort_order = position
    db.commit()
    return load_detail(db, product.id, public_only=False)
