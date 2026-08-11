from __future__ import annotations

from datetime import date

from scripts.final_modeling_pass import build_feature_rows
from scripts.tensor_v3_exact_scoring import exact_match_probability, exact_tiebreak_probability, posterior_match_probability
from tests.test_final_modeling_pass import synthetic_match_on


def test_future_result_cannot_change_earlier_feature_row() -> None:
    earlier = synthetic_match_on("A", "B", "R32", date(2024, 1, 1), "event-1")
    future_one = synthetic_match_on("C", "A", "R32", date(2024, 2, 1), "event-2")
    future_two = synthetic_match_on("A", "C", "R32", date(2024, 2, 1), "event-2")
    rows_one, _, _ = build_feature_rows([earlier, future_one])
    rows_two, _, _ = build_feature_rows([earlier, future_two])
    meta = {"index", "date", "year", "tour", "tournament", "surface", "level", "round", "player1", "player2", "label"}
    features = sorted(set(rows_one.columns) - meta)
    assert rows_one.iloc[0][features].to_dict() == rows_two.iloc[0][features].to_dict()


def test_exact_scoring_is_antisymmetric() -> None:
    p_ab = exact_match_probability(0.66, 0.61, 3)
    p_ba = exact_match_probability(0.61, 0.66, 3)
    assert abs(p_ab + p_ba - 1.0) < 1e-10


def test_tiebreak_symmetry_and_bounds() -> None:
    probability = exact_tiebreak_probability(0.64, 0.58, True)
    reversed_probability = exact_tiebreak_probability(0.58, 0.64, False)
    assert 0.0 < probability < 1.0
    assert abs(probability + reversed_probability - 1.0) < 1e-10


def test_posterior_propagation_is_reproducible_and_bounded() -> None:
    first = posterior_match_probability(65, 35, 61, 39, samples=100, seed=9)
    second = posterior_match_probability(65, 35, 61, 39, samples=100, seed=9)
    assert first == second
    assert 0.0 < first["mean"] < 1.0
    assert first["credible_interval_95"][0] <= first["mean"] <= first["credible_interval_95"][1]
