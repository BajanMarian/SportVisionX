import argparse
import csv
import logging
import sys
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.match_details import fetch_detailed_matches_from_season_url

DEFAULT_SEASON_URL = "https://www.flashscore.com/handball/france/starligue-2022-2023" # "https://www.flashscore.com/football/italy/serie-a-2023-2024/"
DEFAULT_OUTPUT = Path("htmls") / "serie-a-2023-2024-detailed-matches.csv"
DEFAULT_WORKERS = 8

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve detailed match data for a season and export CSV.",
    )
    parser.add_argument(
        "--season-url",
        default=DEFAULT_SEASON_URL,
        help="Season URL (without or with /results).",
    )
    parser.add_argument(
        "--outfile",
        default=str(DEFAULT_OUTPUT),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Parallel workers for per-match detail fetching.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional max matches to process (for testing).",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
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

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    try:
        rows = fetch_detailed_matches_from_season_url(
            season_url=args.season_url,
            workers=max(1, args.workers),
            limit=args.limit,
        )
        output_path = Path(args.outfile)
        write_csv(output_path, rows)

        with_errors = sum(1 for row in rows if row.get("error"))
        logger.info(
            "Exported %d detailed rows to %s (%d rows with errors)",
            len(rows),
            output_path,
            with_errors,
        )
        return 0
    except Exception:
        logger.exception("Failed to retrieve detailed matches")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
