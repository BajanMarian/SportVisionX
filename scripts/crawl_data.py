import argparse
import os
import csv
import sys
from typing import List, Dict, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.webdriver import Options as ChromeOptions
from InquirerPy import inquirer

from crawler.flashscore_crawler import FlashScoreCrawler
from models.match import Sport, Match


def setup_crawler() -> FlashScoreCrawler:
    chrome_options = ChromeOptions()
    chrome_options.add_argument('--headless')
    driver = webdriver.Chrome(options=chrome_options)
    return FlashScoreCrawler(driver)


def compute_leagues_urls(sport: Sport, leagues: List[str], seasons: List[str]) -> Dict[str, str]:
    leagues_urls: dict[str, str] = {}
    for season in seasons:
        for league in leagues:
            league_id = f'{sport.name.lower()}_{league}_{season}'  # e.g. basketball_spain/acb_2020-2021
            leagues_urls[league_id] = FlashScoreCrawler.compute_full_url_for_league(sport, league, season)

    return leagues_urls


def read_file_lines(file_path: str) -> List[str]:
    lines: List[str] = []
    with open(file_path, 'r') as reader:
        for line in reader.readlines():
            lines.append(line.strip())

    return lines


def write_league_data(outfile: str, matches: List[Match]):
    if len(matches) == 0:
        raise Exception('No match has been provided! Please provide at least one match!')

    print(f'Writing crawled data to {outfile} ...')
    with open(outfile, 'w+', encoding='utf8', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=matches[0].to_dict().keys())
        writer.writeheader()
        for match in matches:
            writer.writerow(match.to_dict())


def parse_input() -> Tuple[str, str, str]:
    parser = argparse.ArgumentParser(
        description='Read 2 file paths representing the input data and a directory path where results should be placed'
    )

    # Add arguments with flags
    parser.add_argument('--leagues', type=str, required=True, help='Path to the leagues file')
    parser.add_argument('--seasons', type=str, required=True, help='Path to the seasons file')
    parser.add_argument('--out_dir', type=str, required=True, help='Path to the output folder')

    args = parser.parse_args()
    leagues_path = args.leagues
    seasons_path = args.seasons
    out_dir_path = args.out_dir

    if not os.path.exists(leagues_path):
        print(f'Error: The leagues file path "{leagues_path}" does not exists.', file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(seasons_path):
        print(f'Error: The seasons file path "{seasons_path}" does not exists.', file=sys.stderr)
        sys.exit(1)

    return leagues_path, seasons_path, out_dir_path


def select_sport() -> Sport:
    sports_list = [sport.value for sport in Sport]

    selected_sport = inquirer.select(
        message="Select a sport:",
        choices=sports_list,
    ).execute()

    # Convert the selected string back to the corresponding Sport Enum
    return Sport(selected_sport)


def main():

    leagues_path, seasons_path, out_dir = parse_input()
    leagues = read_file_lines(leagues_path)
    seasons = read_file_lines(seasons_path)
    sport: Sport = select_sport()

    crawler = setup_crawler()
    leagues_urls = compute_leagues_urls(sport, leagues, seasons)

    for league_info, url in leagues_urls.items():

        _, league, season = league_info.split("_")

        league_folder = os.path.join(out_dir, sport.name.lower(), season)
        os.makedirs(league_folder, exist_ok=True)

        league_outfile = os.path.join(league_folder, f'{league.replace('/', '-')}.csv')
        if os.path.exists(league_outfile):
            print(f'File {league_outfile} is on disk. Skipping crawling data ...')
            continue

        # use crawl_matches_v3 method for a fast crawling process
        league_matches = crawler.crawl_matches_v3(url, sport)
        if len(league_matches) == 0:
            print(f'Error: Cannot crawl data for "{league_info}" using {url}.')
            continue

        # data was crawled in reverse chronological order.
        season_start_month = league_matches[-1].date.month

        # crawled data does not contain the year, thus we are going to add it manually
        season_start_year = int(season.split("-")[0])
        for match in league_matches:
            match.enhance_match_date(season_start_year, season_start_month)

        write_league_data(league_outfile, league_matches)


if __name__ == '__main__':
    main()
