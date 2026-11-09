"""initial schema: users, products, product_specs, chat_rooms, chat_messages, user_activity_logs

Revision ID: 0001
Revises:
Create Date: 2026-11-09 12:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of the enum values at this revision (don't import app enums into migrations).
USER_ROLE = ("user", "admin")
USER_STATUS = ("active", "suspended", "withdrawn")
PRODUCT_CATEGORY = (
    "gpu", "cpu", "ram", "storage", "laptop", "desktop",
    "server", "monitor", "keyboard", "audio", "etc",
)
PRODUCT_CONDITION = ("sealed", "like_new", "lightly_used", "used", "for_parts")
PRODUCT_STATUS = ("on_sale", "reserved", "sold", "hidden")
MESSAGE_TYPE = ("text", "image", "system")
ACTIVITY_TYPE = ("view", "search", "chat", "trade", "favorite")

TABLE_OPTS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}

NOW = sa.text("CURRENT_TIMESTAMP")
NOW_ON_UPDATE = sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")


def upgrade() -> None:
    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("nickname", sa.String(30), nullable=False),
        sa.Column("profile_image_url", sa.String(2048), nullable=True),
        sa.Column("role", sa.Enum(*USER_ROLE, name="user_role"), server_default="user", nullable=False),
        sa.Column("status", sa.Enum(*USER_STATUS, name="user_status"), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=NOW_ON_UPDATE, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("nickname", name="uq_users_nickname"),
        **TABLE_OPTS,
    )

    # ------------------------------------------------------------- products
    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("seller_id", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.Enum(*PRODUCT_CATEGORY, name="product_category"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("condition", sa.Enum(*PRODUCT_CONDITION, name="product_condition"), nullable=False),
        sa.Column("status", sa.Enum(*PRODUCT_STATUS, name="product_status"), server_default="on_sale", nullable=False),
        sa.Column("is_hot_deal", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("thumbnail_url", sa.String(2048), nullable=True),
        sa.Column("trade_location", sa.String(100), nullable=True),
        sa.Column("view_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=NOW_ON_UPDATE, nullable=False),
        sa.CheckConstraint("price >= 0", name=op.f("ck_products_price_non_negative")),
        sa.CheckConstraint("view_count >= 0", name=op.f("ck_products_view_count_non_negative")),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], name="fk_products_seller_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        **TABLE_OPTS,
    )
    op.create_index("ix_products_seller_id", "products", ["seller_id"])
    op.create_index("ix_products_category_status_created_at", "products", ["category", "status", "created_at"])
    op.create_index("ix_products_status_price", "products", ["status", "price"])

    # -------------------------------------------------------- product_specs
    op.create_table(
        "product_specs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("manufacturer", sa.String(100), nullable=True),
        sa.Column("model_name", sa.String(150), nullable=True),
        sa.Column("cpu_model", sa.String(120), nullable=True),
        sa.Column("cpu_cores", sa.SmallInteger(), nullable=True),
        sa.Column("ram_gb", sa.Integer(), nullable=True),
        sa.Column("gpu_model", sa.String(120), nullable=True),
        sa.Column("vram_gb", sa.SmallInteger(), nullable=True),
        sa.Column("storage_gb", sa.Integer(), nullable=True),
        sa.Column("storage_type", sa.String(20), nullable=True),
        sa.Column("extra_specs", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_product_specs_product_id_products", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_product_specs"),
        sa.UniqueConstraint("product_id", name="uq_product_specs_product_id"),
        **TABLE_OPTS,
    )
    op.create_index("ix_product_specs_manufacturer", "product_specs", ["manufacturer"])
    op.create_index("ix_product_specs_cpu_model", "product_specs", ["cpu_model"])
    op.create_index("ix_product_specs_gpu_model", "product_specs", ["gpu_model"])
    op.create_index("ix_product_specs_ram_gb", "product_specs", ["ram_gb"])
    op.create_index("ix_product_specs_vram_gb", "product_specs", ["vram_gb"])

    # ----------------------------------------------------------- chat_rooms
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=False),
        sa.Column("buyer_id", sa.BigInteger(), nullable=False),
        sa.Column("seller_id", sa.BigInteger(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=NOW_ON_UPDATE, nullable=False),
        sa.CheckConstraint("buyer_id <> seller_id", name=op.f("ck_chat_rooms_buyer_not_seller")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_chat_rooms_product_id_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], name="fk_chat_rooms_buyer_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"], name="fk_chat_rooms_seller_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_rooms"),
        sa.UniqueConstraint("product_id", "buyer_id", name="uq_chat_rooms_product_id_buyer_id"),
        **TABLE_OPTS,
    )
    op.create_index("ix_chat_rooms_buyer_id_last_message_at", "chat_rooms", ["buyer_id", "last_message_at"])
    op.create_index("ix_chat_rooms_seller_id_last_message_at", "chat_rooms", ["seller_id", "last_message_at"])

    # -------------------------------------------------------- chat_messages
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("room_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("message_type", sa.Enum(*MESSAGE_TYPE, name="message_type"), server_default="text", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], name="fk_chat_messages_room_id_chat_rooms", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_chat_messages_sender_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_chat_messages"),
        **TABLE_OPTS,
    )
    op.create_index("ix_chat_messages_room_id_id", "chat_messages", ["room_id", "id"])
    op.create_index("ix_chat_messages_sender_id", "chat_messages", ["sender_id"])

    # --------------------------------------------------- user_activity_logs
    op.create_table(
        "user_activity_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("session_id", sa.String(128), nullable=True),
        sa.Column("activity_type", sa.Enum(*ACTIVITY_TYPE, name="activity_type"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), nullable=True),
        sa.Column("search_keyword", sa.String(200), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_activity_logs_user_id_users", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_user_activity_logs_product_id_products", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_user_activity_logs"),
        **TABLE_OPTS,
    )
    op.create_index("ix_user_activity_logs_user_id_created_at", "user_activity_logs", ["user_id", "created_at"])
    op.create_index("ix_user_activity_logs_activity_type_created_at", "user_activity_logs", ["activity_type", "created_at"])
    op.create_index("ix_user_activity_logs_session_id", "user_activity_logs", ["session_id"])
    op.create_index("ix_user_activity_logs_product_id", "user_activity_logs", ["product_id"])


def downgrade() -> None:
    # Reverse dependency order: children first.
    op.drop_table("user_activity_logs")
    op.drop_table("chat_messages")
    op.drop_table("chat_rooms")
    op.drop_table("product_specs")
    op.drop_table("products")
    op.drop_table("users")
