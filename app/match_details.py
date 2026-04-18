import asyncio
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.match_results import build_results_url

REQUEST_TIMEOUT_MS = 60_000
REQUEST_TIMEOUT_SECONDS = 35
SHOW_MORE_TIMEOUT_MS = 1_500
MAX_SHOW_MORE_CLICKS = 260
MATCH_ROW_SELECTOR = "div.event__match[data-event-row='true'], div.event__match"
USER_AGENT = "Mozilla/5.0"
X_FSIGN = "SW9D1eZo"
FEED_SEPARATOR = chr(172)
KEY_VALUE_SEPARATOR = chr(247)
DEFAULT_WORKERS = 8
REQUEST_RETRIES = 2

NINJA_FEED_BASE = "https://global.flashscore.ninja/2/x/feed"
MATCH_PARTICIPANTS_URL = "https://2.ds.lsapp.eu/pq_graphql"
ODDS_COMPARISON_URL = "https://global.ds.lsapp.eu/odds/pq_graphql"

ODDS_TARGET_BOOKMAKERS = {
    "fortuna": "fortuna",
    "superbet": "superbet",
    "unibet": "unibet",
}


@dataclass(slots=True)
class MatchSummary:
    event_id: str
    match_url: str
    date: str
    round_label: str
    home_team: str
    away_team: str
    home_score: str
    away_score: str


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).split()).strip()


def _minute_to_int(minute_text: str | None) -> int | None:
    minute_text = _clean_text(minute_text).replace("'", "")
    if not minute_text:
        return None
    if "+" in minute_text:
        base, extra = minute_text.split("+", 1)
        if base.isdigit() and extra.isdigit():
            return int(base) + int(extra)
        return None
    if minute_text.isdigit():
        return int(minute_text)
    return None


def _parse_feed_records(feed_text: str) -> list[list[tuple[str, str]]]:
    records: list[list[tuple[str, str]]] = []
    for raw_record in feed_text.split(FEED_SEPARATOR + "~"):
        pairs: list[tuple[str, str]] = []
        for part in raw_record.split(FEED_SEPARATOR):
            if KEY_VALUE_SEPARATOR not in part:
                continue
            key, value = part.split(KEY_VALUE_SEPARATOR, 1)
            pairs.append((key, value))
        if pairs:
            records.append(pairs)
    return records


