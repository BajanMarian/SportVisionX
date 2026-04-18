from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leagues.id"),
        nullable=False,
    )
    flashscore_link: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    winner: Mapped[str | None] = mapped_column(String(200), nullable=True)
