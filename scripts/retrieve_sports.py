import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.sports import Sport

BASE_URL = "https://www.flashscore.com/"
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "Mozilla/5.0"
LINK_VALIDATION_RETRIES = 3

HTML_INPUT_PATH = Path("htmls") / "sports.html"
ENV_PATH = Path(".env.production")

logger = logging.getLogger(__name__)


def download_html_to_local(url: str, filename: str) -> Path:
    import requests

    headers = {
        "User-Agent": USER_AGENT,
    }

    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()

    htmls_dir = Path.cwd() / "htmls"
    htmls_dir.mkdir(parents=True, exist_ok=True)

    file_path = htmls_dir / filename
    file_path.write_text(resp.text, encoding="utf-8")
    return file_path


def extract_sports_from_saved_html(html_file_path: Path | str) -> list[dict[str, str]]:
    html_path = Path(html_file_path)
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file was not found: {html_path}")

    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    sports: list[dict[str, str]] = []
    seen_rows: set[tuple[str, str]] = set()

    for a in soup.select("a.menuMinority__item[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue

        parts = [p for p in href.split("/") if p]
        if not parts:
            continue
        slug = parts[-1].lower()

        flashscore_link = urljoin(BASE_URL, href)
        row_key = (slug, flashscore_link)
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)

        sports.append(
            {
                "sport_name": slug,
                "flashscore_link": flashscore_link,
            }
        )

    return sorted(sports, key=lambda item: item["sport_name"])


def load_database_url() -> str:
    load_dotenv(Path.cwd() / ENV_PATH)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in .env.production")
    return database_url


def validate_flashscore_link(session: requests.Session, url: str) -> bool:
    for attempt in range(1, LINK_VALIDATION_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return True
            logger.warning(
                "Link validation failed for %s with status %s on attempt %d/%d",
                url,
                response.status_code,
                attempt,
                LINK_VALIDATION_RETRIES,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Link validation raised for %s on attempt %d/%d: %s",
                url,
                attempt,
                LINK_VALIDATION_RETRIES,
                exc,
            )

        if attempt < LINK_VALIDATION_RETRIES:
            time.sleep(1)

    return False


def upsert_sports(session: Session, sports: list[dict[str, str]]) -> int:
    http_session = requests.Session()
    http_session.headers.update({"User-Agent": USER_AGENT})
    inserted_or_updated = 0

    try:
        for sport_data in sports:
            sport_name = sport_data["sport_name"]
            flashscore_link = sport_data["flashscore_link"]

            validated_link = (
                flashscore_link
                if validate_flashscore_link(http_session, flashscore_link)
                else None
            )

            sport = session.get(Sport, sport_name)
            if sport is None:
                sport = Sport(name=sport_name, flashscore_link=validated_link)
                session.add(sport)
            elif validated_link is not None:
                sport.flashscore_link = validated_link

            inserted_or_updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        http_session.close()

    return inserted_or_updated


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        html_file = Path.cwd() / HTML_INPUT_PATH
        sports = extract_sports_from_saved_html(html_file)
        database_url = load_database_url()
        engine = create_engine(database_url)
        session_factory = sessionmaker(bind=engine)

        with session_factory() as db_session:
            processed_count = upsert_sports(db_session, sports)

        logger.info("Processed %d sports into database", processed_count)
        return 0
    except Exception:
        logger.exception("Failed to import sports into database")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
