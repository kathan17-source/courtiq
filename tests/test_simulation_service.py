from __future__ import annotations

import unittest

from backend.app.services.simulation_service import simulate_match_probability, simulate_tournament_draw


class SimulationServiceTests(unittest.TestCase):
    def test_simulation_is_reproducible_with_seed(self) -> None:
        first = simulate_match_probability(0.03, 1000, seed=99)
        second = simulate_match_probability(0.03, 1000, seed=99)
        self.assertEqual(first.player1_win_probability, second.player1_win_probability)

    def test_rejects_non_positive_simulation_count(self) -> None:
        with self.assertRaises(ValueError):
            simulate_match_probability(0.03, 0)

    def test_tournament_draw_is_reproducible(self) -> None:
        def fake_predict(player1: str, player2: str) -> float:
            return 0.65 if player1 < player2 else 0.35

        first = simulate_tournament_draw(["A", "B", "C", "D"], tour="atp", event="Wimbledon", simulations=50, seed=9, predictor=fake_predict)
        second = simulate_tournament_draw(["A", "B", "C", "D"], tour="atp", event="Wimbledon", simulations=50, seed=9, predictor=fake_predict)
        self.assertEqual(first["probabilities"], second["probabilities"])

    def test_pair_probabilities_are_precomputed_once(self) -> None:
        calls = []
        def fake_predict(player1: str, player2: str) -> float:
            calls.append((player1, player2))
            return 0.5
        simulate_tournament_draw(["A", "B", "C", "D"], "atp", "Wimbledon", 100, predictor=fake_predict)
        self.assertEqual(len(calls), 6)

    def test_rejects_excessive_work(self) -> None:
        with self.assertRaises(ValueError):
            simulate_tournament_draw(["A", "B"], "atp", "Wimbledon", 10_001, predictor=lambda *_: 0.5)


if __name__ == "__main__":
    unittest.main()
