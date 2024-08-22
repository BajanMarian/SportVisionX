import re
import time

from typing import List
from datetime import datetime
from selenium.common import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from models.match import Sport, Match


class FlashScoreCrawler:
    HYPERLINK_FOR_MORE_MATCHES = 'Show more matches'

    TABLE_ID = 'live-table'
    MATCH_EVENT_CSS_CLS = "event__match event__match--withRowLink event__match--static event__match--twoLine"

    HOME_TEAM_CSS_CLS = "event__participant event__participant--home"
    AWAY_TEAM_CSS_CLS = "event__participant event__participant--away"
    TOTAL_SCORE_HOME_TEAM_CSS_CLS = "event__score event__score--home"
    TOTAL_SCORE_AWAY_TEAM_CSS_CLS = "event__score event__score--away"
    MATCH_ROUND_CSS_CLS = "event__round"
    MATCH_DATE_CSS_CLS = "event__time"

    def __init__(self, driver: WebDriver) -> None:
        self.driver = driver
        self.loading_time_in_sec = 2

    def _is_hyperlink_visible(self, hyperlink_text: str) -> bool:
        try:
            self.driver.find_element(By.PARTIAL_LINK_TEXT, hyperlink_text)
            return True
        except NoSuchElementException:
            return False

    def _load_the_entire_webpage(self, url: str) -> None:

        self.driver.get(url)

        more_games_hyperlink = (By.PARTIAL_LINK_TEXT, FlashScoreCrawler.HYPERLINK_FOR_MORE_MATCHES)
        time.sleep(self.loading_time_in_sec)

        while self._is_hyperlink_visible(more_games_hyperlink[1]):
            try:
                hyperlink_elem = self.driver.find_element(*more_games_hyperlink)
                # used execute script method in order to avoid overlays and/or ads interceptions
                self.driver.execute_script("arguments[0].click();", hyperlink_elem)
                time.sleep(self.loading_time_in_sec)
            except Exception as e:
                print(f"Loading page error: {e}")
                return

    def crawl_matches_v1(self, url: str, sport: Sport) -> List[Match]:
        self._load_the_entire_webpage(url)

        all_matches = []

        table = self.driver.find_element(By.ID, FlashScoreCrawler.TABLE_ID)
        table_divs = table.find_elements(By.TAG_NAME, "div")

        competition_stage = ""
        for div in table_divs:
            class_name = div.get_attribute("class")

            if FlashScoreCrawler.MATCH_ROUND_CSS_CLS in class_name:
                competition_stage = div.text
            elif FlashScoreCrawler.MATCH_EVENT_CSS_CLS in class_name:
                teams = div.find_elements(By.CSS_SELECTOR, "div.event__participant")
                total_scores = div.find_elements(By.CSS_SELECTOR, f'div.event__score')
                match_date = div.find_element(By.CSS_SELECTOR, "div.event__time")
                m = Match(
                    sport=sport,
                    home_team=teams[0].text,
                    away_team=teams[1].text,
                    home_total_score=int(total_scores[0].text),
                    away_total_score=int(total_scores[1].text),
                    match_date=self.__class__.convert_to_datetime(match_date.text),
                    competition_round=competition_stage
                )
                all_matches.append(m)

        self.driver.quit()
        return all_matches

    def crawl_matches_v2(self, url: str, sport: Sport) -> List[Match]:
        self._load_the_entire_webpage(url)

        all_matches = []

        table = self.driver.find_element(By.ID, FlashScoreCrawler.TABLE_ID)
        table_divs = table.find_elements(By.TAG_NAME, "div")

        home_team = away_team = home_total_score = away_total_score = match_date = competition_stage = ""
        for div in table_divs:
            class_name = div.get_attribute("class")

            if FlashScoreCrawler.MATCH_ROUND_CSS_CLS in class_name:
                competition_stage = div.text
            else:
                if FlashScoreCrawler.MATCH_DATE_CSS_CLS in class_name:
                    match_date = div.text
                elif FlashScoreCrawler.HOME_TEAM_CSS_CLS in class_name:
                    home_team = div.text
                elif FlashScoreCrawler.AWAY_TEAM_CSS_CLS in class_name:
                    away_team = div.text
                elif FlashScoreCrawler.TOTAL_SCORE_HOME_TEAM_CSS_CLS in class_name:
                    home_total_score = div.text
                elif FlashScoreCrawler.TOTAL_SCORE_AWAY_TEAM_CSS_CLS in class_name:
                    away_total_score = div.text

                if all([home_team, away_team, home_total_score, away_total_score, match_date, competition_stage]):
                    m = Match(
                        sport=sport,
                        home_team=home_team,
                        away_team=away_team,
                        home_total_score=int(home_total_score),
                        away_total_score=int(away_total_score),
                        match_date=self.__class__.convert_to_datetime(match_date),
                        competition_round=competition_stage
                    )
                    all_matches.append(m)
                    home_team = away_team = home_total_score = away_total_score = match_date = competition_stage = ""

        self.driver.quit()
        return all_matches

    def crawl_matches_v3(self, url: str, sport: Sport) -> List[Match]:
        self._load_the_entire_webpage(url)
        table: WebElement
        try:
            table = self.driver.find_element(By.ID, FlashScoreCrawler.TABLE_ID)
        except NoSuchElementException:
            print(f'Error: Cannot identify matches table (web_element_id={FlashScoreCrawler.TABLE_ID}) using {url}.')
            return []

        all_matches = []
        match_date = competition_stage = ""

        i = 0
        tokens = table.text.split("\n")
        datetime_pattern = r"\d{2}\.\d{2}\. \d{2}:\d{2}"

        while i < len(tokens):

            if match_date == "":
                if re.match(datetime_pattern, tokens[i]):
                    match_date = tokens[i]
                    if match_date.split(" ")[0] == "29.02.":
                        match_date = "28.02. " + match_date.split(" ")[1]
                    # AOT stands for "After Overtime" stands Awrd for Awarded
                    if tokens[i + 1] == "AOT" or tokens[i+1] == "Awrd":
                        i += 1
                else:
                    competition_stage = tokens[i]
                i += 1
            else:
                home_team = tokens[i]
                away_team = tokens[i + 1]

                home_total_score = tokens[i + 2]
                away_total_score = tokens[i + 3]

                i = i + 4
                try:

                    m = Match(
                        sport=sport,
                        home_team=home_team,
                        away_team=away_team,
                        home_total_score=int(home_total_score),
                        away_total_score=int(away_total_score),
                        match_date=self.__class__.convert_to_datetime(match_date),
                        competition_round=competition_stage
                    )

                    # search for match periods
                    while i < len(tokens) and tokens[i].isdigit():
                        m.add_period_scores(tokens[i], tokens[i + 1])
                        i += 2
                    all_matches.append(m)
                    match_date = ""
                except Exception as e:
                    print(e)
                    print(home_total_score)
                    print(away_total_score)

        return all_matches

    @staticmethod
    def convert_to_datetime(date_str: str) -> datetime:
        return datetime.strptime(date_str, "%d.%m. %H:%M")

    @staticmethod
    def compute_full_url_for_league(sport: Sport, league: str, season: str) -> str:
        return f"https://www.flashscore.com/{sport.name.lower()}/{league}-{season}/results"

    @staticmethod
    def write_matches(fpath: str, matches: List[Match]):
        with open(fpath, 'w+', encoding='utf-8') as f:
            f.write("date,round,home_team,hosts_score,away_team,guests_score,hosts_periods,guests_periods\n")
            for match in matches:
                f.write(str(match))
                f.write("\n")
