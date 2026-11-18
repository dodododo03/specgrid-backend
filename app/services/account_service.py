"""회원 탈퇴 (account withdrawal).

What happens (this is what the 개인정보처리방침 promises — keep the two in sync):
- Personal data on the account is destroyed right away: email, password hash and profile photo are
  removed, and the nickname becomes "탈퇴회원#<id>". The row itself stays (status=withdrawn) because
  other members' chats and trades reference it; with the identifying fields gone it is anonymous.
  Nicknames can't contain '#', so the placeholder can never collide with a real member.
- The member's listings are deleted (soft delete, like a normal delete) and their photos removed;
  pending purchase requests on them are rejected, and their own pending requests are canceled.
- Their 찜 are removed (and the products' favorite counts adjusted).
- Every session is logged out.
- Kept: chat messages and finished trade records, because they are also the other party's record.
  Activity logs are append-only for the app account; scripts/purge_activity_logs.py anonymizes them
  after 30 days and deletes them after 180, as for everyone.

Withdrawal is refused while a trade is ACCEPTED (상품 예약중): the other party is mid-deal.
"""

import logging

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError
from app.core.security import verify_password
from app.core.storage import Storage
from app.models import Favorite, Product, ProductImage, Trade, User
from app.models.enums import TradeStatus, UserStatus
from app.services.login_limiter import LoginLimiter
from app.services.token_store import TokenStore

logger = logging.getLogger(__name__)

WRONG_PASSWORD = "비밀번호가 올바르지 않습니다."
IN_TRADE = "예약중인 거래가 있어 탈퇴할 수 없습니다. 거래를 완료하거나 취소한 뒤 다시 시도해 주세요."


class WrongPasswordError(AppError):
    # Not 401: the browser would treat that as "session expired" and log out instead of showing the message.
    status_code = 400
    code = "wrong_password"


def withdraw(
    db: Session, storage: Storage, store: TokenStore, limiter: LoginLimiter, user: User, password: str, client_ip: str
) -> None:
    # Same brute-force budget as login: a stolen access token must not become a password oracle.
    limiter.ensure_allowed(user.email, client_ip)
    if not verify_password(password, user.password_hash):
        limiter.record_failure(user.email, client_ip)
        raise WrongPasswordError(WRONG_PASSWORD)

    # MariaDB 12 snapshot isolation: FOR UPDATE after an earlier read in the same transaction fails
    # (1020) — the auth dependency already read this row, so end that transaction first.
    db.commit()
    me = db.scalars(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    ).one()
    if me.status != UserStatus.ACTIVE:
        db.rollback()
        raise ConflictError("이미 탈퇴했거나 이용이 제한된 계정입니다.")

    my_products = select(Product.id).where(Product.seller_id == me.id).scalar_subquery()
    # Lock my products too, so a concurrent "accept" can't slip in between the check and the delete.
    db.scalars(select(Product.id).where(Product.seller_id == me.id).with_for_update()).all()
    accepted = db.scalar(
        select(Trade.id).where(
            Trade.status == TradeStatus.ACCEPTED, (Trade.buyer_id == me.id) | (Trade.seller_id == me.id)
        ).limit(1)
    )
    if accepted is not None:
        db.rollback()
        raise ConflictError(IN_TRADE)

    now = func.now()
    # Pending requests: mine as buyer -> canceled; others' on my products -> rejected.
    db.execute(
        update(Trade)
        .where(Trade.buyer_id == me.id, Trade.status == TradeStatus.REQUESTED)
        .values(status=TradeStatus.CANCELED)  # same as a buyer's own cancel
        .execution_options(synchronize_session=False)
    )
    db.execute(
        update(Trade)
        .where(Trade.seller_id == me.id, Trade.status == TradeStatus.REQUESTED)
        .values(status=TradeStatus.REJECTED, responded_at=now)
        .execution_options(synchronize_session=False)
    )

    # My listings: soft delete + photos (files are removed after the commit).
    image_keys = [
        key
        for row in db.execute(
            select(ProductImage.storage_key, ProductImage.thumb_key).where(ProductImage.product_id.in_(my_products))
        )
        for key in row
    ]
    db.execute(delete(ProductImage).where(ProductImage.product_id.in_(my_products)).execution_options(
        synchronize_session=False))
    db.execute(
        update(Product)
        .where(Product.seller_id == me.id, Product.deleted_at.is_(None))
        .values(deleted_at=now)
        .execution_options(synchronize_session=False)
    )

    # My 찜: keep the products' counters consistent with the rows we delete.
    db.execute(
        update(Product)
        .where(
            Product.id.in_(select(Favorite.product_id).where(Favorite.user_id == me.id).scalar_subquery()),
            Product.favorite_count > 0,
        )
        .values(favorite_count=Product.favorite_count - 1)
        .execution_options(synchronize_session=False)
    )
    db.execute(delete(Favorite).where(Favorite.user_id == me.id).execution_options(synchronize_session=False))

    # The account itself: destroy identifying data, keep an anonymous row for others' history.
    if me.profile_image_key:
        image_keys.append(me.profile_image_key)
    me.email = f"withdrawn-{me.id}@withdrawn.invalid"  # .invalid is reserved: can never be a real address
    me.nickname = f"탈퇴회원#{me.id}"
    me.password_hash = None
    me.profile_image_key = None
    me.last_login_at = None
    me.status = UserStatus.WITHDRAWN
    me.withdrawn_at = now
    db.commit()

    store.bump_generation(me.id)  # log out everywhere (access + refresh tokens)
    for key in image_keys:
        try:
            storage.delete(key)
        except OSError:
            logger.warning("orphaned media file left behind: %s", key)
