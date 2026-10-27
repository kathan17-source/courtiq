"""Separate loaded inference parameters from independently supported evaluation claims."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
METRIC_NAMES = ("accuracy", "roc_auc", "log_loss", "brier_score", "ece")


def model_hash(model: dict) -> str:
    return hashlib.sha256(
        json.dumps(model, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def evaluation_presentation(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """A status flag or matching retired numbers alone can never validate a flagged artifact."""
    metrics = payload.get("metrics") or {}
    provenance = payload.get("evaluation_provenance") or {}
    try:
        report_path = (ROOT / provenance["report"]).resolve()
        if not report_path.is_relative_to(ROOT / "docs/evaluation"):
            raise ValueError("Evaluation report outside the reviewed evidence directory")
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes)
        checks = report.get("verification") or {}
        verified = (
            payload.get("evaluation_status") == "independently_reproduced"
            and hashlib.sha256(report_bytes).hexdigest() == provenance.get("sha256")
            and report.get("status") == "reproduced"
            and report.get("model_version") == payload.get("model_version")
            and report.get("model_sha256") == model_hash(payload["model"])
            and report.get("temporal_policy_version") == payload.get("temporal_policy_version")
            and report.get("metrics") == metrics
            and report.get("test_sample_size", 0) > 0
            and bool(report.get("source_files_sha256"))
            and checks.get("regenerated_from_raw") is True
            and checks.get("refitted_parameters_match") is True
            and checks.get("independent_pairwise_auc_and_metric_formulas") is True
            and checks.get("cached_rows_match") is not False
            and all(isinstance(metrics.get(k), (float, int)) for k in METRIC_NAMES)
        )
        if verified:
            return "independently_reproduced", metrics
    except (KeyError, ValueError, TypeError, OSError):
        pass
    if payload.get("legacy_contaminated_metrics_retired") or payload.get("evaluation_status") == "unverified":
        return "unverified", dict.fromkeys(METRIC_NAMES)
    # Other artifacts remain explicitly artifact-reported, not independently validated.
    return "artifact_reported", metrics
