import argparse
import os
import sys
from typing import List, Tuple

from models.championship import Championship


def get_seasons(desired_start_year: int) -> List[str]:
    seasons = []
    for season_start_year in range(desired_start_year, 2023):
        seasons.append(f"{season_start_year}-{season_start_year + 1}")

    return seasons


def parse_input() -> Tuple[str, str]:
    parser = argparse.ArgumentParser(description='Read sport input directory and output file with statistics')

    parser.add_argument('--sport_dir', type=str, required=True, help='Sport specific directory')
    parser.add_argument('--outfile', type=str, required=True, help='Output file with statistics')

    args = parser.parse_args()
    sport_dir_path = args.sport_dir
    out_file_path = args.outfile

    if not os.path.exists(sport_dir_path):
        print(f'Error: Input data directory {sport_dir_path} does not exist.', file=sys.stderr)
        sys.exit(1)

    return sport_dir_path, out_file_path


def main():
    sport_data_dir, outfile = parse_input()

    best_teams_all_wins = 0
    best_teams_all_draws = 0
    best_teams_all_defeats = 0

    with open(outfile, 'w+') as f:
        for season_data in os.listdir(sport_data_dir):
            season_data_dir = os.path.join(sport_data_dir, season_data)
            f.write(f'Stats season {season_data}\n')
            for file in os.listdir(season_data_dir):

                if ('germany-bbl' in file or 'italy-lega-a' in file) and season_data == "2019-2020":
                    continue

                if 'usa-nba' in file:
                    continue

                championship_data_fpath = os.path.join(season_data_dir, file)
                championship = Championship(championship_data_fpath)
                championship.load_matches()

                top_teams_stats = (
                    championship.compute_victories_and_defeats_for_the_best_m_teams_against_the_worst_n_teams(
                        best_teams_number=3,
                        worst_teams_number=3,
                        stabilization_round=7,
                        last_round_of_interest=championship.get_last_round_number()
                    ))

                f.write(f'Championship {file} - best teams results: {top_teams_stats}.\n')
                best_teams_all_wins += top_teams_stats['wins']
                best_teams_all_draws += top_teams_stats['draws']
                best_teams_all_defeats += top_teams_stats['defeats']
            f.write('\n\n')

        f.write("Best teams overall statistics:\n")
        f.write(f" - total wins: {best_teams_all_wins}\n")
        f.write(f" - total defeats: {best_teams_all_defeats}\n")
        f.write(f" - total draws: {best_teams_all_draws}\n")
        f.write(f" - win_rate: "
                f"{best_teams_all_wins/sum([best_teams_all_draws, best_teams_all_wins, best_teams_all_defeats])}")


if __name__ == "__main__":
    main()
