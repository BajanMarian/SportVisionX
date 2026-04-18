import os
import csv
import io
import re
import asyncio
from datetime import datetime, timezone
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.match_results import (
    MatchRow,
    extract_season_label,
    fetch_matches_from_season_url,
)
from app.match_details import fetch_detailed_matches_from_season_url
from db.countries import Country
from db.leagues import League
from db.matches import Match
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

    matches_by_season = (
        select(
            Match.season_id.label("season_id"),
            func.count(Match.id).label("matches_count"),
        )
        .group_by(Match.season_id)
        .subquery()
    )

    statement = (
        select(
            Season.id,
            Season.flashscore_link,
            Season.winner,
            Season.season_years,
            Season.start_year_season,
            Season.end_year_season,
            func.coalesce(matches_by_season.c.matches_count, 0).label("matches_count"),
        )
        .outerjoin(matches_by_season, matches_by_season.c.season_id == Season.id)
        .where(Season.league_id == league_id)
        .order_by(
            Season.end_year_season.desc().nullslast(),
            Season.start_year_season.desc().nullslast(),
            Season.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        {
            "id": row.id,
            "flashscore_link": row.flashscore_link,
            "winner": row.winner,
            "season_years": row.season_years,
            "start_year_season": row.start_year_season,
            "end_year_season": row.end_year_season,
            "matches_count": int(row.matches_count or 0),
            "matches_downloaded": int(row.matches_count or 0) > 0,
        }
        for row in rows
    ]


def _pick_latest_season(seasons: list[Season]) -> Season:
    def season_key(season: Season) -> tuple[int, int, int, int]:
        if season.start_year_season is not None and season.end_year_season is not None:
            return (2, season.end_year_season, season.start_year_season, season.id)

        label = extract_season_label(season.flashscore_link)
        match = re.match(r"^(\d{4})-(\d{4})$", label)
        if not match:
            return (0, 0, 0, season.id)
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        return (1, end_year, start_year, season.id)

    return max(seasons, key=season_key)


def _build_matches_csv(rows: list[MatchRow]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "home_team", "away_team", "home_score", "away_score"])
    for row in rows:
        writer.writerow([row.date, row.home_team, row.away_team, row.home_score, row.away_score])
    return "\ufeff" + buffer.getvalue()


