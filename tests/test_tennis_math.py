from __future__ import annotations

import unittest

from backend.app.services.tennis_math import (
    game_win_probability,
    game_win_probability_dp,
    match_win_from_set,
    set_win_probability_from_hold,
)


class TennisMathTests(unittest.TestCase):
    def test_game_probability_is_half_when_point_probability_half(self) -> None:
        self.assertAlmostEqual(game_win_probability(0.5), 0.5, places=7)

    def test_game_probability_monotonic(self) -> None:
        self.assertLess(game_win_probability(0.55), game_win_probability(0.65))

    def test_best_of_five_rewards_set_edge_more_than_best_of_three(self) -> None:
        self.assertGreater(match_win_from_set(0.58, 5), match_win_from_set(0.58, 3))

    def test_closed_form_hold_matches_recursive_dp(self) -> None:
        for step in range(5, 96, 5):
            p = step / 100
            self.assertAlmostEqual(game_win_probability(p), game_win_probability_dp(p), places=10)

    def test_set_probability_is_symmetric_at_equal_hold(self) -> None:
        self.assertAlmostEqual(set_win_probability_from_hold(0.72, 0.72), 0.5, places=7)

    def test_set_probability_increases_with_hold_edge(self) -> None:
        self.assertGreater(set_win_probability_from_hold(0.78, 0.70), set_win_probability_from_hold(0.74, 0.70))


if __name__ == "__main__":
    unittest.main()
