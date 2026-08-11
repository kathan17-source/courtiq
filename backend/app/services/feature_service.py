from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MatchFeatureRow:
    match_date: date | None
    player1: str
    player2: str
    surface: str
    overall_elo_diff: float
    surface_elo_diff: float
    rolling_form_5_diff: float = 0.0
    rolling_form_10_diff: float = 0.0
    days_rest_diff: float = 0.0
    h2h_prior_diff: float = 0.0
    best_of: int = 3


FEATURE_DEFINITIONS = {
    "overall_elo_diff": "player1 overall Elo before match minus player2 overall Elo before match.",
    "surface_elo_diff": "player1 surface Elo before match minus player2 surface Elo before match.",
    "rolling_form_5_diff": "player1 win rate in previous 5 matches minus player2 previous 5-match win rate.",
    "rolling_form_10_diff": "player1 win rate in previous 10 matches minus player2 previous 10-match win rate.",
    "days_rest_diff": "days since player1 previous match minus days since player2 previous match.",
    "h2h_prior_diff": "player1 wins against player2 before this match minus player2 wins against player1 before this match.",
}


def as_model_vector(row: MatchFeatureRow) -> list[float]:
    return [
        row.overall_elo_diff,
        row.surface_elo_diff,
        row.rolling_form_5_diff,
        row.rolling_form_10_diff,
        row.days_rest_diff,
        row.h2h_prior_diff,
        float(row.best_of == 5),
    ]

