from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.app.services.model_store import load_model_from_path, normalize_player_key
from scripts.train_match_model import RawMatch, load_matches, player_key, process_matches, split_rows_with_rules


class RealDataPipelineTests(unittest.TestCase):
    def test_loads_jeff_sackmann_style_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "atp_matches_2019.csv"
            path.write_text(
                "tourney_date,tourney_name,surface,winner_name,loser_name,best_of,winner_rank,loser_rank,w_ace,l_ace,w_svpt,l_svpt\n"
                "20190101,Brisbane,Hard,Roger Federer,Player Two,3,3,55,8,2,80,75\n",
                encoding="utf-8",
            )
            matches = load_matches(Path(tmp))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].winner, "Roger Federer")
        self.assertEqual(matches[0].surface, "hard")

    def test_loads_supplied_wta_wide_csv_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wta_dir = Path(tmp) / "wta"
            wta_dir.mkdir()
            path = wta_dir / "wta.csv"
            path.write_text(
                "Tournament,Date,Court,Surface,Round,Best of,Player_1,Player_2,Winner,Rank_1,Rank_2,Pts_1,Pts_2,Odd_1,Odd_2,Score\n"
                "Wimbledon,2025-07-01,Outdoor,Grass,1st Round,3,Coco Gauff,Iga Swiatek,Iga Swiatek,2,1,7890,8120,2.05,1.80,6-4 6-4\n",
                encoding="utf-8",
            )
            matches = load_matches(Path(tmp))
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].tour, "wta")
        self.assertEqual(matches[0].winner, "Iga Swiatek")
        self.assertEqual(matches[0].loser, "Coco Gauff")
        self.assertEqual(matches[0].surface, "grass")
        self.assertEqual(matches[0].winner_rank, 1.0)
        self.assertEqual(matches[0].loser_rank, 2.0)
        self.assertEqual(matches[0].winner_rank_points, 8120.0)
        self.assertEqual(matches[0].loser_rank_points, 7890.0)

    def test_features_are_snapshotted_before_match_update(self) -> None:
        matches = [
            RawMatch("atp", date(2020, 1, 1), "Test", "hard", 3, "Player A", "Player B"),
            RawMatch("atp", date(2020, 1, 2), "Test", "hard", 3, "Player A", "Player B"),
        ]
        rows, players = process_matches(matches)
        first = rows[0]
        second = rows[1]
        self.assertEqual(first["overall_elo_diff"], 0.0)
        self.assertNotEqual(second["overall_elo_diff"], 0.0)
        self.assertEqual(players[player_key("Player A", "atp")].matches, 2)

    def test_same_tournament_date_results_do_not_feed_each_other(self) -> None:
        early = RawMatch("wta", date(2025, 7, 1), "Same Day Open", "hard", 3, "Player A", "Player B")
        later = RawMatch("wta", date(2025, 7, 1), "Same Day Open", "hard", 3, "Player A", "Player C")
        changed_later = RawMatch("wta", date(2025, 7, 1), "Same Day Open", "hard", 3, "Player C", "Player A")
        rows_original, _ = process_matches([early, later])
        rows_changed, _ = process_matches([early, changed_later])
        original_early = next(row for row in rows_original if {row["player1"], row["player2"]} == {"Player A", "Player B"})
        changed_early = next(row for row in rows_changed if {row["player1"], row["player2"]} == {"Player A", "Player B"})
        self.assertEqual(original_early, changed_early)

    def test_future_row_does_not_change_prior_features(self) -> None:
        prefix = [
            RawMatch("atp", date(2020, 1, 1), "Test", "hard", 3, "Player A", "Player B"),
            RawMatch("atp", date(2020, 1, 2), "Test", "hard", 3, "Player B", "Player A"),
        ]
        future = RawMatch("atp", date(2030, 1, 1), "Future", "clay", 3, "Player A", "Player B")
        rows_without_future, _ = process_matches(prefix)
        rows_with_future, _ = process_matches([*prefix, future])
        for left, right in zip(rows_without_future, rows_with_future[: len(rows_without_future)], strict=True):
            self.assertEqual(left, right)

    def test_split_rules_use_modern_holdout_when_available(self) -> None:
        rows = [{"date": f"{year}-01-01", "label": year % 2} for year in (2022, 2023, 2024, 2025, 2025)]
        train, validation, test, rules = split_rows_with_rules(rows)
        self.assertEqual(len(train), 2)
        self.assertEqual(len(validation), 1)
        self.assertEqual(len(test), 2)
        self.assertEqual(rules["split_type"], "fixed_modern_holdout")

    def test_model_artifact_loads_player_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            path.write_text(
                """
                {
                  "model_version": "test-model",
                  "generated_at": "2026-01-01T00:00:00Z",
                  "tour": "atp",
                  "training_cutoff": "date <= 2023",
                  "temporal_policy_version": "round_safe_v1",
                  "matches_processed": 2,
                  "metrics": {"accuracy": 0.5},
                  "model": {"feature_names": ["overall_elo_diff"], "coefficients": [1.0], "intercept": 0.0},
                  "players": {
                    "atp::player a": {
                      "name": "Player A", "tour": "atp", "overall_elo": 1510,
                      "surface_elo": {"hard": 1512, "clay": 1500, "grass": 1500},
                      "form_5": 0.6, "form_10": 0.55, "form_20": 0.5,
                      "surface_form": {"hard": 0.6, "clay": 0.5, "grass": 0.5},
                      "last_date": "2020-01-02", "matches": 2
                    }
                  }
                }
                """,
                encoding="utf-8",
            )
            model = load_model_from_path(path)
        self.assertEqual(model.version, "test-model")
        self.assertIn(normalize_player_key("Player A", "atp"), model.players)


if __name__ == "__main__":
    unittest.main()
