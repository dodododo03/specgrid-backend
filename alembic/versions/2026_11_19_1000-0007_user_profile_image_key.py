"""users.profile_image_url -> profile_image_key

Store a storage key (like product_images) instead of a full URL, so the public URL is built from
MEDIA_BASE_URL at response time and moving to another host/CDN at deploy needs no data rewrite.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nothing ever wrote this column before (no upload feature existed), so drop any stray values
    # rather than misinterpret a URL as a storage key.
    op.execute("UPDATE users SET profile_image_url = NULL")
    op.alter_column(
        'users', 'profile_image_url',
        new_column_name='profile_image_key',
        existing_type=sa.String(2048), type_=sa.String(255), existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'users', 'profile_image_key',
        new_column_name='profile_image_url',
        existing_type=sa.String(255), type_=sa.String(2048), existing_nullable=True,
    )
