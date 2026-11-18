"""users: consent timestamps + withdrawn_at

Records when a member agreed to the 이용약관 / 개인정보 수집·이용 (proof of consent), and when they
withdrew. Members who signed up before consent existed keep NULL.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('terms_agreed_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('privacy_agreed_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('withdrawn_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'withdrawn_at')
    op.drop_column('users', 'privacy_agreed_at')
    op.drop_column('users', 'terms_agreed_at')
