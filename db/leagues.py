from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class League(Base):
    __tablename__ = "leagues"
    __table_args__ = (
        UniqueConstraint("sport_id", "country_id", "slug", name="uq_leagues_sport_country_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sport_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sports.id"),
        nullable=False,
    )
    country_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("countries.id"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    flashscore_link: Mapped[str] = mapped_column(String(500), nullable=False)
