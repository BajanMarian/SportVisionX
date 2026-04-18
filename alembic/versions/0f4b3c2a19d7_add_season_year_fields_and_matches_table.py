"""add season year fields and matches table

Revision ID: 0f4b3c2a19d7
Revises: e9d26f14bb97
Create Date: 2026-04-18 22:05:00.000000

"""

from typing import Sequence, Union
import re
from urllib.parse import urlparse

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f4b3c2a19d7"
down_revision: Union[str, Sequence[str], None] = "e9d26f14bb97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEASON_PATTERN = re.compile(r"(20\d{2})-(20\d{2})(?:/)?$")


def _extract_years(flashscore_link: str) -> tuple[str | None, int | None, int | None]:
    path = urlparse(flashscore_link or "").path
    match = SEASON_PATTERN.search(path)
    if not match:
        return None, None, None

    start_year = int(match.group(1))
    end_year = int(match.group(2))
    return f"{start_year}-{end_year}", start_year, end_year


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("seasons", sa.Column("season_years", sa.String(length=9), nullable=True))
    op.add_column("seasons", sa.Column("start_year_season", sa.Integer(), nullable=True))
    op.add_column("seasons", sa.Column("end_year_season", sa.Integer(), nullable=True))

    seasons_table = sa.table(
        "seasons",
        sa.column("id", sa.Integer()),
        sa.column("flashscore_link", sa.String()),
        sa.column("season_years", sa.String()),
        sa.column("start_year_season", sa.Integer()),
        sa.column("end_year_season", sa.Integer()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(seasons_table.c.id, seasons_table.c.flashscore_link)
    ).fetchall()

    for row in rows:
        season_years, start_year, end_year = _extract_years(row.flashscore_link)
        if season_years is None:
            continue
        connection.execute(
            sa.update(seasons_table)
            .where(seasons_table.c.id == row.id)
            .values(
                season_years=season_years,
                start_year_season=start_year,
                end_year_season=end_year,
            )
        )

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(length=50), nullable=True),
        sa.Column("flashscore_link", sa.String(length=500), nullable=False),
        sa.Column("kickoff_datetime_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_date_label", sa.String(length=40), nullable=True),
        sa.Column("home_team", sa.String(length=200), nullable=False),
        sa.Column("away_team", sa.String(length=200), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "flashscore_link", name="uq_matches_season_flashscore_link"),
    )
    op.create_index("ix_matches_season_id", "matches", ["season_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_matches_season_id", table_name="matches")
    op.drop_table("matches")
    op.drop_column("seasons", "end_year_season")
    op.drop_column("seasons", "start_year_season")
    op.drop_column("seasons", "season_years")
