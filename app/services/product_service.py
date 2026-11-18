from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Product, ProductSpec, User
from app.models.enums import ProductStatus
from app.schemas.product import (
    MyProductParams,
    ProductCreate,
    ProductSearchParams,
    ProductSort,
    ProductStatusUpdate,
    ProductUpdate,
    TradePoint,
)
from app.services import trade_service
from app.services.manufacturer_aliases import search_terms

NOT_FOUND = "상품을 찾을 수 없습니다."
IN_TRADE = "예약중인 거래가 있습니다. 거래를 완료하거나 취소한 뒤 다시 시도해 주세요."

_ORDER_BY = {
    ProductSort.LATEST: (Product.created_at.desc(), Product.id.desc()),
    ProductSort.PRICE_ASC: (Product.price.asc(), Product.id.desc()),
    ProductSort.PRICE_DESC: (Product.price.desc(), Product.id.desc()),
    ProductSort.POPULAR: (Product.view_count.desc(), Product.id.desc()),
}


def create_product(db: Session, seller: User, data: ProductCreate) -> Product:
    product = Product(
        seller_id=seller.id,
        category=data.category,
        title=data.title,
        description=data.description,
        price=data.price,
        condition=data.condition,
        trade_location=data.trade_location,
    )
    _set_point(product, data.trade_point)
    if data.spec is not None:
        product.spec = ProductSpec(**data.spec.model_dump())
    db.add(product)
    db.commit()
    return load_detail(db, product.id, public_only=False)


def _set_point(product: Product, point: TradePoint | None) -> None:
    product.trade_lat = point.lat if point else None
    product.trade_lng = point.lng if point else None


def _visible() -> list:
    return [Product.deleted_at.is_(None), Product.status != ProductStatus.HIDDEN]


def load_detail(db: Session, product_id: int, *, public_only: bool) -> Product:
    conditions = [Product.id == product_id, Product.deleted_at.is_(None)]
    if public_only:
        conditions.append(Product.status != ProductStatus.HIDDEN)
    product = db.scalar(
        select(Product)
        .options(joinedload(Product.spec), joinedload(Product.seller))
        .where(*conditions)
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise NotFoundError(NOT_FOUND)
    return product


def get_public_product(db: Session, product_id: int) -> Product:
    """Public detail view (404 for missing / hidden / deleted). Doesn't touch view_count."""
    return load_detail(db, product_id, public_only=True)


def increment_view_count(db: Session, product_id: int) -> Product:
    """Atomic +1 in the DB (no lost updates under concurrent views), then the fresh row."""
    db.execute(
        update(Product)
        .where(Product.id == product_id)
        .values(view_count=Product.view_count + 1)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return load_detail(db, product_id, public_only=True)


def get_owned_for_update(db: Session, product_id: int, user: User) -> Product:
    """Lock the row (SELECT ... FOR UPDATE) so concurrent edits by the owner don't interleave."""
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
        .with_for_update()
    )
    if product is None:
        raise NotFoundError(NOT_FOUND)
    if product.seller_id != user.id:
        raise PermissionDeniedError("본인이 등록한 상품만 수정할 수 있습니다.")
    return product


def update_product(db: Session, product_id: int, user: User, data: ProductUpdate) -> Product:
    product = get_owned_for_update(db, product_id, user)
    old_location = product.trade_location

    for field, value in data.model_dump(exclude_unset=True, exclude={"spec", "trade_point"}).items():
        setattr(product, field, value)

    if "trade_point" in data.model_fields_set:
        _set_point(product, data.trade_point)
    elif "trade_location" in data.model_fields_set and data.trade_location != old_location:
        _set_point(product, None)  # the place changed without a new pin: the old pin would mislead

    if "spec" in data.model_fields_set:
        if data.spec is None:
            product.spec = None  # delete-orphan removes the row
        else:
            changes = data.spec.model_dump(exclude_unset=True)
            if product.spec is None:
                product.spec = ProductSpec(**changes)
            else:
                for field, value in changes.items():
                    setattr(product.spec, field, value)

    db.commit()
    return load_detail(db, product_id, public_only=False)


def change_status(db: Session, product_id: int, user: User, data: ProductStatusUpdate) -> Product:
    product = get_owned_for_update(db, product_id, user)
    # The row lock above also serializes us with trade_service, which locks the same row.
    if data.status != product.status and trade_service.has_accepted_trade(db, product_id):
        db.rollback()
        raise ConflictError(IN_TRADE)  # reserved/sold must follow the trade, not be set by hand
    product.status = data.status
    db.commit()
    return load_detail(db, product_id, public_only=False)


def delete_product(db: Session, product_id: int, user: User) -> None:
    """Soft delete: the row stays for chat/activity history but disappears everywhere in the API."""
    product = get_owned_for_update(db, product_id, user)
    if trade_service.has_accepted_trade(db, product_id):
        db.rollback()
        raise ConflictError(IN_TRADE)
    trade_service.reject_open_requests(db, product_id)
    product.deleted_at = func.now()
    db.commit()


def list_my_products(db: Session, user: User, params: MyProductParams) -> tuple[list[Product], int]:
    stmt = select(Product).where(Product.seller_id == user.id, Product.deleted_at.is_(None))
    if params.status:
        stmt = stmt.where(Product.status == params.status)
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Product.id).subquery()))
    items = db.scalars(
        stmt.options(joinedload(Product.spec))
        .order_by(Product.created_at.desc(), Product.id.desc())
        .limit(params.size)
        .offset((params.page - 1) * params.size)
    ).all()
    return list(items), total or 0


