from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class RawMatch:
    match_date: date
    winner: str
    loser: str
    tournament: str
    surface: str
    best_of: int = 3


def build_minimal_feature_row(match: RawMatch, winner_rating: float, loser_rating: float) -> dict[str, float | str | int]:
    """Build a leakage-safe feature row from information known before the match."""
    return {
        "match_date": match.match_date.isoformat(),
        "winner": match.winner,
        "loser": match.loser,
        "surface": match.surface,
        "best_of": match.best_of,
        "rating_diff": winner_rating - loser_rating,
    }
