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


def test_frontend_metrics_match_checked_in_artifacts() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    for tour in ("atp", "wta"):
        artifact = json.loads((ROOT / f"output/models/courtiq_model_{tour}.json").read_text(encoding="utf-8"))
        metrics = artifact["metrics"]
        assert artifact["model_version"] in source
        assert f"{metrics['accuracy'] * 100:.2f}%" in source
        assert f"{metrics['log_loss']:.4f}" in source
        assert f"{metrics['brier_score']:.4f}" in source


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

