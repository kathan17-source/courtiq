from __future__ import annotations

from dataclasses import dataclass
from random import Random
from time import perf_counter
from itertools import combinations

from backend.app.services.tennis_math import clamp


@dataclass(frozen=True)
class SimulationResult:
    simulations: int
    seed: int
    player1_win_probability: float
    elapsed_ms: float


def simulate_match_probability(player1_point_edge: float, simulations: int, seed: int = 42) -> SimulationResult:
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    if simulations > 10_000:
        raise ValueError("simulations must not exceed 10000")
    rng = Random(seed)
    p = clamp(0.5 + player1_point_edge, 0.35, 0.65)
    started = perf_counter()
    wins = 0
    for _ in range(simulations):
        p1_sets = 0
        p2_sets = 0
        while p1_sets < 2 and p2_sets < 2:
            p1_games = 0
            p2_games = 0
            while True:
                if rng.random() < p:
                    p1_games += 1
                else:
                    p2_games += 1
                if (p1_games >= 6 or p2_games >= 6) and abs(p1_games - p2_games) >= 2:
                    break
                if p1_games == 6 and p2_games == 6:
                    if rng.random() < p:
                        p1_games += 1
                    else:
                        p2_games += 1
                    break
            if p1_games > p2_games:
                p1_sets += 1
            else:
                p2_sets += 1
        if p1_sets > p2_sets:
            wins += 1
    elapsed_ms = (perf_counter() - started) * 1000
    return SimulationResult(
        simulations=simulations,
        seed=seed,
        player1_win_probability=wins / simulations,
        elapsed_ms=round(elapsed_ms, 2),
    )


def benchmark_simulations(sizes: tuple[int, ...] = (1_000, 10_000), seed: int = 42) -> list[SimulationResult]:
    return [simulate_match_probability(0.035, size, seed=seed) for size in sizes]


def simulate_tournament_draw(
    players: list[str],
    tour: str,
    event: str,
    simulations: int = 10_000,
    seed: int = 42,
    predictor: object | None = None,
) -> dict[str, object]:
    if simulations <= 0:
        raise ValueError("simulations must be positive")
    if simulations > 10_000:
        raise ValueError("simulations must not exceed 10000")
    if len(players) > 128:
        raise ValueError("draw size must not exceed 128")
    if len(players) < 2 or len(players) & (len(players) - 1):
        raise ValueError("draw size must be a power of two with at least two players")
    if len({player.strip().lower() for player in players}) != len(players):
        raise ValueError("draw contains duplicate players")

    rng = Random(seed)
    rounds = draw_round_names(len(players))
    counts = {player: {round_name: 0 for round_name in rounds} for player in players}
    counts = {player: {**counts[player], "Champion": 0} for player in players}
    started = perf_counter()
    pair_probabilities: dict[tuple[str, str], float] = {}
    for p1, p2 in combinations(players, 2):
        if predictor is None:
            from backend.app.schemas.prediction import PredictionRequest
            from backend.app.services.prediction_service import predict_match
            value = predict_match(PredictionRequest(player1=p1, player2=p2, tour=tour, event=event)).player1_win_probability
        else:
            value = float(predictor(p1, p2))
        pair_probabilities[(p1, p2)] = value
        pair_probabilities[(p2, p1)] = 1.0 - value

    for _ in range(simulations):
        alive = list(players)
        round_index = 0
        while len(alive) > 1:
            winners: list[str] = []
            round_name = rounds[round_index]
            for index in range(0, len(alive), 2):
                p1, p2 = alive[index], alive[index + 1]
                probability = pair_probabilities[(p1, p2)]
                winner = p1 if rng.random() < probability else p2
                winners.append(winner)
                counts[winner][round_name] += 1
            alive = winners
            round_index += 1
        counts[alive[0]]["Champion"] += 1

    probabilities = {
        player: {key: round(value / simulations, 4) for key, value in player_counts.items()}
        for player, player_counts in counts.items()
    }
    return {
        "event": event,
        "tour": tour,
        "draw_size": len(players),
        "simulations": simulations,
        "seed": seed,
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "probabilities": probabilities,
    }


def draw_round_names(size: int) -> list[str]:
    names_by_size = {
        128: ["R64", "R32", "R16", "QF", "SF", "Final"],
        64: ["R32", "R16", "QF", "SF", "Final"],
        32: ["R16", "QF", "SF", "Final"],
        16: ["QF", "SF", "Final"],
        8: ["QF", "SF", "Final"],
        4: ["SF", "Final"],
        2: ["Final"],
    }
    if size in names_by_size:
        return names_by_size[size]
    rounds: list[str] = []
    current = size // 2
    while current > 1:
        rounds.append(f"R{current}")
        current //= 2
    rounds.append("Final")
    return rounds
