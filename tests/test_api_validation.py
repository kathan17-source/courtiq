from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient
    from backend.app.main import app
except ModuleNotFoundError:  # local bundled runtime may not have FastAPI installed
    TestClient = None
    app = None


class ApiValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        if TestClient is None or app is None:
            self.skipTest("FastAPI is not installed in this runtime")
        self.client = TestClient(app)

    def test_api_health_exists(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_launcher_serves_frontend_root_and_assets(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("CourtIQ", response.text)
        self.assertNotIn('"detail":"Not Found"', response.text)

        script = self.client.get("/app.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("javascript", script.headers["content-type"])

        docs = self.client.get("/docs")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("text/html", docs.headers["content-type"])

    def test_frontend_deep_path_falls_back_to_app(self) -> None:
        response = self.client.get("/train/gear")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("CourtIQ", response.text)

    def test_predict_uses_loaded_atp_model_by_default(self) -> None:
        response = self.client.post(
            "/api/predict",
            json={"player1": "Carlos Alcaraz", "player2": "Jannik Sinner", "event": "Wimbledon", "tour": "atp"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data_status"], "real_artifact_loaded")

    def test_predict_rejects_cross_tour_selection(self) -> None:
        response = self.client.post(
            "/api/predict",
            json={
                "player1": "Carlos Alcaraz",
                "player2": "Coco Gauff",
                "event": "Wimbledon",
                "tour": "atp",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_predict_uses_loaded_wta_model_by_default(self) -> None:
        response = self.client.post(
            "/api/predict",
            json={"player1": "Coco Gauff", "player2": "Iga Swiatek", "event": "Wimbledon", "tour": "wta"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data_status"], "real_artifact_loaded")

    def test_predict_rejects_invalid_best_of(self) -> None:
        response = self.client.post(
            "/api/predict",
            json={
                "player1": "Carlos Alcaraz",
                "player2": "Jannik Sinner",
                "event": "Wimbledon",
                "tour": "atp",
                "best_of": 4,
                "allow_demo": True,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_unknown_event_requires_explicit_surface(self) -> None:
        payload = {"player1": "Carlos Alcaraz", "player2": "Jannik Sinner", "event": "Unknown Invitational", "tour": "atp"}
        self.assertEqual(self.client.post("/api/predict", json=payload).status_code, 400)
        payload["surface"] = "hard"
        self.assertEqual(self.client.post("/api/predict", json=payload).status_code, 200)

    def test_tournament_simulation_schema_bounds(self) -> None:
        valid = {"tour": "atp", "event": "Wimbledon", "draw_size": 2, "players": ["Carlos Alcaraz", "Jannik Sinner"], "simulations": 5, "seed": 7}
        response = self.client.post("/api/simulate/tournament", json=valid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["seed"], 7)
        for key, value in {
            "too_many": {**valid, "simulations": 10001},
            "bad_tour": {**valid, "tour": "mixed"},
            "duplicate": {**valid, "players": ["Carlos Alcaraz", "carlos alcaraz"]},
            "mismatch": {**valid, "draw_size": 4},
            "oversized": {**valid, "draw_size": 256},
        }.items():
            with self.subTest(key=key):
                self.assertEqual(self.client.post("/api/simulate/tournament", json=value).status_code, 422)

    def test_prediction_exposes_freshness(self) -> None:
        response = self.client.post("/api/predict", json={"player1": "Carlos Alcaraz", "player2": "Jannik Sinner", "event": "Wimbledon", "tour": "atp"})
        diagnostics = response.json()["diagnostics"]
        self.assertTrue(diagnostics["artifact_as_of"])
        self.assertIn("temporal_policy", diagnostics)


if __name__ == "__main__":
    unittest.main()
