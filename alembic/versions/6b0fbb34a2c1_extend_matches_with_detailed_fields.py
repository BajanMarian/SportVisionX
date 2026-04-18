"""extend matches with detailed fields

Revision ID: 6b0fbb34a2c1
Revises: 0f4b3c2a19d7
Create Date: 2026-04-18 23:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b0fbb34a2c1"
down_revision: Union[str, Sequence[str], None] = "0f4b3c2a19d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("matches", "match_date_label", new_column_name="match_date")
    op.add_column("matches", sa.Column("kickoff_hour_utc", sa.String(length=5), nullable=True))
    op.add_column("matches", sa.Column("intermediate_scores", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("final_score", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("goals", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("yellow_cards", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("red_cards", sa.Text(), nullable=True))
    op.add_column("matches", sa.Column("referee", sa.String(length=200), nullable=True))
    op.add_column("matches", sa.Column("referee_country_code", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("stadium", sa.String(length=200), nullable=True))
    op.add_column("matches", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("matches", sa.Column("attendance", sa.String(length=50), nullable=True))
    op.add_column("matches", sa.Column("capacity", sa.String(length=50), nullable=True))
    op.add_column("matches", sa.Column("fortuna_1", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("fortuna_x", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("fortuna_2", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("superbet_1", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("superbet_x", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("superbet_2", sa.String(length=20), nullable=True))
    op.add_column("matches", sa.Column("crawl_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("matches", "crawl_error")
    op.drop_column("matches", "superbet_2")
    op.drop_column("matches", "superbet_x")
    op.drop_column("matches", "superbet_1")
    op.drop_column("matches", "fortuna_2")
    op.drop_column("matches", "fortuna_x")
    op.drop_column("matches", "fortuna_1")
    op.drop_column("matches", "capacity")
    op.drop_column("matches", "attendance")
    op.drop_column("matches", "city")
    op.drop_column("matches", "stadium")
    op.drop_column("matches", "referee_country_code")
    op.drop_column("matches", "referee")
    op.drop_column("matches", "red_cards")
    op.drop_column("matches", "yellow_cards")
    op.drop_column("matches", "goals")
    op.drop_column("matches", "final_score")
    op.drop_column("matches", "intermediate_scores")
    op.drop_column("matches", "kickoff_hour_utc")
    op.alter_column("matches", "match_date", new_column_name="match_date_label")
