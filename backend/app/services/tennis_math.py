from __future__ import annotations

from functools import lru_cache
from math import exp
from random import Random


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + exp(-value))


def game_win_probability(point_probability: float) -> float:
    p = clamp(point_probability, 0.01, 0.99)
    q = 1.0 - p
    before_deuce = (p**4) * (1 + 4 * q + 10 * (q**2))
    reach_deuce = 20 * (p**3) * (q**3)
    win_from_deuce = (p**2) / ((p**2) + (q**2))
    return before_deuce + reach_deuce * win_from_deuce


def game_win_probability_dp(point_probability: float) -> float:
    p = clamp(point_probability, 0.01, 0.99)

    @lru_cache(maxsize=None)
    def solve(server_points: int, returner_points: int) -> float:
        if server_points >= 4 and server_points - returner_points >= 2:
            return 1.0
        if returner_points >= 4 and returner_points - server_points >= 2:
            return 0.0
        if server_points >= 3 and returner_points >= 3:
            diff = server_points - returner_points
            if diff == 0:
                q = 1.0 - p
                return (p * p) / ((p * p) + (q * q))
            if diff == 1:
                return p + (1.0 - p) * solve(3, 3)
            if diff == -1:
                return p * solve(3, 3)
        return p * solve(server_points + 1, returner_points) + (1.0 - p) * solve(server_points, returner_points + 1)

    return solve(0, 0)


def set_win_probability_from_hold(p1_hold: float, p2_hold: float, p1_serves_first: bool = True, tiebreak: bool = True) -> float:
    p1_hold = clamp(p1_hold, 0.01, 0.99)
    p2_hold = clamp(p2_hold, 0.01, 0.99)

    @lru_cache(maxsize=None)
    def solve(games_a: int, games_b: int, server_turn: int) -> float:
        if games_a >= 6 and games_a - games_b >= 2:
            return 1.0
        if games_b >= 6 and games_b - games_a >= 2:
            return 0.0
        if games_a == 6 and games_b == 6 and tiebreak:
            return 0.5 + 0.45 * (p1_hold - p2_hold)
        if games_a >= 7:
            return 1.0
        if games_b >= 7:
            return 0.0
        p_game_a = p1_hold if ((server_turn % 2 == 0) == p1_serves_first) else (1.0 - p2_hold)
        return p_game_a * solve(games_a + 1, games_b, server_turn + 1) + (1.0 - p_game_a) * solve(games_a, games_b + 1, server_turn + 1)

    return clamp(solve(0, 0, 0), 0.0, 1.0)


def match_win_from_set(set_probability: float, best_of: int) -> float:
    p = clamp(set_probability, 0.01, 0.99)
    if best_of == 5:
        return (p**3) * (1 + 3 * (1 - p) + 6 * ((1 - p) ** 2))
    return (p**2) * (3 - 2 * p)


def monte_carlo_game_probability(point_probability: float, simulations: int = 5000, seed: int = 7) -> float:
    rng = Random(seed)
    wins = 0
    for _ in range(simulations):
        server = 0
        returner = 0
        while True:
            if rng.random() < point_probability:
                server += 1
            else:
                returner += 1
            if server >= 4 and server - returner >= 2:
                wins += 1
                break
            if returner >= 4 and returner - server >= 2:
                break
    return wins / simulations
