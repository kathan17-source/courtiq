from __future__ import annotations

import unittest

try:
    from backend.app.schemas.prediction import PredictionRequest
    from backend.app.services.model_store import (
        ModelUnavailableError,
        clear_model_cache,
        get_player_record,
        load_tour_model,
    )
    from backend.app.services.prediction_service import predict_match
except ModuleNotFoundError:
    PredictionRequest = None
    ModelUnavailableError = None
    clear_model_cache = None
    get_player_record = None
    load_tour_model = None
    predict_match = None


class PredictionServiceTests(unittest.TestCase):
    def test_prediction_contract(self) -> None:
        if PredictionRequest is None or predict_match is None:
            self.skipTest("Pydantic is not installed in this runtime")
        response = predict_match(
            PredictionRequest(
                player1="Carlos Alcaraz",
                player2="Jannik Sinner",
                event="Wimbledon",
                tour="atp",
                allow_demo=True,
            )
        )
        self.assertEqual(response.surface, "grass")
        self.assertGreaterEqual(response.player1_win_probability, 0.02)
        self.assertLessEqual(response.player1_win_probability, 0.98)
        self.assertIn(response.winner, {"Carlos Alcaraz", "Jannik Sinner"})

    def test_production_artifact_loads_for_real_atp_prediction(self) -> None:
        if PredictionRequest is None or predict_match is None or load_tour_model is None:
            self.skipTest("Backend dependencies are not installed in this runtime")
        clear_model_cache()
        model = load_tour_model("atp")
        self.assertGreater(model.matches_processed, 0)
        self.assertGreater(len(model.feature_names), 0)
        self.assertIn(
            model.model_type,
            {"logistic_regression", "calibrated_logistic_regression", "enhanced_logistic_regression", "time_safe_stacked_ensemble"},
        )

        response = predict_match(
            PredictionRequest(
                player1="Carlos Alcaraz",
                player2="Jannik Sinner",
                event="Wimbledon",
                tour="atp",
            )
        )
        self.assertEqual(response.data_status, "real_artifact_loaded")
        self.assertEqual(response.model_version, model.version)
        self.assertGreaterEqual(response.player1_win_probability, 0.01)
        self.assertLessEqual(response.player1_win_probability, 0.99)

    def test_wta_artifact_loads_and_predicts_separately(self) -> None:
        if PredictionRequest is None or predict_match is None or load_tour_model is None:
            self.skipTest("Backend dependencies are not installed in this runtime")
        clear_model_cache()
        model = load_tour_model("wta")
        self.assertGreater(model.matches_processed, 0)
        self.assertTrue(all(player.tour == "wta" for player in model.players.values()))

        response = predict_match(
            PredictionRequest(
                player1="Coco Gauff",
                player2="Iga Swiatek",
                event="Wimbledon",
                tour="wta",
            )
        )
        self.assertEqual(response.data_status, "real_artifact_loaded")
        self.assertEqual(response.model_version, model.version)
        self.assertIn(response.winner, {"Coco Gauff", "Iga Swiatek"})
        self.assertGreaterEqual(response.player1_win_probability, 0.01)
        self.assertLessEqual(response.player1_win_probability, 0.99)

    def test_cross_tour_player_lookup_is_blocked(self) -> None:
        if get_player_record is None or ModelUnavailableError is None:
            self.skipTest("Backend dependencies are not installed in this runtime")
        clear_model_cache()
        with self.assertRaises(ModelUnavailableError):
            get_player_record("Coco Gauff", "atp")


if __name__ == "__main__":
    unittest.main()
