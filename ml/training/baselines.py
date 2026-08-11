from __future__ import annotations

from backend.app.services.elo_service import PlayerRating, update_pair


def train_surface_elo(matches: list[dict[str, str]]) -> dict[str, PlayerRating]:
    ratings: dict[str, PlayerRating] = {}
    for row in matches:
        winner_name = row["winner"]
        loser_name = row["loser"]
        surface = row.get("surface", "hard")
        winner = ratings.setdefault(winner_name, PlayerRating())
        loser = ratings.setdefault(loser_name, PlayerRating())
        update_pair(winner, loser, surface)
    return ratings
