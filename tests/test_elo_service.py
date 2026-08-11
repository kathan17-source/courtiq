from __future__ import annotations

import unittest

from backend.app.services.elo_service import PlayerRating, expected_score, update_pair


class EloServiceTests(unittest.TestCase):
    def test_equal_ratings_are_even(self) -> None:
        self.assertAlmostEqual(expected_score(1500, 1500), 0.5, places=7)

    def test_update_pair_increases_winner_rating(self) -> None:
        winner = PlayerRating()
        loser = PlayerRating()
        delta = update_pair(winner, loser, "hard")
        self.assertGreater(delta, 0)
        self.assertGreater(winner.overall, 1500)
        self.assertLess(loser.overall, 1500)


if __name__ == "__main__":
    unittest.main()
