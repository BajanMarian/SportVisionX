import os
import csv
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import Options as ChromeOptions
from typing import List, Dict

from crawler.flashscore_crawler import FlashScoreCrawler
from models.match import Sport, Match


def setup_crawler() -> FlashScoreCrawler:
    chrome_options = ChromeOptions()
    chrome_options.add_argument('--headless')
    driver = webdriver.Chrome(options=chrome_options)
    return FlashScoreCrawler(driver)


def get_basketball_leagues(seasons: List[str]) -> Dict[str, str]:
    leagues = []
    with open("../leagues_data/basketball/leagues.txt", "r") as f:
        for line in f:
            leagues.append(line.strip())

    sport = Sport.BASKETBALL
    leagues_urls: dict[str, str] = {}
    for season in seasons:
        for league in leagues:
            league_details = f"{sport.name.lower()}_{league}_{season}"
            leagues_urls[league_details] = FlashScoreCrawler.compute_full_url_for_league(sport, league, season)

    return leagues_urls


def get_seasons(desired_start_year: int) -> List[str]:
    seasons = []
    for season_start_year in range(desired_start_year, 2023):
        seasons.append(f"{season_start_year}-{season_start_year + 1}")

    return seasons


def write_league_data(outfile: str, matches: List[Match]):
    if len(matches) == 0:
        raise Exception('No match has been provided! Please provide at least one match!')

    print(f'Writing crawled data to {outfile} ...')
    with open(outfile, 'w+', encoding='utf8', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=matches[0].to_dict().keys())
        writer.writeheader()
        for match in matches:
            writer.writerow(match.to_dict())


def main():

    crawler = setup_crawler()
    seasons = get_seasons(2015)
    all_basketball_leagues = get_basketball_leagues(seasons)

    crawled_data_dir = ".results"

    for league_details, url in all_basketball_leagues.items():

        sport, league, season = league_details.split("_")

        league_folder = os.path.join(crawled_data_dir, sport, season)
        os.makedirs(league_folder, exist_ok=True)

        league_results_file = os.path.join(league_folder, f'{league.replace('/', '-')}.csv')
        if os.path.exists(league_results_file):
            print(f'File {league_results_file} is on disk. Skipping crawling data ...')
            continue

        league_matches = crawler.crawl_matches_v3(url, Sport.BASKETBALL)

        # first match of the season is in the last index of league matches - data has been crawled in descending order
        season_start_month = league_matches[-1].date.month
        # crawled data does not contain the year, thus we are going to add it manually on Match's "date" property
        season_start_year = int(season.split("-")[0])
        for match in league_matches:
            match.enhance_match_date(season_start_year, season_start_month)

        write_league_data(league_results_file, league_matches)


if __name__ == '__main__':
    main()
