import csv
import logging
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://www.flashscore.com/"
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "Mozilla/5.0"

HTML_INPUT_PATH = Path("htmls") / "sports.html"

CSV_OUTPUT_PATH = Path("sports.csv")
CSV_HEADERS = ("sport_name", "flashscore_link")

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


def write_sports_csv(sports: list[dict[str, str]], csv_file_path: Path | str) -> Path:
    csv_path = Path(csv_file_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(CSV_HEADERS))
        writer.writeheader()
        for sport in sports:
            writer.writerow(
                {
                    "sport_name": sport["sport_name"],
                    "flashscore_link": sport["flashscore_link"],
                }
            )

    return csv_path


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        html_file = Path.cwd() / HTML_INPUT_PATH
        output_csv = Path.cwd() / CSV_OUTPUT_PATH
        sports = extract_sports_from_saved_html(html_file)
        csv_path = write_sports_csv(sports, output_csv)
        logger.info("Extracted %d sports to %s", len(sports), csv_path)
        return 0
    except Exception:
        logger.exception("Failed to generate sports CSV")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
