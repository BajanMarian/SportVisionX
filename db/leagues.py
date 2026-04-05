from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class League(Base):
    __tablename__ = "leagues"

    sport_name: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("sports.name"),
        primary_key=True,
    )
    country: Mapped[str] = mapped_column(String(100), primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    flashscore_link: Mapped[str] = mapped_column(String(500), nullable=False)
