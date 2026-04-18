"""add round and unibet to matches

Revision ID: ae7f6d3f4c91
Revises: 6b0fbb34a2c1
Create Date: 2026-04-18 23:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ae7f6d3f4c91"
down_revision: Union[str, Sequence[str], None] = "6b0fbb34a2c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("matches", sa.Column("round_label", sa.String(length=120), nullable=True))
    op.add_column("matches", sa.Column("unibet_1", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("unibet_x", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("unibet_2", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("matches", "unibet_2")
    op.drop_column("matches", "unibet_x")
    op.drop_column("matches", "unibet_1")
    op.drop_column("matches", "round_label")
