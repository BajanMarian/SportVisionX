import argparse
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.leagues import League
from db.seasons import Season

ENV_PATH = Path(".env.production")
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "Mozilla/5.0"
DEFAULT_WORKERS = 8
REQUEST_RETRIES = 2

SEASON_URL_PATTERN = re.compile(r"\d{4}-\d{4}/?$")
SEASON_TEXT_PATTERN = re.compile(r"\b\d{4}/\d{4}\b|\b\d{4}-\d{4}\b")

logger = logging.getLogger(__name__)


def load_database_url() -> str:
    load_dotenv(Path.cwd() / ENV_PATH)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in .env.production")
    return database_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Flashscore archive pages for leagues and import seasons.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Number of worker threads used for archive downloads and parsing.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit how many leagues are processed (useful for testing).",
    )
    return parser.parse_args()


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def build_archive_url(league_url: str) -> str:
    return urljoin(normalize_url(league_url), "archive/")


def fetch_archive_html(archive_url: str, timeout_seconds: int) -> str:
    last_error: Exception | None = None

    for attempt in range(1, REQUEST_RETRIES + 2):
        try:
            response = requests.get(
                archive_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt <= REQUEST_RETRIES:
                time.sleep(0.5 * attempt)
                continue
            raise

    raise RuntimeError(f"Failed to fetch archive URL: {archive_url}") from last_error


def extract_winner_from_anchor(anchor) -> str | None:
    parent = anchor.parent
    if parent is None:
        return None

    row_text = parent.get_text(" ", strip=True)
    anchor_text = anchor.get_text(" ", strip=True)
    if not row_text or not anchor_text:
        return None

    winner = row_text.replace(anchor_text, "", 1).strip(" -:")
    winner = re.sub(r"\s+", " ", winner)
    return winner or None


def extract_json_object_after_assignment(html: str, assignment_key: str) -> dict:
    start_idx = html.find(assignment_key)
    if start_idx < 0:
        raise ValueError(f"Could not find assignment key '{assignment_key}' in archive HTML")

    object_start = html.find("{", start_idx)
    if object_start < 0:
        raise ValueError(f"Could not find JSON object start after '{assignment_key}'")

    depth = 0
    object_end = -1
    for idx, char in enumerate(html[object_start:], start=object_start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

        if depth == 0:
            object_end = idx
            break

    if object_end < 0:
        raise ValueError(f"Could not find JSON object end after '{assignment_key}'")

    return json.loads(html[object_start : object_end + 1])


def extract_season_rows_from_environment(archive_url: str, html: str) -> list[dict[str, str | None]]:
    environment = extract_json_object_after_assignment(html, "window.environment =")
    season_list = environment.get("season_list", [])
    if not season_list:
        season_list = environment.get("stats2_config", {}).get("season_list", [])

    rows: list[dict[str, str | None]] = []
    seen_links: set[str] = set()

    for season in season_list:
        pathname = str(season.get("pathname", "")).strip()
        season_name = str(season.get("name", "")).strip()
        if not pathname:
            continue

        season_url = normalize_url(urljoin(archive_url, pathname))
        if season_url in seen_links:
            continue

        if not SEASON_TEXT_PATTERN.search(season_name):
            continue

        seen_links.add(season_url)
        rows.append(
            {
                "flashscore_link": season_url,
                "winner": None,
            }
        )

    return rows


def pick_winner_name(winners: object) -> str | None:
    if isinstance(winners, dict):
        for key in sorted(winners.keys(), key=str):
            winner_data = winners[key]
            if isinstance(winner_data, dict):
                name = str(winner_data.get("name", "")).strip()
                if name:
                    return name
        return None

    if isinstance(winners, list):
        for winner_data in winners:
            if isinstance(winner_data, dict):
                name = str(winner_data.get("name", "")).strip()
                if name:
                    return name
        return None

    return None


def extract_season_rows_from_archive_data(archive_url: str, html: str) -> list[dict[str, str | None]]:
    archive_data = extract_json_object_after_assignment(html, "var league_archive_data =")
    seasons = archive_data.get("seasons", [])

    rows: list[dict[str, str | None]] = []
    seen_links: set[str] = set()

    for season in seasons:
        if not isinstance(season, dict):
            continue

        season_url_raw = str(season.get("url", "")).strip()
        if not season_url_raw:
            continue

        season_url = normalize_url(urljoin(archive_url, season_url_raw))
        if season_url in seen_links:
            continue

        season_name = str(season.get("name", "")).strip()
        if season_name and not SEASON_TEXT_PATTERN.search(season_name):
            continue

        seen_links.add(season_url)
        rows.append(
            {
                "flashscore_link": season_url,
                "winner": pick_winner_name(season.get("winners")),
            }
        )

    return rows


def extract_season_rows_from_anchors(archive_url: str, html: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html, "html.parser")
    archive_parts = [part for part in urlparse(archive_url).path.split("/") if part]
    if len(archive_parts) < 4:
        raise ValueError(f"Unexpected archive URL format: {archive_url}")
    sport_slug, country_slug, league_slug = archive_parts[0], archive_parts[1], archive_parts[2]

    season_rows: list[dict[str, str | None]] = []
    seen_links: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue

        season_text = anchor.get_text(" ", strip=True)
        season_url = normalize_url(urljoin(archive_url, href))
        if season_url in seen_links:
            continue

        season_parts = [part for part in urlparse(season_url).path.split("/") if part]
        season_slug = season_parts[2] if len(season_parts) >= 3 else ""
        same_competition_family = (
            len(season_parts) >= 3
            and season_parts[0] == sport_slug
            and season_parts[1] == country_slug
            and season_slug.startswith(league_slug)
        )
        is_archive_link = season_url.endswith("/archive/")
        looks_like_season = bool(
            SEASON_URL_PATTERN.search(urlparse(season_url).path)
            or SEASON_TEXT_PATTERN.search(season_text)
            or re.search(rf"^{re.escape(league_slug)}-\d{{4}}-\d{{4}}$", season_slug)
        )

        if not same_competition_family or is_archive_link or not looks_like_season:
            continue

        seen_links.add(season_url)
        season_rows.append(
            {
                "flashscore_link": season_url,
                "winner": extract_winner_from_anchor(anchor),
            }
        )

    return season_rows


def extract_season_rows(archive_url: str, html: str) -> list[dict[str, str | None]]:
    try:
        rows = extract_season_rows_from_archive_data(archive_url, html)
        if rows:
            return rows
    except Exception as exc:
        logger.debug("Archive data parsing failed for %s: %s", archive_url, exc)

    try:
        rows = extract_season_rows_from_environment(archive_url, html)
        if rows:
            return rows
    except Exception as exc:
        logger.debug("Environment JSON parsing failed for %s: %s", archive_url, exc)

    return extract_season_rows_from_anchors(archive_url, html)


def fetch_and_parse_archive(league_data: dict[str, int | str]) -> dict:
    archive_url = build_archive_url(str(league_data["flashscore_link"]))
    html = fetch_archive_html(archive_url, REQUEST_TIMEOUT_SECONDS)
    seasons = extract_season_rows(archive_url, html)
    return {
        "league_id": int(league_data["id"]),
        "league_url": normalize_url(str(league_data["flashscore_link"])),
        "archive_url": archive_url,
        "seasons": seasons,
    }


def load_leagues(session: Session) -> list[dict[str, int | str]]:
    leagues = session.scalars(select(League)).all()
    return [
        {
            "id": league.id,
            "flashscore_link": league.flashscore_link,
        }
        for league in leagues
    ]


def fetch_archives_in_parallel(
    leagues: list[dict[str, int | str]],
    workers: int,
    session: Session,
) -> tuple[int, int]:
    max_workers = max(1, min(workers, len(leagues) or 1))
    failed = 0
    processed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_and_parse_archive, league): league
            for league in leagues
        }
        total = len(futures)

        for idx, future in enumerate(as_completed(futures), start=1):
            league = futures[future]
            try:
                parsed = future.result()
                # Persist each archive result immediately to avoid losing progress
                # during long-running crawls.
                upserted = upsert_seasons(session, [parsed])
                session.commit()
                processed += upserted
                logger.info(
                    "Archive %d/%d parsed for league_id=%s (%d seasons, %d upserted)",
                    idx,
                    total,
                    league["id"],
                    len(parsed["seasons"]),
                    upserted,
                )
            except Exception as exc:
                failed += 1
                session.rollback()
                logger.warning(
                    "Archive %d/%d failed for league_id=%s: %s",
                    idx,
                    total,
                    league["id"],
                    exc,
                )

    logger.info("Archive parsing complete: %d upserted rows, %d failed archives", processed, failed)
    return processed, failed


