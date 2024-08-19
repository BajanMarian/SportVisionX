import os
from datetime import datetime

import pandas as pd

from models.match import Match, Sport
from typing import List, Dict, Optional


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

            if row['home_score_by_period'] is None or row['away_score_by_period'] is None:
                home_score_by_period = row['home_score_by_period'].split('-')
                away_score_by_period = row['away_score_by_period'].split('-')
                for i in range(len(home_score_by_period)):
                    m.add_period_scores(home_score_by_period[i], away_score_by_period[i])

            self.matches.append(m)

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

            if match.date < limit_date:
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
    ) -> Dict[str, int]:
        best_teams_stats = {"wins": 0, "defeats": 0, "draw": 0}

        current_round = stabilization_round + 1
        while current_round <= last_round_of_interest:
            round_matches = self.get_matches_from_round(current_round)

            # compute standings and extract the first and last teams
            standings = self.compute_standings_before_round(current_round - 1)
            best_teams_group = Championship.extract_first_k_teams(standings, best_teams_number)
            worst_teams_group = Championship.extract_last_k_teams(standings, worst_teams_number)

            for match in round_matches:
                if match.home_team in best_teams_group and match.away_team in worst_teams_group:
                    if match.home_total_score > match.away_total_score:
                        best_teams_stats["wins"] += 1
                    elif match.home_total_score < match.away_total_score:
                        best_teams_stats["defeats"] += 1
                    else:
                        best_teams_stats["draw"] += 1
                elif match.home_team in worst_teams_group and match.away_team in best_teams_group:
                    if match.home_total_score > match.away_total_score:
                        best_teams_stats["defeats"] += 1
                    elif match.home_total_score < match.away_total_score:
                        best_teams_stats["wins"] += 1
                    else:
                        best_teams_stats["draw"] += 1
            current_round += 1

        return best_teams_stats
