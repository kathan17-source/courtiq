from __future__ import annotations

from functools import lru_cache

import numpy as np

from backend.app.services.tennis_math import game_win_probability, match_win_from_set


def tiebreak_server_is_a(total_points: int, first_server_is_a: bool = True) -> bool:
    serves_a = total_points == 0 or total_points % 4 in {0, 3}
    return serves_a if first_server_is_a else not serves_a


def exact_tiebreak_probability(p_a_serve: float, p_b_serve: float, first_server_is_a: bool = True) -> float:
    """Exact standard first-to-seven, win-by-two tiebreak probability.

    The infinite 6-6 tail is represented as a finite periodic Markov chain and
    solved as a linear system; the pre-6 states use memoized recursion.
    """
    pa, pb = float(p_a_serve), float(p_b_serve)
    if not (0 < pa < 1 and 0 < pb < 1):
        raise ValueError("Service-point probabilities must be strictly between zero and one")

    states = [(diff, mod) for diff in (-1, 0, 1) for mod in range(4) if (mod - abs(diff)) % 2 == 0]
    index = {state: i for i, state in enumerate(states)}
    matrix = np.eye(len(states))
    rhs = np.zeros(len(states))
    for state, row in index.items():
        diff, mod = state
        a_serves = tiebreak_server_is_a(mod, first_server_is_a)
        p_a_point = pa if a_serves else 1.0 - pb
        for next_diff, probability in ((diff + 1, p_a_point), (diff - 1, 1.0 - p_a_point)):
            if next_diff >= 2:
                rhs[row] += probability
            elif next_diff <= -2:
                continue
            else:
                matrix[row, index[(next_diff, (mod + 1) % 4)]] -= probability
    tail = np.linalg.solve(matrix, rhs)

    @lru_cache(maxsize=None)
    def solve(a: int, b: int) -> float:
        if a >= 7 and a - b >= 2:
            return 1.0
        if b >= 7 and b - a >= 2:
            return 0.0
        if a >= 6 and b >= 6:
            return float(tail[index[(a - b, (a + b) % 4)]])
        total = a + b
        p_a_point = pa if tiebreak_server_is_a(total, first_server_is_a) else 1.0 - pb
        return p_a_point * solve(a + 1, b) + (1.0 - p_a_point) * solve(a, b + 1)

    return solve(0, 0)


def exact_set_probability(p_a_serve: float, p_b_serve: float, first_server_is_a: bool = True) -> float:
    hold_a = game_win_probability(p_a_serve)
    hold_b = game_win_probability(p_b_serve)

    @lru_cache(maxsize=None)
    def solve(games_a: int, games_b: int, next_server_a: bool) -> float:
        if games_a >= 6 and games_a - games_b >= 2:
            return 1.0
        if games_b >= 6 and games_b - games_a >= 2:
            return 0.0
        if games_a == 6 and games_b == 6:
            return exact_tiebreak_probability(p_a_serve, p_b_serve, next_server_a)
        p_a_game = hold_a if next_server_a else 1.0 - hold_b
        return p_a_game * solve(games_a + 1, games_b, not next_server_a) + (1.0 - p_a_game) * solve(games_a, games_b + 1, not next_server_a)

    return solve(0, 0, first_server_is_a)


def exact_match_probability(p_a_serve: float, p_b_serve: float, best_of: int = 3) -> float:
    # Unknown first server is integrated symmetrically rather than guessed.
    set_probability = 0.5 * (
        exact_set_probability(p_a_serve, p_b_serve, True)
        + exact_set_probability(p_a_serve, p_b_serve, False)
    )
    return match_win_from_set(set_probability, best_of)


def posterior_match_probability(
    a_alpha: float,
    a_beta: float,
    b_alpha: float,
    b_beta: float,
    *,
    best_of: int = 3,
    samples: int = 2000,
    seed: int = 20260810,
) -> dict[str, float | list[float]]:
    rng = np.random.default_rng(seed)
    a = rng.beta(a_alpha, a_beta, samples)
    b = rng.beta(b_alpha, b_beta, samples)
    probabilities = np.array([exact_match_probability(float(pa), float(pb), best_of) for pa, pb in zip(a, b, strict=True)])
    low, high = np.quantile(probabilities, [0.025, 0.975])
    return {"mean": float(probabilities.mean()), "variance": float(probabilities.var()), "credible_interval_95": [float(low), float(high)], "samples": samples}