def upsert_seasons(session: Session, parsed_archives: list[dict]) -> int:
    processed = 0

    for archive_data in parsed_archives:
        for season_data in archive_data["seasons"]:
            season = session.scalar(
                select(Season).where(Season.flashscore_link == season_data["flashscore_link"])
            )

            if season is None:
                season = Season(
                    league_id=archive_data["league_id"],
                    flashscore_link=season_data["flashscore_link"],
                    winner=season_data["winner"],
                )
                session.add(season)
            else:
                season.league_id = archive_data["league_id"]
                season.winner = season_data["winner"]

            processed += 1

    return processed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        database_url = load_database_url()
        engine = create_engine(database_url)
        session_factory = sessionmaker(bind=engine)

        with session_factory() as db_session:
            leagues = load_leagues(db_session)
            if not leagues:
                raise RuntimeError("No leagues were found in the database.")

            if args.limit is not None:
                leagues = leagues[: max(args.limit, 0)]
            if not leagues:
                raise RuntimeError("No leagues to process after applying --limit.")

            processed, failed = fetch_archives_in_parallel(leagues, args.workers, db_session)

        logger.info(
            "Processed %d seasons from %d league archive pages (%d failed)",
            processed,
            len(leagues),
            failed,
        )
        return 0
    except Exception:
        logger.exception("Failed to retrieve seasons from league archive pages")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