def _request_text(url: str, headers: dict[str, str] | None = None) -> str:
    last_error: Exception | None = None
    merged_headers = {"User-Agent": USER_AGENT}
    if headers:
        merged_headers.update(headers)

    for attempt in range(1, REQUEST_RETRIES + 2):
        try:
            response = requests.get(url, headers=merged_headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt <= REQUEST_RETRIES:
                time.sleep(0.3 * attempt)
                continue
            raise

    raise RuntimeError(f"Failed to GET {url}") from last_error


def _request_json(url: str) -> dict:
    text = _request_text(url)
    return json.loads(text)


def _fetch_feed(feed_path: str) -> str:
    return _request_text(
        f"{NINJA_FEED_BASE}/{feed_path}",
        headers={"X-Fsign": X_FSIGN},
    )


def _extract_event_segments(record_pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    common_keys = {"III", "IA", "IB", "INX", "IOX"}
    segment_keys = {"IE", "IF", "IU", "ICT", "IK", "IM", "IJ", "IL"}

    common: dict[str, str] = {}
    current_segment: dict[str, str] | None = None
    segments: list[dict[str, str]] = []

    for key, value in record_pairs:
        if key in common_keys:
            common[key] = value
            if current_segment is not None and key not in current_segment:
                current_segment[key] = value
            continue

        if key == "IE":
            if current_segment is not None and "IE" in current_segment:
                segments.append(current_segment)
            current_segment = dict(common)
            current_segment["IE"] = value
            continue

        if key in segment_keys:
            if current_segment is None:
                current_segment = dict(common)
            current_segment[key] = value

    if current_segment is not None and "IE" in current_segment:
        segments.append(current_segment)

    return segments


def _parse_dc_feed(feed_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for record in _parse_feed_records(feed_text):
        for key, value in record:
            values[key] = value
    return values


def _parse_lineups_starters(feed_text: str) -> tuple[set[str], set[str]]:
    records = _parse_feed_records(feed_text)
    current_side: str | None = None
    current_section: str | None = None
    home_starters: set[str] = set()
    away_starters: set[str] = set()

    for record in records:
        for key, value in record:
            if key == "LC":
                if value == "1":
                    current_side = "home"
                elif value == "2":
                    current_side = "away"
                else:
                    current_side = None
            elif key == "LB":
                current_section = value

        player_id = next((value for key, value in record if key == "LP"), "")
        if not player_id:
            continue
        if current_section != "Starting Lineups":
            continue
        if current_side == "home":
            home_starters.add(player_id)
        elif current_side == "away":
            away_starters.add(player_id)

    return home_starters, away_starters


def _parse_sui_feed(
    feed_text: str,
    home_starters: set[str],
    away_starters: set[str],
) -> dict:
    records = _parse_feed_records(feed_text)
    intermediate_scores: list[dict[str, str]] = []
    goals: list[dict[str, str]] = []
    yellow_cards: list[dict[str, str | bool | None]] = []
    red_cards: list[dict[str, str | bool | None]] = []
    metadata_codes: dict[str, str] = {}
    sub_in: dict[str, int] = {}
    sub_out: dict[str, int] = {}

    for record in records:
        first_key = record[0][0]

        if first_key == "AC":
            row = {key: value for key, value in record}
            intermediate_scores.append(
                {
                    "period": row.get("AC", ""),
                    "home": row.get("IG", ""),
                    "away": row.get("IH", ""),
                }
            )
            continue

        if any(key == "MIT" for key, _ in record):
            pending_code: str | None = None
            for key, value in record:
                if key == "MIT":
                    pending_code = value
                elif key == "MIV" and pending_code:
                    metadata_codes[pending_code] = value
                    pending_code = None
            continue

        if not any(key == "III" for key, _ in record):
            continue

        for segment in _extract_event_segments(record):
            side = "home" if segment.get("IA") == "1" else "away" if segment.get("IA") == "2" else "unknown"
            minute = segment.get("IB", "")
            minute_int = _minute_to_int(minute)
            event_type_label = _clean_text(segment.get("IK", ""))
            event_type_id = _clean_text(segment.get("IE", ""))
            player_name = _clean_text(segment.get("IF", ""))
            player_id = _clean_text(segment.get("IM", ""))
            score_after = ""
            if segment.get("INX") is not None and segment.get("IOX") is not None:
                score_after = f"{segment.get('INX')}-{segment.get('IOX')}"

            if event_type_label == "Substitution - In" or event_type_id == "7":
                if player_id and minute_int is not None:
                    sub_in[player_id] = minute_int
                continue

            if event_type_label == "Substitution - Out" or event_type_id == "6":
                if player_id and minute_int is not None:
                    sub_out[player_id] = minute_int
                continue

            if event_type_label == "Goal" or event_type_id == "3":
                goals.append(
                    {
                        "minute": minute,
                        "team": side,
                        "player": player_name,
                        "score_after_event": score_after,
                    }
                )
                continue

            if event_type_label == "Yellow Card" or event_type_id == "1":
                yellow_cards.append(
                    {
                        "minute": minute,
                        "team": side,
                        "player": player_name,
                        "player_id": player_id,
                        "reason": _clean_text(segment.get("IL", "")),
                        "on_pitch": None,
                    }
                )
                continue

            if event_type_label == "Red Card" or event_type_id in {"2", "16", "17"}:
                red_cards.append(
                    {
                        "minute": minute,
                        "team": side,
                        "player": player_name,
                        "player_id": player_id,
                        "reason": _clean_text(segment.get("IL", "")),
                        "on_pitch": None,
                    }
                )

    def mark_on_pitch(card_rows: list[dict[str, str | bool | None]]) -> None:
        for row in card_rows:
            player_id = _clean_text(str(row.get("player_id", "")))
            minute_int = _minute_to_int(str(row.get("minute", "")))
            if not player_id or minute_int is None:
                row["on_pitch"] = None
                continue

            if player_id in home_starters or player_id in away_starters:
                enter_minute = 0
            else:
                enter_minute = sub_in.get(player_id)

            if enter_minute is None:
                row["on_pitch"] = None
                continue

            leave_minute = sub_out.get(player_id, 200)
            row["on_pitch"] = bool(enter_minute <= minute_int <= leave_minute)

    mark_on_pitch(yellow_cards)
    mark_on_pitch(red_cards)

    metadata = {
        "referee": _clean_text(metadata_codes.get("REF", "")),
        "stadium": _clean_text(metadata_codes.get("VEN", "")),
        "city": _clean_text(metadata_codes.get("TWN", "")),
        "attendance": _clean_text(metadata_codes.get("ATT", "")),
        "capacity": _clean_text(metadata_codes.get("CAP", "")),
        "referee_country_code": _clean_text(metadata_codes.get("RCC", "")),
    }

    return {
        "intermediate_scores": intermediate_scores,
        "goals": goals,
        "yellow_cards": yellow_cards,
        "red_cards": red_cards,
        "metadata": metadata,
    }


def _fetch_home_away_participant_ids(event_id: str) -> tuple[str | None, str | None]:
    payload = _request_json(
        f"{MATCH_PARTICIPANTS_URL}?_hash=dsos2&eventId={event_id}&projectId=2"
    )
    event = payload.get("data", {}).get("findEventById", {})
    home_id: str | None = None
    away_id: str | None = None

    for participant in event.get("eventParticipants", []):
        participant_id = participant.get("id")
        side = participant.get("type", {}).get("side")
        if side == "HOME":
            home_id = participant_id
        elif side == "AWAY":
            away_id = participant_id

    return home_id, away_id


def _extract_target_1x2_odds(event_id: str) -> dict[str, str]:
    result = {
        "fortuna_1": "",
        "fortuna_x": "",
        "fortuna_2": "",
        "superbet_1": "",
        "superbet_x": "",
        "superbet_2": "",
        "unibet_1": "",
        "unibet_x": "",
        "unibet_2": "",
    }

    home_participant_id, away_participant_id = _fetch_home_away_participant_ids(event_id)
    if not home_participant_id or not away_participant_id:
        return result

    payload = _request_json(
        (
            f"{ODDS_COMPARISON_URL}?_hash=oce&eventId={event_id}"
            "&projectId=2&geoIpCode=RO&geoIpSubdivisionCode=ROB"
        )
    )
    odds_data = payload.get("data", {}).get("findOddsByEventId", {})
    settings = odds_data.get("settings", {})
    odds_rows = odds_data.get("odds", [])

    bookmaker_labels: dict[int, str] = {}
    for bookmaker_entry in settings.get("bookmakers", []):
        bookmaker = bookmaker_entry.get("bookmaker", {})
        bookmaker_id = bookmaker.get("id")
        bookmaker_name = _clean_text(bookmaker.get("name", "")).lower()
        if bookmaker_id is None:
            continue

        for needle, label in ODDS_TARGET_BOOKMAKERS.items():
            if needle in bookmaker_name:
                bookmaker_labels[int(bookmaker_id)] = label
                break

    for row in odds_rows:
        if row.get("bettingType") != "HOME_DRAW_AWAY":
            continue
        if row.get("bettingScope") != "FULL_TIME":
            continue

        bookmaker_id = int(row.get("bookmakerId") or 0)
        label = bookmaker_labels.get(bookmaker_id)
        if not label:
            continue

        home_value = ""
        draw_value = ""
        away_value = ""
        for odd_item in row.get("odds", []):
            participant_id = odd_item.get("eventParticipantId")
            odd_value = _clean_text(odd_item.get("value", ""))
            if participant_id == home_participant_id:
                home_value = odd_value
            elif participant_id == away_participant_id:
                away_value = odd_value
            elif participant_id is None:
                draw_value = odd_value

        if home_value:
            result[f"{label}_1"] = home_value
        if draw_value:
            result[f"{label}_x"] = draw_value
        if away_value:
            result[f"{label}_2"] = away_value

    return result


def _format_intermediate_scores(period_rows: list[dict[str, str]]) -> str:
    scores = [f"[{row.get('home', '')}-{row.get('away', '')}]" for row in period_rows]
    return "[" + ", ".join(scores) + "]"


def _epoch_to_utc(epoch_value: str | None) -> tuple[str, str]:
    epoch_value = _clean_text(epoch_value)
    if not epoch_value.isdigit():
        return "", ""
    dt = datetime.fromtimestamp(int(epoch_value), tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC"), dt.strftime("%H:%M")


def _build_match_details(summary: MatchSummary) -> dict[str, str]:
    dc_feed = _fetch_feed(f"dc_1_{summary.event_id}")
    sui_feed = _fetch_feed(f"df_sui_1_{summary.event_id}")
    li_feed = _fetch_feed(f"df_li_1_{summary.event_id}")

    dc = _parse_dc_feed(dc_feed)
    home_starters, away_starters = _parse_lineups_starters(li_feed)
    sui = _parse_sui_feed(sui_feed, home_starters, away_starters)
    odds = _extract_target_1x2_odds(summary.event_id)

    final_home = _clean_text(dc.get("DE", "")) or summary.home_score
    final_away = _clean_text(dc.get("DF", "")) or summary.away_score
    final_score = f"{final_home}-{final_away}" if final_home or final_away else ""
    kickoff_datetime_utc, kickoff_hour_utc = _epoch_to_utc(dc.get("DC"))

    return {
        "event_id": summary.event_id,
        "match_link": summary.match_url,
        "match_date": summary.date,
        "round": summary.round_label,
        "kickoff_datetime_utc": kickoff_datetime_utc,
        "kickoff_hour_utc": kickoff_hour_utc,
        "home_team": summary.home_team,
        "away_team": summary.away_team,
        "intermediate_scores": _format_intermediate_scores(sui["intermediate_scores"]),
        "final_score": final_score,
        "goals": json.dumps(sui["goals"], ensure_ascii=False),
        "yellow_cards": json.dumps(sui["yellow_cards"], ensure_ascii=False),
        "red_cards": json.dumps(sui["red_cards"], ensure_ascii=False),
        "referee": sui["metadata"]["referee"],
        "referee_country_code": sui["metadata"]["referee_country_code"],
        "stadium": sui["metadata"]["stadium"],
        "city": sui["metadata"]["city"],
        "attendance": sui["metadata"]["attendance"],
        "capacity": sui["metadata"]["capacity"],
        "fortuna_1": odds["fortuna_1"],
        "fortuna_x": odds["fortuna_x"],
        "fortuna_2": odds["fortuna_2"],
        "superbet_1": odds["superbet_1"],
        "superbet_x": odds["superbet_x"],
        "superbet_2": odds["superbet_2"],
        "unibet_1": odds["unibet_1"],
        "unibet_x": odds["unibet_x"],
        "unibet_2": odds["unibet_2"],
        "error": "",
    }


async def _expand_all_results(page) -> None:
    for _ in range(MAX_SHOW_MORE_CLICKS):
        before = await page.locator(MATCH_ROW_SELECTOR).count()
        button = page.locator("button:has-text('Show more matches')").first
        if await button.count() == 0:
            break

        try:
            if not await button.is_visible(timeout=SHOW_MORE_TIMEOUT_MS):
                break
        except PlaywrightTimeoutError:
            break

        await button.scroll_into_view_if_needed()
        await button.click()
        await page.wait_for_timeout(900)

        after = await page.locator(MATCH_ROW_SELECTOR).count()
        if after <= before:
            await page.wait_for_timeout(1_100)
            after_retry = await page.locator(MATCH_ROW_SELECTOR).count()
            if after_retry <= before:
                break


def _extract_event_id_from_row(row, match_url: str) -> str:
    query_mid = parse_qs(urlparse(match_url).query).get("mid", [""])[0]
    if query_mid:
        return query_mid

    row_id = _clean_text(row.get("id", ""))
    match = re.match(r"g_\d+_([A-Za-z0-9]+)", row_id)
    if match:
        return match.group(1)
    return ""


def _extract_round_label_from_row(row) -> str:
    for sibling in row.previous_siblings:
        if getattr(sibling, "name", None) is None:
            continue
        classes = sibling.get("class", []) or []
        if "event__round" in classes:
            return _clean_text(sibling.get_text(" ", strip=True))
    return ""


def _parse_matches_from_results_html(results_url: str, html: str) -> list[MatchSummary]:
    soup = BeautifulSoup(html, "html.parser")
    matches: list[MatchSummary] = []
    seen: set[str] = set()

    for row in soup.select(MATCH_ROW_SELECTOR):
        link = row.select_one("a.eventRowLink[href]")
        if link is None:
            continue

        href = _clean_text(link.get("href", ""))
        if not href:
            continue
        match_url = urljoin(results_url, href)
        event_id = _extract_event_id_from_row(row, match_url)
        if not event_id or event_id in seen:
            continue

        seen.add(event_id)
        matches.append(
            MatchSummary(
                event_id=event_id,
                match_url=match_url,
                date=_clean_text((row.select_one(".event__time") or row).get_text(" ", strip=True)),
                round_label=_extract_round_label_from_row(row),
                home_team=_clean_text((row.select_one(".event__homeParticipant") or row).get_text(" ", strip=True)),
                away_team=_clean_text((row.select_one(".event__awayParticipant") or row).get_text(" ", strip=True)),
                home_score=_clean_text((row.select_one(".event__score--home") or row).get_text(" ", strip=True)),
                away_score=_clean_text((row.select_one(".event__score--away") or row).get_text(" ", strip=True)),
            )
        )

    return matches


async def _fetch_results_page_matches_async(results_url: str) -> list[MatchSummary]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(results_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT_MS)
            await page.wait_for_selector(MATCH_ROW_SELECTOR, timeout=REQUEST_TIMEOUT_MS)
            await _expand_all_results(page)
            html = await page.content()
        finally:
            await browser.close()

    return _parse_matches_from_results_html(results_url, html)


def _run_in_fresh_loop(coro):
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def fetch_results_page_matches(results_url: str) -> list[MatchSummary]:
    return _run_in_fresh_loop(_fetch_results_page_matches_async(results_url))


def fetch_detailed_matches_from_season_url(
    season_url: str,
    workers: int = DEFAULT_WORKERS,
    limit: int | None = None,
) -> list[dict[str, str]]:
    results_url = build_results_url(season_url)
    matches = fetch_results_page_matches(results_url)
    if limit is not None:
        matches = matches[: max(limit, 0)]

    if not matches:
        return []

    max_workers = max(1, min(workers, len(matches)))
    output_rows: list[dict[str, str] | None] = [None] * len(matches)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(_build_match_details, match): idx
            for idx, match in enumerate(matches)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            source_match = matches[idx]
            try:
                output_rows[idx] = future.result()
            except Exception as exc:
                output_rows[idx] = {
                    "event_id": source_match.event_id,
                    "match_link": source_match.match_url,
                    "match_date": source_match.date,
                    "round": source_match.round_label,
                    "kickoff_datetime_utc": "",
                    "kickoff_hour_utc": "",
                    "home_team": source_match.home_team,
                    "away_team": source_match.away_team,
                    "intermediate_scores": "",
                    "final_score": "",
                    "goals": "[]",
                    "yellow_cards": "[]",
                    "red_cards": "[]",
                    "referee": "",
                    "referee_country_code": "",
                    "stadium": "",
                    "city": "",
                    "attendance": "",
                    "capacity": "",
                    "fortuna_1": "",
                    "fortuna_x": "",
                    "fortuna_2": "",
                    "superbet_1": "",
                    "superbet_x": "",
                    "superbet_2": "",
                    "unibet_1": "",
                    "unibet_x": "",
                    "unibet_2": "",
                    "error": str(exc),
                }

    return [row for row in output_rows if row is not None]
