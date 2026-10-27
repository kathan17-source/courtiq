from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "outputs/tennis-ai-app/app.js"
INDEX_HTML = ROOT / "outputs/tennis-ai-app/index.html"


def test_invalid_leaky_baseline_is_retired_not_deployed() -> None:
    assert not (ROOT / "output/models/courtiq_logistic_baseline.json").exists()
    note = (ROOT / "output/research/retired_models/legacy_leaky_baseline.md").read_text(encoding="utf-8")
    assert "RETIRED / INVALID" in note
    assert "temporal leakage" in note


def test_production_model_directory_contains_only_authoritative_artifacts() -> None:
    names = sorted(path.name for path in (ROOT / "output/models").glob("*.json"))
    assert names == ["courtiq_model_atp.json", "courtiq_model_wta.json"]


def test_frontend_metrics_are_api_owned_and_unverified_atp_values_are_not_hardcoded() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "/api/model/metrics?tour=" in source
    assert "Evaluation unverified or unavailable" in source
    for value in ("65.50%", "0.7132", "0.6185", "0.2154", "0.0271"):
        assert value not in source
    assert "chart-observed" not in source  # No fabricated observed calibration curve.
    artifact = json.loads((ROOT / "output/models/courtiq_model_atp.json").read_text())
    assert artifact["evaluation_status"] == "unverified"
    assert all(value is None for value in artifact["metrics"].values())


def test_tournament_ui_uses_production_simulation_endpoint() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    assert "/api/simulate/tournament" in source
    assert "MODEL-SIMULATED CHAMPION PROBABILITY" in source
    assert "Relative field rating" not in source


def test_public_shell_has_neutral_identity_and_no_favicon_social_preview() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "Device profile" in source
    assert "Local profile · kp" not in source
    assert 'property="og:image"' not in source