def _apply_filters(stmt: Select, p: ProductSearchParams) -> Select:
    stmt = stmt.where(*_visible())
    if not p.include_sold:
        stmt = stmt.where(Product.status == ProductStatus.ON_SALE)
    if p.q:
        stmt = stmt.where(Product.title.contains(p.q, autoescape=True))
    if p.category:
        stmt = stmt.where(Product.category == p.category)
    if p.condition:
        stmt = stmt.where(Product.condition.in_(p.condition))
    if p.min_price is not None:
        stmt = stmt.where(Product.price >= p.min_price)
    if p.max_price is not None:
        stmt = stmt.where(Product.price <= p.max_price)
    if p.hot_only:
        stmt = stmt.where(Product.is_hot_deal.is_(True))

    spec_filters = []
    if p.manufacturer:
        spec_filters.append(or_(*(
            ProductSpec.manufacturer.contains(term, autoescape=True) for term in search_terms(p.manufacturer)
        )))
    if p.cpu:
        spec_filters.append(ProductSpec.cpu_model.contains(p.cpu, autoescape=True))
    if p.gpu:
        spec_filters.append(ProductSpec.gpu_model.contains(p.gpu, autoescape=True))
    if p.min_cores is not None:
        spec_filters.append(ProductSpec.cpu_cores >= p.min_cores)
    if p.min_ram_gb is not None:
        spec_filters.append(ProductSpec.ram_gb >= p.min_ram_gb)
    if p.min_vram_gb is not None:
        spec_filters.append(ProductSpec.vram_gb >= p.min_vram_gb)
    if p.min_storage_gb is not None:
        spec_filters.append(ProductSpec.storage_gb >= p.min_storage_gb)
    if spec_filters:
        # Inner join only when filtering by spec: products without specs can't match a spec filter.
        stmt = stmt.join(Product.spec).where(*spec_filters)
    return stmt


def search_products(db: Session, params: ProductSearchParams) -> tuple[list[Product], int]:
    base = _apply_filters(select(Product), params)
    total = db.scalar(select(func.count()).select_from(base.with_only_columns(Product.id).subquery()))
    items = db.scalars(
        base.options(joinedload(Product.spec))
        .order_by(*_ORDER_BY[params.sort])
        .limit(params.size)
        .offset((params.page - 1) * params.size)
    ).all()
    return list(items), total or 0
