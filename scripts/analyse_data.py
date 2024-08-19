import os
from typing import List

from models.championship import Championship


def get_seasons(desired_start_year: int) -> List[str]:
    seasons = []
    for season_start_year in range(desired_start_year, 2023):
        seasons.append(f"{season_start_year}-{season_start_year + 1}")

    return seasons


def main():
    data_dir = '.results'
    sport = 'basketball'
    seasons = get_seasons(2015)

    total_wins = 0
    total_defeats = 0

    for season in seasons:
        season_data_dir = os.path.join(data_dir, sport, season)
        for file in os.listdir(season_data_dir):
            if 'germany-bbl' in file and season == "2019-2020":
                continue

            championship_data_fpath = os.path.join(season_data_dir, file)
            championship = Championship(championship_data_fpath)
            championship.load_matches()

            top_teams_stats = (
                championship.compute_victories_and_defeats_for_the_best_m_teams_against_the_worst_n_teams(
                    best_teams_number=3,
                    worst_teams_number=3,
                    stabilization_round=10,
                    last_round_of_interest=championship.get_last_round_number()
                ))

            print("Championship", file, " - best teams results:", top_teams_stats)
            total_wins += top_teams_stats['wins']
            total_defeats += top_teams_stats['defeats']

    print("Wins", total_wins, "Defeats", total_defeats, "Win Rate", total_wins / (total_wins + total_defeats))


if __name__ == "__main__":
    main()
