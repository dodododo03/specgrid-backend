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
