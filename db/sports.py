from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base

class Sport(Base):
    __tablename__ = "sports"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    flashscore_link: Mapped[str] = mapped_column(String(500), nullable=True)