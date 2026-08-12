from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.model_store import ModelUnavailableError, load_model_from_path

ATP = Path("output/models/courtiq_model_atp.json")


@pytest.mark.parametrize("mutation", ["coefficients", "metadata", "calibration", "tour"])
def test_malformed_artifacts_fail_loudly(tmp_path: Path, mutation: str) -> None:
    payload = json.loads(ATP.read_text())
    if mutation == "coefficients":
        payload["model"]["coefficients"] = payload["model"]["coefficients"][:-1]
    elif mutation == "metadata":
        payload.pop("training_cutoff", None)
    elif mutation == "calibration":
        payload["model"]["calibration"]["slope"] = -1
    else:
        payload["tour"] = "mixed"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ModelUnavailableError):
        load_model_from_path(path)
