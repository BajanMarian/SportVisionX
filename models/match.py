from datetime import datetime
from enum import Enum
from typing import Tuple, List


class Sport(Enum):
    TENNIS = "Tennis"
    HOCKEY = "Hockey"
    FOOTBALL = "Football"
    HANDBALL = "Handball"
    BASKETBALL = "Basketball"
    VOLLEYBALL = "Volleyball"


class Match:
    _DRAW = "Draw"

    def __init__(
            self,
            sport: Sport,
            home_team: str,
            away_team: str,
            home_total_score: int,
            away_total_score: int,
            match_date: datetime,
            competition_round: str
    ):
        if not isinstance(sport, Sport):
            raise ValueError(f'Sport must be an instance of Sport Enum. Got {type(sport)}.')

        self.home_team = home_team
        self.away_team = away_team
        self.home_total_score = home_total_score
        self.away_total_score = away_total_score
        self.sport = sport
        self.date = match_date
        self.round = competition_round

        self.home_score_by_period: List[int] = []
        self.away_score_by_period: List[int] = []

    def __str__(self):
        periods = f'{"-".join(map(str, self.home_score_by_period))},{"-".join(map(str, self.away_score_by_period))}'
        return (f'{self.sport},{self.date},{self.home_team},{self.away_team},'
                f'{self.home_total_score},{self.away_total_score},{periods}')

    def add_period_scores(self, home_score, away_score) -> None:
        self.home_score_by_period.append(home_score)
        self.away_score_by_period.append(away_score)

    def get_winner(self) -> str:
        if self.home_total_score > self.away_total_score:
            return self.home_team
        elif self.home_total_score < self.away_total_score:
            return self.away_team
        return self._DRAW

    def to_dict(self):
        return {
            "sport": self.sport.value,
            "date": self.date,
            "round": self.round,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "home_total_score": self.home_total_score,
            "away_total_score": self.away_total_score,
            "home_score_by_period": "-".join(map(str, self.home_score_by_period)),
            "away_score_by_period": "-".join(map(str, self.away_score_by_period)),
        }

    def enhance_match_date(self, season_start_year: int, season_start_month: int):
        if self.date.month >= season_start_month:
            self.date = self.date.replace(year=season_start_year)
        else:
            self.date = self.date.replace(year=season_start_year + 1)

    def compute_points(self) -> Tuple[int, int]:

        point_system = {
            Sport.FOOTBALL: (3, 1),  # 3 points for a win, 1 point each for a draw
            Sport.HANDBALL: (2, 1),  # 2 points for a win, 1 point each for a draw
            Sport.BASKETBALL: (2, 0),  # 2 points for a win, no draw
            Sport.HOCKEY: (2, 1),  # 2 points for a win, 1 point each for a draw
            Sport.VOLLEYBALL: (3, (2, 1)),  # if score is 3-0 or 3-1, 3 points for a win
                                            # if score is 3-2, 2 points for a win and 1 point for a loss
            Sport.TENNIS: (0, 0)  # typically not point-based, so 0 for both
        }

        if self.sport == Sport.TENNIS:
            raise Exception("compute_points() method does not handle volleyball or tennis matches.")

        victory_points, draw_points = point_system[self.sport]
        defeat_points = 0

        if self.sport == Sport.VOLLEYBALL and self.home_total_score + self.away_total_score == 5:
            victory_points, defeat_points = draw_points

        if self.home_total_score > self.away_total_score:
            return victory_points, defeat_points
        elif self.away_total_score > self.home_total_score:
            return defeat_points, victory_points

        return draw_points, draw_points

    @classmethod
    def draw(cls) -> str:
        return cls._DRAW