def _build_detailed_matches_csv(rows: list[dict[str, str]]) -> str:
    columns = [
        "event_id",
        "match_link",
        "match_date",
        "kickoff_datetime_utc",
        "kickoff_hour_utc",
        "home_team",
        "away_team",
        "intermediate_scores",
        "final_score",
        "goals",
        "yellow_cards",
        "red_cards",
        "referee",
        "referee_country_code",
        "stadium",
        "city",
        "attendance",
        "capacity",
        "fortuna_1",
        "fortuna_x",
        "fortuna_2",
        "superbet_1",
        "superbet_x",
        "superbet_2",
        "error",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return "\ufeff" + buffer.getvalue()


def _parse_final_score(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    match = re.search(r"^\s*(\d+)\s*-\s*(\d+)\s*$", value)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _parse_kickoff_datetime_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC")
        return parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _normalize_match_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc}{path}{query}"


@app.get("/api/leagues/{league_id}/matches.csv")
async def download_matches_csv_for_league(
    league_id: int,
    season_id: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db_session),
) -> StreamingResponse:
    league = session.scalar(select(League).where(League.id == league_id))
    if league is None:
        raise HTTPException(status_code=404, detail=f"League id={league_id} was not found")

    if season_id is not None:
        season = session.scalar(
            select(Season).where(Season.id == season_id, Season.league_id == league_id)
        )
        if season is None:
            raise HTTPException(
                status_code=404,
                detail=f"Season id={season_id} was not found for league id={league_id}",
            )
    else:
        league_seasons = session.scalars(select(Season).where(Season.league_id == league_id)).all()
        if not league_seasons:
            raise HTTPException(status_code=404, detail=f"No seasons found for league id={league_id}")
        season = _pick_latest_season(league_seasons)

    try:
        _, match_rows = await asyncio.to_thread(fetch_matches_from_season_url, season.flashscore_link)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Failed to crawl Flashscore results page. "
                f"Details: {exc}"
            ),
        ) from exc

    csv_payload = _build_matches_csv(match_rows)
    season_label = extract_season_label(season.flashscore_link)
    filename = f"{league.slug}-{season_label}-matches.csv"

    return StreamingResponse(
        iter([csv_payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/leagues/{league_id}/matches-detailed.csv")
async def download_detailed_matches_csv_for_league(
    league_id: int,
    season_id: int | None = Query(default=None, ge=1),
    workers: int = Query(default=8, ge=1, le=24),
    max_matches: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db_session),
) -> StreamingResponse:
    league = session.scalar(select(League).where(League.id == league_id))
    if league is None:
        raise HTTPException(status_code=404, detail=f"League id={league_id} was not found")

    if season_id is not None:
        season = session.scalar(
            select(Season).where(Season.id == season_id, Season.league_id == league_id)
        )
        if season is None:
            raise HTTPException(
                status_code=404,
                detail=f"Season id={season_id} was not found for league id={league_id}",
            )
    else:
        league_seasons = session.scalars(select(Season).where(Season.league_id == league_id)).all()
        if not league_seasons:
            raise HTTPException(status_code=404, detail=f"No seasons found for league id={league_id}")
        season = _pick_latest_season(league_seasons)

    try:
        rows = await asyncio.to_thread(
            fetch_detailed_matches_from_season_url,
            season.flashscore_link,
            workers,
            max_matches,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to crawl detailed match data. Details: {exc}",
        ) from exc

    csv_payload = _build_detailed_matches_csv(rows)
    season_label = extract_season_label(season.flashscore_link)
    filename = f"{league.slug}-{season_label}-matches-detailed.csv"

    return StreamingResponse(
        iter([csv_payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/seasons/{season_id}/crawl-matches")
async def crawl_matches_for_season(
    season_id: int,
    workers: int = Query(default=8, ge=1, le=24),
    max_matches: int | None = Query(default=None, ge=1),
    session: Session = Depends(get_db_session),
) -> dict[str, int]:
    season = session.scalar(select(Season).where(Season.id == season_id))
    if season is None:
        raise HTTPException(status_code=404, detail=f"Season id={season_id} was not found")

    try:
        detailed_rows = await asyncio.to_thread(
            fetch_detailed_matches_from_season_url,
            season.flashscore_link,
            workers,
            max_matches,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to crawl detailed season data. Details: {exc}",
        ) from exc

    existing_rows = session.scalars(select(Match).where(Match.season_id == season_id)).all()
    by_link: dict[str, Match] = {
        row.flashscore_link: row
        for row in existing_rows
    }
    by_event_id: dict[str, Match] = {
        row.event_id: row
        for row in existing_rows
        if row.event_id
    }

    inserted = 0
    updated = 0
    crawled = 0

    for payload in detailed_rows:
        match_link = _normalize_match_url(payload.get("match_link", ""))
        if not match_link:
            continue
        crawled += 1

        event_id = (payload.get("event_id") or "").strip()
        home_team = (payload.get("home_team") or "").strip() or "Unknown Home"
        away_team = (payload.get("away_team") or "").strip() or "Unknown Away"
        final_score = (payload.get("final_score") or "").strip()
        home_score, away_score = _parse_final_score(final_score)
        kickoff_datetime_utc = _parse_kickoff_datetime_utc(payload.get("kickoff_datetime_utc"))
        kickoff_hour_utc = (payload.get("kickoff_hour_utc") or "").strip() or None
        match_date = (payload.get("match_date") or "").strip() or None

        row = by_link.get(match_link)
        if row is None and event_id:
            row = by_event_id.get(event_id)
        if row is None:
            row = Match(
                season_id=season_id,
                event_id=event_id or None,
                flashscore_link=match_link,
                match_date=match_date,
                kickoff_datetime_utc=kickoff_datetime_utc,
                kickoff_hour_utc=kickoff_hour_utc,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                intermediate_scores=(payload.get("intermediate_scores") or "").strip() or None,
                final_score=final_score or None,
                goals=(payload.get("goals") or "").strip() or None,
                yellow_cards=(payload.get("yellow_cards") or "").strip() or None,
                red_cards=(payload.get("red_cards") or "").strip() or None,
                referee=(payload.get("referee") or "").strip() or None,
                referee_country_code=(payload.get("referee_country_code") or "").strip() or None,
                stadium=(payload.get("stadium") or "").strip() or None,
                city=(payload.get("city") or "").strip() or None,
                attendance=(payload.get("attendance") or "").strip() or None,
                capacity=(payload.get("capacity") or "").strip() or None,
                fortuna_1=(payload.get("fortuna_1") or "").strip() or None,
                fortuna_x=(payload.get("fortuna_x") or "").strip() or None,
                fortuna_2=(payload.get("fortuna_2") or "").strip() or None,
                superbet_1=(payload.get("superbet_1") or "").strip() or None,
                superbet_x=(payload.get("superbet_x") or "").strip() or None,
                superbet_2=(payload.get("superbet_2") or "").strip() or None,
                crawl_error=(payload.get("error") or "").strip() or None,
            )
            session.add(row)
            by_link[match_link] = row
            if event_id:
                by_event_id[event_id] = row
            inserted += 1
            continue

        has_changes = False
        if row.flashscore_link != match_link:
            by_link.pop(row.flashscore_link, None)
            row.flashscore_link = match_link
            by_link[match_link] = row
            has_changes = True
        if (row.event_id or "") != event_id:
            row.event_id = event_id or None
            if row.event_id:
                by_event_id[row.event_id] = row
            has_changes = True
        if (row.match_date or "") != (match_date or ""):
            row.match_date = match_date
            has_changes = True
        if row.kickoff_datetime_utc != kickoff_datetime_utc:
            row.kickoff_datetime_utc = kickoff_datetime_utc
            has_changes = True
        if (row.kickoff_hour_utc or "") != (kickoff_hour_utc or ""):
            row.kickoff_hour_utc = kickoff_hour_utc
            has_changes = True
        if row.home_team != home_team:
            row.home_team = home_team
            has_changes = True
        if row.away_team != away_team:
            row.away_team = away_team
            has_changes = True
        if row.home_score != home_score:
            row.home_score = home_score
            has_changes = True
        if row.away_score != away_score:
            row.away_score = away_score
            has_changes = True
        if (row.intermediate_scores or "") != ((payload.get("intermediate_scores") or "").strip()):
            row.intermediate_scores = (payload.get("intermediate_scores") or "").strip() or None
            has_changes = True
        if (row.final_score or "") != final_score:
            row.final_score = final_score or None
            has_changes = True
        if (row.goals or "") != ((payload.get("goals") or "").strip()):
            row.goals = (payload.get("goals") or "").strip() or None
            has_changes = True
        if (row.yellow_cards or "") != ((payload.get("yellow_cards") or "").strip()):
            row.yellow_cards = (payload.get("yellow_cards") or "").strip() or None
            has_changes = True
        if (row.red_cards or "") != ((payload.get("red_cards") or "").strip()):
            row.red_cards = (payload.get("red_cards") or "").strip() or None
            has_changes = True
        if (row.referee or "") != ((payload.get("referee") or "").strip()):
            row.referee = (payload.get("referee") or "").strip() or None
            has_changes = True
        if (row.referee_country_code or "") != ((payload.get("referee_country_code") or "").strip()):
            row.referee_country_code = (payload.get("referee_country_code") or "").strip() or None
            has_changes = True
        if (row.stadium or "") != ((payload.get("stadium") or "").strip()):
            row.stadium = (payload.get("stadium") or "").strip() or None
            has_changes = True
        if (row.city or "") != ((payload.get("city") or "").strip()):
            row.city = (payload.get("city") or "").strip() or None
            has_changes = True
        if (row.attendance or "") != ((payload.get("attendance") or "").strip()):
            row.attendance = (payload.get("attendance") or "").strip() or None
            has_changes = True
        if (row.capacity or "") != ((payload.get("capacity") or "").strip()):
            row.capacity = (payload.get("capacity") or "").strip() or None
            has_changes = True
        if (row.fortuna_1 or "") != ((payload.get("fortuna_1") or "").strip()):
            row.fortuna_1 = (payload.get("fortuna_1") or "").strip() or None
            has_changes = True
        if (row.fortuna_x or "") != ((payload.get("fortuna_x") or "").strip()):
            row.fortuna_x = (payload.get("fortuna_x") or "").strip() or None
            has_changes = True
        if (row.fortuna_2 or "") != ((payload.get("fortuna_2") or "").strip()):
            row.fortuna_2 = (payload.get("fortuna_2") or "").strip() or None
            has_changes = True
        if (row.superbet_1 or "") != ((payload.get("superbet_1") or "").strip()):
            row.superbet_1 = (payload.get("superbet_1") or "").strip() or None
            has_changes = True
        if (row.superbet_x or "") != ((payload.get("superbet_x") or "").strip()):
            row.superbet_x = (payload.get("superbet_x") or "").strip() or None
            has_changes = True
        if (row.superbet_2 or "") != ((payload.get("superbet_2") or "").strip()):
            row.superbet_2 = (payload.get("superbet_2") or "").strip() or None
            has_changes = True
        if (row.crawl_error or "") != ((payload.get("error") or "").strip()):
            row.crawl_error = (payload.get("error") or "").strip() or None
            has_changes = True

        if has_changes:
            updated += 1

    session.commit()

    total_in_db = int(
        session.scalar(
            select(func.count()).select_from(Match).where(Match.season_id == season_id)
        )
        or 0
    )

    return {
        "season_id": season_id,
        "crawled": crawled,
        "inserted": inserted,
        "updated": updated,
        "total_in_db": total_in_db,
    }


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
