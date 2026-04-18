"""convert match odds columns to float

Revision ID: 9b2d3f5c8a11
Revises: ae7f6d3f4c91
Create Date: 2026-04-19 11:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b2d3f5c8a11"
down_revision: Union[str, Sequence[str], None] = "ae7f6d3f4c91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ODDS_COLUMNS = [
    "fortuna_1",
    "fortuna_x",
    "fortuna_2",
    "superbet_1",
    "superbet_x",
    "superbet_2",
    "unibet_1",
    "unibet_x",
    "unibet_2",
]


def upgrade() -> None:
    """Upgrade schema."""
    for column in ODDS_COLUMNS:
        op.alter_column(
            "matches",
            column,
            type_=sa.Float(),
            existing_type=sa.String(length=20),
            postgresql_using=f"NULLIF({column}, '')::double precision",
            existing_nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column in ODDS_COLUMNS:
        op.alter_column(
            "matches",
            column,
            type_=sa.String(length=20),
            existing_type=sa.Float(),
            postgresql_using=f"{column}::text",
            existing_nullable=True,
        )
