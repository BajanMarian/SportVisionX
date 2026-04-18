import asyncio
import sys
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

REQUEST_TIMEOUT_MS = 60_000
SHOW_MORE_TIMEOUT_MS = 1_500
MAX_SHOW_MORE_CLICKS = 260
MATCH_ROW_SELECTOR = "div.event__match[data-event-row='true'], div.event__match"


@dataclass(slots=True)
class MatchRow:
    date: str
    home_team: str
    away_team: str
    home_score: str
    away_score: str


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def build_results_url(season_url: str) -> str:
    return urljoin(normalize_url(season_url), "results/")


def extract_season_label(season_url: str) -> str:
    import re

    match = re.search(r"(\d{4}-\d{4})/?$", season_url)
    return match.group(1) if match else "season"


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).split()).strip()


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


def _extract_team_name(container) -> str:
    if container is None:
        return ""

    preferred = container.select_one('[data-testid="wcl-scores-simple-text-01"], .wcl-name_jjfMf')
    if preferred is not None:
        return _clean_text(preferred.get_text(" ", strip=True))
    return _clean_text(container.get_text(" ", strip=True))


def _parse_matches_from_html(html: str) -> list[MatchRow]:
    soup = BeautifulSoup(html, "html.parser")
    parsed_matches: list[MatchRow] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for row in soup.select(MATCH_ROW_SELECTOR):
        date_value = _clean_text((row.select_one(".event__time") or row).get_text(" ", strip=True))
        home_team = _extract_team_name(row.select_one(".event__homeParticipant"))
        away_team = _extract_team_name(row.select_one(".event__awayParticipant"))
        home_score = _clean_text((row.select_one(".event__score--home") or row).get_text(" ", strip=True))
        away_score = _clean_text((row.select_one(".event__score--away") or row).get_text(" ", strip=True))

        if not home_team or not away_team:
            continue

        row_key = (date_value, home_team, away_team, home_score, away_score)
        if row_key in seen:
            continue
        seen.add(row_key)

        parsed_matches.append(
            MatchRow(
                date=date_value,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
            )
        )

    return parsed_matches


async def _fetch_matches_async(season_url: str) -> tuple[str, list[MatchRow]]:
    results_url = build_results_url(season_url)
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

    return results_url, _parse_matches_from_html(html)


def _run_in_fresh_loop(coro):
    # Uvicorn on Windows may run with SelectorEventLoop, which breaks Playwright's
    # subprocess transport. Use a dedicated Proactor loop for this crawl.
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def fetch_matches_from_season_url(season_url: str) -> tuple[str, list[MatchRow]]:
    return _run_in_fresh_loop(_fetch_matches_async(season_url))
