import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from db.countries import Country
from db.leagues import League
from db.seasons import Season
from db.sports import Sport

DEFAULT_ENV_FILE = ".env.production"
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


def load_database_url(env_file: str) -> str:
    load_dotenv(Path.cwd() / env_file)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(f"DATABASE_URL is not set in {env_file}")
    return database_url


def build_session_factory(env_file: str) -> tuple[sessionmaker, object]:
    database_url = load_database_url(env_file)
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(bind=engine), engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    env_file = os.getenv("SPORTVISIONX_ENV_FILE", DEFAULT_ENV_FILE)
    session_factory, engine = build_session_factory(env_file)
    app.state.session_factory = session_factory
    app.state.engine = engine
    yield
    engine.dispose()


app = FastAPI(title="SportVisionX API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        yield session


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def get_summary(session: Session = Depends(get_db_session)) -> dict[str, int]:
    return {
        "sports_count": int(session.scalar(select(func.count()).select_from(Sport)) or 0),
        "countries_count": int(session.scalar(select(func.count()).select_from(Country)) or 0),
        "leagues_count": int(session.scalar(select(func.count()).select_from(League)) or 0),
        "seasons_count": int(session.scalar(select(func.count()).select_from(Season)) or 0),
    }


@app.get("/api/sports")
def get_sports(session: Session = Depends(get_db_session)) -> list[dict]:
    statement = (
        select(
            Sport.id,
            Sport.name,
            Sport.flashscore_link,
            func.count(func.distinct(League.id)).label("league_count"),
            func.count(func.distinct(Season.id)).label("season_count"),
        )
        .select_from(Sport)
        .outerjoin(League, League.sport_id == Sport.id)
        .outerjoin(Season, Season.league_id == League.id)
        .group_by(Sport.id)
        .order_by(Sport.name.asc())
    )
    rows = session.execute(statement).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "flashscore_link": row.flashscore_link,
            "league_count": int(row.league_count or 0),
            "season_count": int(row.season_count or 0),
        }
        for row in rows
    ]


@app.get("/api/sports/{sport_id}/leagues")
def get_leagues_for_sport(
    sport_id: int,
    session: Session = Depends(get_db_session),
) -> list[dict]:
    sport_exists = session.scalar(select(func.count()).select_from(Sport).where(Sport.id == sport_id))
    if not sport_exists:
        raise HTTPException(status_code=404, detail=f"Sport id={sport_id} was not found")

    statement = (
        select(
            League.id,
            League.name,
            League.slug,
            League.flashscore_link,
            Country.name.label("country_name"),
            func.count(Season.id).label("season_count"),
        )
        .select_from(League)
        .join(Country, Country.id == League.country_id)
        .outerjoin(Season, Season.league_id == League.id)
        .where(League.sport_id == sport_id)
        .group_by(League.id, Country.name)
        .order_by(Country.name.asc(), League.name.asc())
    )
    rows = session.execute(statement).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "flashscore_link": row.flashscore_link,
            "country_name": row.country_name,
            "season_count": int(row.season_count or 0),
        }
        for row in rows
    ]


@app.get("/api/sports/by-name/{sport_name}/leagues")
def get_leagues_for_sport_name(
    sport_name: str,
    session: Session = Depends(get_db_session),
) -> list[dict]:
    sport = session.scalar(select(Sport).where(func.lower(Sport.name) == sport_name.lower()))
    if sport is None:
        raise HTTPException(status_code=404, detail=f"Sport name='{sport_name}' was not found")
    return get_leagues_for_sport(sport.id, session)


@app.get("/api/leagues/{league_id}/seasons")
def get_seasons_for_league(
    league_id: int,
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[dict]:
    league_exists = session.scalar(select(func.count()).select_from(League).where(League.id == league_id))
    if not league_exists:
        raise HTTPException(status_code=404, detail=f"League id={league_id} was not found")

    statement = (
        select(Season.id, Season.flashscore_link, Season.winner)
        .where(Season.league_id == league_id)
        .order_by(Season.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        {
            "id": row.id,
            "flashscore_link": row.flashscore_link,
            "winner": row.winner,
        }
        for row in rows
    ]


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
