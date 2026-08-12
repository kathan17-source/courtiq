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

    def test_unknown_and_sensitive_paths_return_controlled_404(self) -> None:
        for path in ("/train/gear", "/.env", "/.git/config", "/Dockerfile", "/tests/test_api_validation.py", "/assets/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("/Users/", response.text)

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

    def test_request_models_reject_unknown_fields(self) -> None:
        payload = {
            "player1": "Carlos Alcaraz", "player2": "Jannik Sinner",
            "event": "Wimbledon", "tour": "atp", "unexpected": "ignored-before-hardening",
        }
        self.assertEqual(self.client.post("/api/predict", json=payload).status_code, 422)

    def test_security_headers_and_api_cache_policy(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertNotIn("unsafe-eval", response.headers["content-security-policy"])

    def test_unrelated_origin_get_and_preflight_are_not_allowed(self) -> None:
        get_response = self.client.get("/api/health", headers={"origin": "https://evil.example"})
        self.assertNotIn("access-control-allow-origin", get_response.headers)
        preflight = self.client.options(
            "/api/predict",
            headers={
                "origin": "https://evil.example",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        self.assertEqual(preflight.status_code, 400)
        self.assertNotIn("access-control-allow-origin", preflight.headers)

    def test_non_upload_body_limit_rejects_before_parsing(self) -> None:
        response = self.client.post(
            "/api/predict",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": str(2 * 1024 * 1024 + 1)},
        )
        self.assertEqual(response.status_code, 413)

    def test_request_id_is_sanitized(self) -> None:
        response = self.client.get("/api/health", headers={"x-request-id": "bad id/forged"})
        self.assertNotEqual(response.headers["x-request-id"], "bad id/forged")
        self.assertRegex(response.headers["x-request-id"], r"^[A-Za-z0-9_-]{1,64}$")

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
