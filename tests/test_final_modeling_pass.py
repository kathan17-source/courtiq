from __future__ import annotations

import unittest
from datetime import date

from scripts.final_modeling_pass import (
    PlayerState,
    RawMatch,
    build_feature_rows,
    latent_exact_match_probability,
    latent_skill,
)


def synthetic_match(winner: str, loser: str, round_name: str) -> RawMatch:
    return synthetic_match_on(winner, loser, round_name, date(2025, 1, 1), "2025-leakage-open")


def synthetic_match_on(winner: str, loser: str, round_name: str, match_date: date, tournament_id: str) -> RawMatch:
    return RawMatch(
        tour="atp",
        match_date=match_date,
        tournament_id=tournament_id,
        tournament="Leakage Open",
        surface="hard",
        level="250",
        indoor="O",
        round=round_name,
        best_of=3,
        winner=winner,
        loser=loser,
        winner_rank=10,
        loser_rank=20,
        winner_rank_points=3000,
        loser_rank_points=1500,
        winner_age=25,
        loser_age=26,
        winner_height=185,
        loser_height=183,
        winner_hand="R",
        loser_hand="R",
        score="6-4 6-4",
        stats={
            "w_svpt": 60.0,
            "l_svpt": 62.0,
            "w_service_won": 40.0,
            "l_service_won": 34.0,
            "w_return_won": 28.0,
            "l_return_won": 20.0,
            "w_ace": 5.0,
            "l_ace": 3.0,
            "w_df": 2.0,
            "l_df": 4.0,
            "w_first_in": 38.0,
            "l_first_in": 39.0,
            "w_first_won": 29.0,
            "l_first_won": 25.0,
            "w_second_total": 22.0,
            "l_second_total": 23.0,
            "w_second_won": 11.0,
            "l_second_won": 9.0,
            "w_bp_saved": 4.0,
            "l_bp_saved": 2.0,
            "w_bp_faced": 6.0,
            "l_bp_faced": 7.0,
            "w_bp_converted": 5.0,
            "l_bp_converted": 2.0,
            "w_bp_opps": 7.0,
            "l_bp_opps": 6.0,
        },
    )


class FinalModelingPassTests(unittest.TestCase):
    def test_same_round_results_do_not_feed_each_other(self) -> None:
        rows, _, _ = build_feature_rows(
            [
                synthetic_match("Player A", "Player B", "R32"),
                synthetic_match("Player A", "Player C", "R32"),
            ]
        )
        second = rows.sort_values("index").iloc[1]
        self.assertEqual(second["player1"], "Player A")
        self.assertEqual(second["player2"], "Player C")
        self.assertEqual(float(second["matches_diff"]), 0.0)
        self.assertEqual(float(second["residual_form_short_diff"]), 0.0)
        self.assertEqual(float(second["score_dominance_diff"]), 0.0)

    def test_completed_round_updates_later_round(self) -> None:
        rows, _, _ = build_feature_rows(
            [
                synthetic_match("Player A", "Player B", "R32"),
                synthetic_match("Player A", "Player C", "R16"),
            ]
        )
        later = rows.sort_values("index").iloc[1]
        self.assertEqual(later["player1"], "Player A")
        self.assertEqual(later["player2"], "Player C")
        self.assertGreater(float(later["matches_diff"]), 0.0)
        self.assertGreater(float(later["residual_form_short_diff"]), 0.0)

    def test_later_round_does_not_update_earlier_round_even_if_file_order_is_bad(self) -> None:
        rows, _, _ = build_feature_rows(
            [
                synthetic_match("Player A", "Player C", "R16"),
                synthetic_match("Player A", "Player B", "R32"),
            ]
        )
        earlier_round = rows[rows["round"] == "R32"].iloc[0]
        self.assertEqual({earlier_round["player1"], earlier_round["player2"]}, {"Player A", "Player B"})
        self.assertEqual(float(earlier_round["matches_diff"]), 0.0)
        self.assertEqual(float(earlier_round["residual_form_short_diff"]), 0.0)

    def test_later_round_metadata_cannot_rewrite_earlier_snapshot(self) -> None:
        earlier = synthetic_match("Player A", "Player B", "R32")
        later = synthetic_match("Player A", "Player C", "R16")
        later.winner_rank = 1
        later.winner_rank_points = 12000
        rows, _, _ = build_feature_rows([later, earlier])
        first = rows[rows["round"] == "R32"].iloc[0]
        self.assertAlmostEqual(abs(float(first["ranking_diff"])), 10 / 998, places=6)
        self.assertAlmostEqual(abs(float(first["ranking_points_diff"])), 1500 / 12000, places=6)

    def test_latent_serve_return_exact_probability_is_bounded(self) -> None:
        a = PlayerState("Player A", "atp")
        b = PlayerState("Player B", "atp")
        probability = latent_exact_match_probability(a, b, "hard", 3)
        self.assertGreater(probability, 0.0)
        self.assertLess(probability, 1.0)
        self.assertIn("uncertainty", latent_skill(a, "hard"))

    def test_common_opponent_features_are_time_safe_and_nonzero_later(self) -> None:
        rows, _, _ = build_feature_rows(
            [
                synthetic_match_on("Player A", "Shared X", "R32", date(2024, 1, 1), "event-1"),
                synthetic_match_on("Player B", "Shared X", "R32", date(2024, 2, 1), "event-2"),
                synthetic_match_on("Player A", "Player B", "R32", date(2024, 3, 1), "event-3"),
            ]
        )
        later = rows.sort_values("date").iloc[-1]
        self.assertGreater(float(later["common_opponent_match_weight"]), 0.0)
        self.assertGreaterEqual(abs(float(later["common_opponent_result_residual_diff"])), 0.0)


if __name__ == "__main__":
    unittest.main()
