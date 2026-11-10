"""찜 (favorites).

PUT/DELETE are idempotent: pressing the heart twice is not an error, and the count only changes
when a row was really added/removed. The favorites row and products.favorite_count change in the
same transaction, so the counter can't drift:

  add:    INSERT favorites ...;  UPDATE products SET favorite_count = favorite_count + 1
          (a concurrent duplicate INSERT hits the unique key -> rolled back, count untouched)
  remove: DELETE favorites ...;  only if a row was deleted -> favorite_count - 1
"""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models import Favorite, Product, User
from app.models.enums import ProductStatus

NOT_FOUND = "상품을 찾을 수 없습니다."


def _count(db: Session, product_id: int) -> int:
    return db.scalar(
        select(Product.favorite_count).where(Product.id == product_id).execution_options(populate_existing=True)
    ) or 0


def add(db: Session, user: User, product_id: int) -> tuple[bool, int]:
    """Returns (newly_added, favorite_count)."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id, Product.deleted_at.is_(None), Product.status != ProductStatus.HIDDEN
        )
    )
    if product is None:
        raise NotFoundError(NOT_FOUND)
    if product.seller_id == user.id:
        raise AppError("본인 상품은 찜할 수 없습니다.")

    already = db.scalar(select(Favorite.id).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    if already is not None:
        db.commit()
        return False, _count(db, product_id)
    if product.status == ProductStatus.SOLD:
        raise ConflictError("판매 완료된 상품은 찜할 수 없습니다.")

    db.add(Favorite(user_id=user.id, product_id=product_id))
    try:
        db.flush()
    except IntegrityError:  # the same user's other request inserted it a moment ago
        db.rollback()
        return False, _count(db, product_id)
    db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(favorite_count=Product.favorite_count + 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return True, _count(db, product_id)


def remove(db: Session, user: User, product_id: int) -> tuple[bool, int]:
    """Returns (actually_removed, favorite_count). Works even if the product was sold/hidden/deleted."""
    existing = db.scalar(
        select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id).with_for_update()
    )
    if existing is None:
        if db.scalar(select(Product.id).where(Product.id == product_id)) is None:
            db.rollback()
            raise NotFoundError(NOT_FOUND)
        db.commit()
        return False, _count(db, product_id)

    db.delete(existing)
    db.execute(
        update(Product)
        .where(Product.id == product_id, Product.favorite_count > 0)
        .values(favorite_count=Product.favorite_count - 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return True, _count(db, product_id)


def favorited_ids(db: Session, user: User | None, product_ids: list[int]) -> set[int]:
    """Which of these products the user has hearted — one query for a whole page of cards."""
    if user is None or not product_ids:
        return set()
    return set(db.scalars(
        select(Favorite.product_id).where(Favorite.user_id == user.id, Favorite.product_id.in_(product_ids))
    ))


def list_mine(db: Session, user: User, page: int, size: int) -> tuple[list[Product], int]:
    """내 찜 목록, most recently hearted first. Deleted/hidden products drop out; sold ones stay."""
    base = (
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(
            Favorite.user_id == user.id,
            Product.deleted_at.is_(None),
            Product.status != ProductStatus.HIDDEN,
        )
    )
    total = db.scalar(select(func.count()).select_from(base.with_only_columns(Product.id).subquery()))
    items = db.scalars(
        base.options(joinedload(Product.spec))
        .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).unique().all()
    return list(items), total or 0
