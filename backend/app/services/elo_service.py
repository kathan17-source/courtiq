from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

SURFACES = ("hard", "clay", "grass")


@dataclass
class PlayerRating:
    overall: float = 1500.0
    surface: dict[str, float] = field(default_factory=lambda: {surface: 1500.0 for surface in SURFACES})
    matches: int = 0
    uncertainty: float = 85.0


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def recency_weight(days_old: float, half_life_days: float = 365.0 * 1.5) -> float:
    if days_old <= 0:
        return 1.0
    return exp(-(0.6931471805599453 / half_life_days) * days_old)


def blended_rating(player: PlayerRating, surface: str) -> float:
    surface_rating = player.surface.get(surface, player.overall)
    return 0.62 * surface_rating + 0.30 * player.overall - 0.08 * player.uncertainty


def update_pair(winner: PlayerRating, loser: PlayerRating, surface: str, best_of: int = 3, k_base: float = 18.0) -> float:
    surface = surface if surface in SURFACES else "hard"
    expected = expected_score(blended_rating(winner, surface), blended_rating(loser, surface))
    importance = 1.08 if best_of == 5 else 1.0
    experience_drag = 1.0 / (1.0 + min(winner.matches, loser.matches) / 140.0)
    k = (k_base + k_base * experience_drag) * importance
    delta = k * (1.0 - expected)
    winner.overall += delta * 0.42
    loser.overall -= delta * 0.42
    winner.surface[surface] = winner.surface.get(surface, winner.overall) + delta * 0.72
    loser.surface[surface] = loser.surface.get(surface, loser.overall) - delta * 0.72
    winner.matches += 1
    loser.matches += 1
    winner.uncertainty = max(28.0, winner.uncertainty * 0.992)
    loser.uncertainty = max(28.0, loser.uncertainty * 0.992)
    return delta

