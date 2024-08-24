import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import pandas as pd

from models.match import Match, Sport
from typing import List, Dict, Optional, Tuple


class Championship:

    def __init__(self, championship_data_file: str):
        if not os.path.isfile(championship_data_file):
            raise FileNotFoundError
        if not championship_data_file.endswith('.csv'):
            raise Exception('File extension not supported. Please provide a CSV file.')
        self.championship_data_file = championship_data_file
        self.matches: List[Match] = []

    def load_matches(self) -> None:
        """
        Loads all matches from championship_data_file into self.matches.
        """
        df = pd.read_csv(self.championship_data_file)
        for _, row in df.iterrows():
            m = Match(
                sport=Sport(row['sport']),
                home_team=row['home_team'],
                away_team=row['away_team'],
                home_total_score=int(row['home_total_score']),
                away_total_score=int(row['away_total_score']),
                match_date=datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S'),
                competition_round=row['round'],
            )

            if type(row['home_score_by_period']) is str and type(row['away_score_by_period']) is str:
                home_score_by_period = row['home_score_by_period'].split('-')
                away_score_by_period = row['away_score_by_period'].split('-')
                for i in range(len(home_score_by_period)):
                    m.add_period_scores(home_score_by_period[i], away_score_by_period[i])

            self.matches.append(m)

    def validate(self) -> str:

        if len(self.matches) == 0:
            return (f'{self.championship_data_file}: '
                    f'No match found. Please consider loading the matches before validating the championship.')

        all_teams = set()
        games_per_round = defaultdict(int)

        for match in self.matches:
            if "ROUND " in match.round:
                all_teams.add(match.home_team)
                all_teams.add(match.away_team)
                games_per_round[int(match.round.split(' ')[1])] += 1

        # Ensure that the data is correctly structured and organized by rounds
        if len(games_per_round.keys()) == 0:
            return f'{self.championship_data_file} does not have data structured and organized by rounds.'

        # Check for missing rounds
        max_round = max(games_per_round.keys())
        missing_rounds = []
        for match_round in range(1, max_round + 1):
            if match_round not in games_per_round:
                missing_rounds.append(match_round)

        if len(missing_rounds) > 0:
            return f'{self.championship_data_file} has missing round(s): {missing_rounds}.'

        # if the championship has an even number of teams, we expect 'teams_count/2' matches per round
        if len(all_teams) % 2 == 0:
            expected_games_count_per_round = int(len(all_teams) / 2)
            for round_id, games_played in games_per_round.items():

                if games_played != expected_games_count_per_round:
                    uncompleted_rds = {k: v for k, v in games_per_round.items() if v != expected_games_count_per_round}

                    max_rounds_count_in_uncompleted_rds = max(uncompleted_rds.values())
                    min_rounds_count_in_uncompleted_rds = min(uncompleted_rds.values())
                    # consider a maximum of 2 teams that have retired in the current season
                    if max_rounds_count_in_uncompleted_rds != min_rounds_count_in_uncompleted_rds \
                            or max_rounds_count_in_uncompleted_rds != expected_games_count_per_round - 1:
                        return (f'{self.championship_data_file} has uncompleted round(s): {uncompleted_rds}. '
                                f'Expected {expected_games_count_per_round} matches per round because the championship '
                                f'has {len(all_teams)} teams.')
        return ""

    def get_matches_from_round(self, championship_round: str | int) -> List[Match]:

        if type(championship_round) is int:
            championship_round = "ROUND " + str(championship_round)

        round_matches = list(filter(lambda match: match.round == championship_round, self.matches))
        return round_matches

    def get_last_round_number(self) -> int:
        final_round = 0
        for match in self.matches:
            if match.round.startswith("ROUND"):
                current_round = int(match.round.split(" ")[1])
                if current_round > final_round:
                    final_round = current_round

        return final_round

    @staticmethod
    def get_last_match_date_from_round(round_matches: List[Match]) -> Optional[datetime]:

        if len(round_matches) == 0:
            return None

        # sort dates in descending order
        datetime_list = sorted([match.date for match in round_matches], reverse=True)

        # A round typically spans 4 consecutive days, but matches may occasionally be rescheduled.
        # By sorting the datetime_list, the middle element likely represents a match played
        # within the expected timeframe for round X.
        middle_datetime = datetime_list[len(datetime_list) // 2]

        for last_match_datetime in datetime_list:
            if abs((last_match_datetime - middle_datetime).days) < 4:
                return last_match_datetime

        return middle_datetime

    def compute_standings_before_round(self, championship_round: int) -> Dict[str, Dict[str, int]]:

        previous_round_matches = self.get_matches_from_round(championship_round - 1)
        limit_date = self.get_last_match_date_from_round(previous_round_matches)

        # all matches played before the limit_date will be taken into consideration

        standings = {}
        for match in self.matches:
            if match.home_team not in standings:
                standings[match.home_team] = {
                    "points": 0,
                    "games": 0
                }

            if match.away_team not in standings:
                standings[match.away_team] = {
                    "points": 0,
                    "games": 0
                }

            if match.date <= limit_date:
                points = match.compute_points()
                standings[match.home_team]["points"] += points[0]
                standings[match.away_team]["points"] += points[1]
                standings[match.home_team]["games"] += 1
                standings[match.away_team]["games"] += 1

        standings = dict(sorted(
            {
                key: value
                for key, value in standings.items()
                if value["games"] != 0
            }.items(),
            key=lambda item: -(item[1]["points"] / item[1]["games"])
        ))

        return standings

    @staticmethod
    def extract_first_k_teams(standings: Dict[str, Dict[str, int]], k: int) -> List[str]:
        sorted_standings = dict(sorted(
            standings.items(),
            key=lambda item: -(item[1]["points"] / item[1]["games"])
        ))
        return list(sorted_standings.keys())[:k]

    @staticmethod
    def extract_last_k_teams(standings: Dict[str, Dict[str, int]], k: int) -> List[str]:
        sorted_standings = dict(sorted(
            standings.items(),
            key=lambda item: item[1]["points"] / item[1]["games"]
        ))
        return list(sorted_standings.keys())[:k]

    def compute_victories_and_defeats_for_the_best_m_teams_against_the_worst_n_teams(
            self,
            best_teams_number: int,
            worst_teams_number: int,
            stabilization_round: int,
            last_round_of_interest: int,
    ) -> Tuple[Dict[str, int], Dict[str, List[Match]]]:

        best_teams_stats = {'wins': 0, 'defeats': 0, 'draws': 0}
        best_teams_matches = {'best_teams_victory': [], 'best_teams_defeats': [], 'draws': []}

        current_round = stabilization_round + 1
        while current_round <= last_round_of_interest:
            round_matches = self.get_matches_from_round(current_round)

            # compute standings and extract the first and last teams
            standings = self.compute_standings_before_round(current_round)
            best_teams_group = Championship.extract_first_k_teams(standings, best_teams_number)
            worst_teams_group = Championship.extract_last_k_teams(standings, worst_teams_number)

            for match in round_matches:
                if (match.home_team in best_teams_group and match.away_team in worst_teams_group) or \
                        (match.home_team in worst_teams_group and match.away_team in best_teams_group):

                    winner = match.get_winner()
                    if winner in best_teams_group:
                        best_teams_stats['wins'] += 1
                        best_teams_matches['best_teams_victory'].append(match)
                    elif winner in worst_teams_group:
                        best_teams_stats['defeats'] += 1
                        best_teams_matches['best_teams_defeats'].append(match)
                    else:
                        best_teams_stats['draws'] += 1
                        best_teams_matches['draws'].append(match)

            current_round += 1

        return best_teams_stats, best_teams_matches
