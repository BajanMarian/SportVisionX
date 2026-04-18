from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("season_id", "flashscore_link", name="uq_matches_season_flashscore_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("seasons.id"),
        nullable=False,
    )
    event_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    flashscore_link: Mapped[str] = mapped_column(String(500), nullable=False)
    match_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    round_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kickoff_datetime_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    kickoff_hour_utc: Mapped[str | None] = mapped_column(String(5), nullable=True)
    home_team: Mapped[str] = mapped_column(String(200), nullable=False)
    away_team: Mapped[str] = mapped_column(String(200), nullable=False)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intermediate_scores: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_score: Mapped[str | None] = mapped_column(String(20), nullable=True)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)
    yellow_cards: Mapped[str | None] = mapped_column(Text, nullable=True)
    red_cards: Mapped[str | None] = mapped_column(Text, nullable=True)
    referee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    referee_country_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stadium: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attendance: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fortuna_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    fortuna_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    fortuna_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    superbet_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    superbet_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    superbet_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    unibet_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    unibet_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    unibet_2: Mapped[float | None] = mapped_column(Float, nullable=True)
    crawl_error: Mapped[str | None] = mapped_column(Text, nullable=True)
