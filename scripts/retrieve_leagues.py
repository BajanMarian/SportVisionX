import argparse
import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.countries import Country
from db.leagues import League
from db.sports import Sport

ENV_PATH = Path(".env.production")
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "Mozilla/5.0"
REQUEST_DELAY_SECONDS = 0.5

logger = logging.getLogger(__name__)


def fetch_html(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def parse_sport_slug(sport_url: str) -> str:
    path_parts = [part for part in urlparse(sport_url).path.split("/") if part]
    if not path_parts:
        raise ValueError(f"Unexpected sport url format: {sport_url}")
    return path_parts[0]


def load_database_url() -> str:
    load_dotenv(Path.cwd() / ENV_PATH)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in .env.production")
    return database_url


def parse_sport_names(raw_value: str) -> list[str]:
    sport_names = [sport.strip().lower() for sport in raw_value.split(",") if sport.strip()]
    if not sport_names:
        raise ValueError("At least one sport name must be provided.")
    return list(dict.fromkeys(sport_names))


def prompt_for_sports() -> str:
    raw_value = input("Enter sport name(s), separated by comma: ").strip()
    if not raw_value:
        raise ValueError("No sport name was provided.")
    return raw_value


def extract_country_links_from_sport_html(
    html: str,
    sport_url: str,
) -> list[dict[str, str]]:
    sport_slug = parse_sport_slug(sport_url)
    soup = BeautifulSoup(html, "html.parser")
    countries: list[dict[str, str]] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        country_name = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "").strip()

        if not country_name or not href:
            continue

        absolute_url = urljoin(sport_url, href)
        path_parts = [part for part in urlparse(absolute_url).path.split("/") if part]
        if len(path_parts) != 2 or path_parts[0] != sport_slug:
            continue

        if absolute_url in seen:
            continue

        seen.add(absolute_url)
        countries.append({"country": country_name, "url": absolute_url})

    return countries


def extract_leagues_from_country_page(
    html: str,
    sport_id: int,
    country_id: int,
    country_url: str,
) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    path_parts = [part for part in urlparse(country_url).path.split("/") if part]

    if len(path_parts) < 2:
        raise ValueError(f"Unexpected country url format: {country_url}")

    sport_slug = path_parts[0]
    country_slug = path_parts[1]

    leagues: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.select("a[href]"):
        league_name = anchor.get_text(" ", strip=True)
        href = anchor.get("href", "").strip()

        if not league_name or not href:
            continue

        league_url = urljoin(country_url, href)
        league_parts = [part for part in urlparse(league_url).path.split("/") if part]
        if len(league_parts) != 3:
            continue

        if league_parts[0] != sport_slug or league_parts[1] != country_slug:
            continue

        league_slug = league_parts[2]
        key = (league_name.lower(), league_url)
        if key in seen:
            continue

        seen.add(key)
        leagues.append(
            {
                "sport_id": sport_id,
                "country_id": country_id,
                "name": league_name,
                "slug": league_slug,
                "flashscore_link": league_url,
            }
        )

    return leagues


def crawl_sport_leagues(
    sport: Sport,
    session_db: Session,
    sport_url: str,
    session_http: requests.Session,
) -> list[dict[str, str]]:
    sport_html = fetch_html(session_http, sport_url)
    countries = extract_country_links_from_sport_html(sport_html, sport_url)

    all_leagues: list[dict[str, str]] = []
    for country in countries:
        try:
            country_id = get_or_create_country(session_db, country["country"])
            html = fetch_html(session_http, country["url"])
            all_leagues.extend(
                extract_leagues_from_country_page(
                    html=html,
                    sport_id=sport.id,
                    country_id=country_id,
                    country_url=country["url"],
                )
            )
            time.sleep(REQUEST_DELAY_SECONDS)
        except Exception as exc:
            logger.warning("Failed to process %s: %s", country["url"], exc)

    return all_leagues


def get_sports_to_process(session: Session, sport_names: list[str]) -> list[Sport]:
    sports_to_process: list[Sport] = []

    for sport_name in sport_names:
        sport = session.scalar(
            select(Sport).where(Sport.name == sport_name)
        )
        if sport is None:
            raise ValueError(f"Sport '{sport_name}' was not found in the sports table.")
        if not sport.flashscore_link:
            raise ValueError(f"Sport '{sport_name}' does not have a flashscore_link.")
        sports_to_process.append(sport)

    return sports_to_process


def get_or_create_country(session: Session, country_name: str) -> int:
    country = session.scalar(
        select(Country).where(Country.name == country_name)
    )
    if country is None:
        country = Country(name=country_name)
        session.add(country)
        session.flush()
    return country.id


def upsert_leagues(session: Session, leagues: list[dict[str, str]]) -> int:
    processed = 0

    for league_data in leagues:
        league = session.scalar(
            select(League).where(
                League.sport_id == league_data["sport_id"],
                League.country_id == league_data["country_id"],
                League.slug == league_data["slug"],
            )
        )

        if league is None:
            league = League(**league_data)
            session.add(league)
        else:
            league.name = league_data["name"]
            league.flashscore_link = league_data["flashscore_link"]

        processed += 1

    return processed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve leagues for one or more sports from Flashscore.",
    )
    parser.add_argument(
        "--sports",
        help="Comma-separated sport names already stored in the sports table.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    database_url = load_database_url()
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)

    http_session = requests.Session()
    http_session.headers.update({"User-Agent": USER_AGENT})

    try:
        sports_arg = args.sports if args.sports else prompt_for_sports()
        with session_factory() as db_session:
            sport_names = parse_sport_names(sports_arg)
            sports_to_process = get_sports_to_process(db_session, sport_names)

            processed = 0
            for sport in sports_to_process:
                logger.info("Retrieving leagues for %s from %s", sport.name, sport.flashscore_link)
                leagues = crawl_sport_leagues(sport, db_session, sport.flashscore_link, http_session)
                processed += upsert_leagues(db_session, leagues)

            db_session.commit()

        logger.info("Processed %d leagues across %d sport(s)", processed, len(sport_names))
        return 0
    except Exception:
        logger.exception("Failed to retrieve leagues for %s", args.sports or "<prompted input>")
        return 1
    finally:
        http_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
