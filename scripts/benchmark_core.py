from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.elo_service import PlayerRating, blended_rating, expected_score, update_pair
from backend.app.services.feature_service import MatchFeatureRow, as_model_vector
from backend.app.services.simulation_service import simulate_match_probability
from backend.app.services.tennis_math import clamp, game_win_probability, match_win_from_set, sigmoid
from backend.app.services.video_analysis import Point2D, joint_angle
from ml.features.build_features import RawMatch, build_minimal_feature_row


def measure(label: str, fn) -> dict:  # type: ignore[no-untyped-def]
    started = perf_counter()
    result = fn()
    elapsed = (perf_counter() - started) * 1000
    return {"name": label, "elapsed_ms": round(elapsed, 3), **result}


def benchmark_preprocessing() -> dict:
    rows = [
        RawMatch(
            match_date=date(2024, 1, 1) + timedelta(days=i % 365),
            winner=f"Player {i % 200}",
            loser=f"Player {(i + 7) % 200}",
            tournament=f"Tournament {i % 40}",
            surface=("Hard", "Clay", "Grass")[i % 3],
            best_of=5 if i % 17 == 0 else 3,
        )
        for i in range(10_000)
    ]
    built = [build_minimal_feature_row(row, 1520 + (i % 100), 1490 + (i % 80)) for i, row in enumerate(rows)]
    return {"rows": len(built)}


def benchmark_elo() -> dict:
    players = [PlayerRating() for _ in range(256)]
    for i in range(10_000):
        update_pair(players[i % 256], players[(i * 7 + 11) % 256], ("hard", "clay", "grass")[i % 3], best_of=5 if i % 19 == 0 else 3)
    return {"matches": 10_000}


def benchmark_features() -> dict:
    rows = [
        MatchFeatureRow(
            match_date=date(2024, 1, 1),
            player1="A",
            player2="B",
            surface="hard",
            overall_elo_diff=i % 300 - 150,
            surface_elo_diff=i % 220 - 110,
            rolling_form_5_diff=(i % 10) / 10,
            rolling_form_10_diff=(i % 20) / 20,
            days_rest_diff=i % 6,
            h2h_prior_diff=i % 5 - 2,
            best_of=5 if i % 11 == 0 else 3,
        )
        for i in range(10_000)
    ]
    vectors = [as_model_vector(row) for row in rows]
    return {"feature_rows": len(vectors), "features_per_row": len(vectors[0])}


def benchmark_prediction() -> dict:
    p1 = PlayerRating(overall=1620)
    p2 = PlayerRating(overall=1580)
    p1.surface.update({"hard": 1640, "clay": 1570, "grass": 1610})
    p2.surface.update({"hard": 1560, "clay": 1630, "grass": 1540})
    for _ in range(10_000):
        p1_rating = blended_rating(p1, "hard")
        p2_rating = blended_rating(p2, "hard")
        elo_prior = expected_score(p1_rating, p2_rating)
        point_edge = clamp((p1_rating - p2_rating) / 1150.0, -0.11, 0.11)
        p1_hold = game_win_probability(clamp(0.635 + point_edge, 0.50, 0.78))
        p2_hold = game_win_probability(clamp(0.635 - point_edge, 0.50, 0.78))
        set_probability = sigmoid((p1_hold - p2_hold) * 3.4)
        _ = clamp(0.62 * match_win_from_set(set_probability, 3) + 0.38 * elo_prior, 0.02, 0.98)
    return {"predictions": 10_000}


def benchmark_api_prediction_endpoint() -> dict:
    try:
        from fastapi.testclient import TestClient
        from backend.app.main import app
    except ModuleNotFoundError as exc:
        return {"status": "skipped", "reason": f"optional dependency unavailable: {exc.name}"}

    client = TestClient(app)
    payload = {
        "player1": "Carlos Alcaraz",
        "player2": "Jannik Sinner",
        "event": "Wimbledon",
        "tour": "atp",
        "allow_demo": True,
    }
    ok = 0
    for _ in range(100):
        response = client.post("/api/predict", json=payload)
        ok += int(response.status_code == 200)
    return {"requests": 100, "successful_requests": ok}


def benchmark_tournament_simulation() -> dict:
    # A lightweight 16-player tournament proxy: 15 match simulations per bracket.
    winners = 0
    for i in range(10_000):
        result = simulate_match_probability(0.02 + ((i % 7) - 3) / 500, simulations=15, seed=1000 + i)
        winners += int(result.player1_win_probability >= 0.5)
    return {"tournament_simulations": 10_000, "bracket_matchups_per_simulation": 15, "top_seed_proxy_wins": winners}


def benchmark_video_angles() -> dict:
    a = Point2D(0.1, 0.2)
    b = Point2D(0.5, 0.6)
    c = Point2D(0.8, 0.3)
    total = 0.0
    for _ in range(100_000):
        total += joint_angle(a, b, c)
    return {"joint_angles": 100_000, "checksum": round(total, 3)}


if __name__ == "__main__":
    benchmark_plan = [
        ("data_preprocessing_10k_rows", benchmark_preprocessing),
        ("elo_updates_10k_matches", benchmark_elo),
        ("feature_generation_10k_rows", benchmark_features),
        ("api_prediction_math_10k_calls", benchmark_prediction),
        ("api_prediction_endpoint_100_requests", benchmark_api_prediction_endpoint),
        ("tournament_simulation_10k_brackets", benchmark_tournament_simulation),
        ("video_joint_angle_100k_frames", benchmark_video_angles),
    ]
    results = [measure(label, fn) for label, fn in benchmark_plan]
    for item in results:
        measurable = item.get("rows") or item.get("matches") or item.get("feature_rows") or item.get("predictions") or item.get("tournament_simulations") or item.get("joint_angles")
        if measurable:
            item["throughput_per_second"] = round(measurable / max(item["elapsed_ms"] / 1000, 1e-9), 2)
    out = ROOT / "output/benchmarks/core_benchmarks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"benchmarks": results}, indent=2), encoding="utf-8")
    print(json.dumps({"benchmarks": results}, indent=2))
