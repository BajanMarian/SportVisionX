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

    data_problems_file = os.path.join(os.path.dirname(outfile), 'crawled_data_issues.txt')

    with open(outfile, 'w+', encoding='utf-8') as f, open(data_problems_file, 'w+') as pf:
        data_files_count = 0
        problematic_files_count = 0
        for season_data in os.listdir(sport_data_dir):

            f.write(f'Stats season {season_data}\n')
            season_data_dir = os.path.join(sport_data_dir, season_data)

            for file in os.listdir(season_data_dir):

                # if ('germany-bbl' in file or 'italy-lega-a' in file) and season_data == "2019-2020":
                #     continue
                #
                # if 'usa-nba' in file:
                #     continue

                championship_data_fpath = os.path.join(season_data_dir, file)
                championship = Championship(championship_data_fpath)
                championship.load_matches()
                data_files_count += 1

                validation_result = championship.validate()
                if validation_result != "":
                    problematic_files_count += 1
                    pf.write(f'!!! [Data Validation Error] {validation_result} !!!\n')
                    continue

                top_teams_stats, top_teams_matches = (
                    championship.compute_victories_and_defeats_for_the_best_m_teams_against_the_worst_n_teams(
                        best_teams_number=3,
                        worst_teams_number=3,
                        stabilization_round=7,
                        last_round_of_interest=championship.get_last_round_number()
                    ))

                f.write(f'\nChampionship {file} - best teams results: {top_teams_stats}.\n')
                f.write('Matches insights:\n')
                for outcome_details, matches in top_teams_matches.items():
                    if len(matches) == 0:
                        continue
                    f.write(f'\t{outcome_details}:\n')
                    for match in matches:
                        match_info = match.to_dict()
                        del match_info['date']
                        del match_info['sport']
                        f.write(f'\t\t{match_info.values()}\n')

                best_teams_all_wins += top_teams_stats['wins']
                best_teams_all_draws += top_teams_stats['draws']
                best_teams_all_defeats += top_teams_stats['defeats']
            f.write('\n\n')

        win_rate = best_teams_all_wins / sum([best_teams_all_wins, best_teams_all_defeats, best_teams_all_draws])
        overall_stats = (
            'Best teams overall statistics:\n'
            f' - Total wins: {best_teams_all_wins}\n'
            f' - Total defeats: {best_teams_all_defeats}\n'
            f' - Total draws: {best_teams_all_draws}\n'
            f' - Win rate: {win_rate:.2%}\n\n'  # Format win rate as a percentage with 2 decimal places
            f'NOTE: Identified {problematic_files_count} problematic files out of {data_files_count} data files.\n'
            f'The discovered issues have been written to the {data_problems_file} file.'
        )
        f.write(overall_stats)


if __name__ == "__main__":
    main()
