"""Profile photo: set / remove (one photo per user).

Same file/DB consistency rules as product photos:
- set: the new file is written first, then the DB commit; if the commit fails the new file is
  removed. The OLD file is deleted only after the commit, so the DB never points at a missing file.
- remove: DB first, then the file (a failed file delete only leaves a harmless orphan).
The user row is locked (SELECT ... FOR UPDATE) so two concurrent uploads can't both "win" and leave
one file orphaned with nobody pointing at it.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.storage import Storage
from app.models import User
from app.services.image_processing import process_avatar

logger = logging.getLogger(__name__)


def _lock_user(db: Session, user: User) -> User:
    # MariaDB 12 snapshot isolation: a FOR UPDATE after an earlier read in the same transaction
    # fails with 1020, and the auth dependency already read this row. End that transaction first.
    db.commit()
    return db.scalars(
        select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True)
    ).one()


def _delete_quietly(storage: Storage, key: str) -> None:
    try:
        storage.delete(key)
    except OSError:
        logger.warning("orphaned media file left behind: %s", key)


def set_profile_image(db: Session, storage: Storage, user: User, data: bytes) -> User:
    avatar = process_avatar(data)  # validate before touching the DB or disk
    locked = _lock_user(db, user)
    old_key = locked.profile_image_key
    new_key = f"users/{locked.id}/{uuid.uuid4().hex}.webp"  # new name each time: no stale browser cache
    try:
        storage.save(new_key, avatar, "image/webp")
        locked.profile_image_key = new_key
        db.commit()
    except Exception:
        db.rollback()
        _delete_quietly(storage, new_key)
        raise
    if old_key:
        _delete_quietly(storage, old_key)
    db.refresh(locked)
    return locked


def remove_profile_image(db: Session, storage: Storage, user: User) -> User:
    locked = _lock_user(db, user)
    old_key = locked.profile_image_key
    if old_key:
        locked.profile_image_key = None
        db.commit()
        _delete_quietly(storage, old_key)
    else:
        db.commit()  # release the row lock
    db.refresh(locked)
    return locked
