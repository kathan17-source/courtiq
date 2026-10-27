from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import evaluation_provenance as provenance
from backend.app.services.model_store import load_model_from_path
from scripts.verify_atp_evaluation import independent_metrics

ATP = Path("output/models/courtiq_model_atp.json")


def payload():
    return json.loads(ATP.read_text())


def test_retired_numbers_cannot_be_reintroduced_by_status_flag(tmp_path):
    data = payload()
    data["metrics"] = data["legacy_contaminated_metrics_retired"]["previous_metrics"]
    data["evaluation_status"] = "independently_reproduced"
    file = tmp_path / "model.json"
    file.write_text(json.dumps(data))
    loaded = load_model_from_path(file)
    assert loaded.evaluation_status == "unverified"
    assert all(value is None for value in loaded.metrics.values())
    assert loaded.coefficients == data["model"]["coefficients"]


def proof(data, tmp_path, monkeypatch):
    """Synthetic unit-test provenance, never a production evaluation claim."""
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    data["metrics"] = data["legacy_contaminated_metrics_retired"]["previous_metrics"]
    data["evaluation_status"] = "independently_reproduced"
    report = {
        "status": "reproduced",
        "model_version": data["model_version"],
        "model_sha256": provenance.model_hash(data["model"]),
        "temporal_policy_version": data["temporal_policy_version"],
        "metrics": data["metrics"],
        "test_sample_size": 4,
        "source_files_sha256": {"synthetic-fixture": "0" * 64},
        "verification": {
            "regenerated_from_raw": True,
            "refitted_parameters_match": True,
            "cached_rows_match": True,
            "independent_pairwise_auc_and_metric_formulas": True,
        },
    }
    folder = tmp_path / "docs/evaluation"
    folder.mkdir(parents=True)
    path = folder / "fixture.json"
    path.write_text(json.dumps(report))
    data["evaluation_provenance"] = {
        "report": "docs/evaluation/fixture.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return report, path


def test_equal_retired_values_are_not_proof_of_contamination(tmp_path, monkeypatch):
    data = payload()
    proof(data, tmp_path, monkeypatch)
    status, metrics = provenance.evaluation_presentation(data)
    assert status == "independently_reproduced"
    assert metrics == data["legacy_contaminated_metrics_retired"]["previous_metrics"]


@pytest.mark.parametrize("change", ["model", "version", "policy", "metric", "report", "refit", "source"])
def test_independent_evidence_is_bound_to_the_exact_model_and_evaluation(tmp_path, monkeypatch, change):
    data = payload()
    report, path = proof(data, tmp_path, monkeypatch)
    if change == "model":
        data["model"]["intercept"] += 0.01
    elif change == "version":
        data["model_version"] = "different-model"
    elif change == "policy":
        data["temporal_policy_version"] = "different-policy"
    elif change == "metric":
        data["metrics"] = {**data["metrics"], "accuracy": 0.99}
    elif change == "report":
        path.write_text("{}")
    else:
        if change == "refit":
            report["verification"]["refitted_parameters_match"] = False
        else:
            report["source_files_sha256"] = {}
        path.write_text(json.dumps(report))
        data["evaluation_provenance"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert provenance.evaluation_presentation(data)[0] == "unverified"


def test_api_and_inference_distinguish_availability_from_evaluation():
    with TestClient(app) as client:
        metrics = client.get("/api/model/metrics").json()
        assert metrics["status"] == "unverified"
        assert all(metrics[key] is None for key in provenance.METRIC_NAMES)
        response = client.post(
            "/api/predict",
            json={"player1": "Carlos Alcaraz", "player2": "Jannik Sinner", "event": "Wimbledon", "tour": "atp"},
        )
        assert response.status_code == 200
        assert response.json()["data_status"] == "real_artifact_loaded"
        assert response.json()["diagnostics"]["evaluation_status"] == "unverified"
        assert response.json()["diagnostics"]["warnings"]
        assert client.get("/api/model/version").json()["evaluation_status"] == "unverified"
        assert client.get("/api/model/metrics?tour=wta").json()["status"] == "artifact_reported"


def test_independent_metric_formulas_handle_ties_and_bin_boundaries():
    import numpy as np

    result = independent_metrics(np.array([0, 1, 0, 1]), np.array([0.5, 0.5, 0.1, 0.9]))
    assert result["accuracy"] == 0.75
    assert result["roc_auc"] == 0.875
    assert result["brier_score"] == pytest.approx(0.13)
