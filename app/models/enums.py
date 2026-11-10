from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    WITHDRAWN = "withdrawn"


class ProductCategory(StrEnum):
    GPU = "gpu"
    CPU = "cpu"
    RAM = "ram"
    STORAGE = "storage"
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    SERVER = "server"
    MONITOR = "monitor"
    KEYBOARD = "keyboard"
    AUDIO = "audio"
    ETC = "etc"


class ProductCondition(StrEnum):
    SEALED = "sealed"              # 미개봉
    LIKE_NEW = "like_new"          # 거의 새것
    LIGHTLY_USED = "lightly_used"  # 사용감 적음
    USED = "used"                  # 사용감 있음
    FOR_PARTS = "for_parts"        # 부품용/고장


class ProductStatus(StrEnum):
    ON_SALE = "on_sale"
    RESERVED = "reserved"
    SOLD = "sold"
    HIDDEN = "hidden"


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    SYSTEM = "system"


class ActivityType(StrEnum):
    VIEW = "view"
    SEARCH = "search"
    CHAT = "chat"
    TRADE = "trade"
    FAVORITE = "favorite"


class TradeStatus(StrEnum):
    REQUESTED = "requested"  # 구매 요청 (판매자 응답 대기)
    ACCEPTED = "accepted"    # 판매자 수락 -> 상품 예약중
    REJECTED = "rejected"    # 판매자 거절 (또는 다른 사람과 거래 완료되어 자동 거절)
    CANCELED = "canceled"    # 구매자 취소, 또는 수락 후 판매자 취소
    COMPLETED = "completed"  # 거래 완료 -> 상품 판매완료


ACTIVE_TRADE_STATUSES = (TradeStatus.REQUESTED, TradeStatus.ACCEPTED)
