"""Read-only reproduction of the exact ATP artifact; never trains/promotes a replacement."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import final_modeling_pass as training


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def independent_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    """Independent formulas, including pairwise AUC rather than the training rank routine."""
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    y = labels.astype(int)
    positive, negative = p[y == 1], p[y == 0]
    auc = ((positive[:, None] > negative).sum() + 0.5 * (positive[:, None] == negative).sum()) / (
        len(positive) * len(negative)
    )
    bins = np.minimum((p * 10).astype(int), 9)
    calibration_error = sum(abs(float((p[bins == b] - y[bins == b]).sum())) for b in range(10)) / len(y)
    return {
        "accuracy": float(np.mean((p >= 0.5) == y)),
        "roc_auc": float(auc),
        "log_loss": float(np.mean(np.where(y == 1, -np.log(p), -np.log1p(-p)))),
        "brier_score": float(np.mean(np.square(p - y))),
        "ece": float(calibration_error),
    }


def run(data_dir: Path, artifact_path: Path, cached_rows: Path | None = None) -> dict:
    original = artifact_path.read_bytes()
    artifact = json.loads(original)
    training.DATA_DIR = data_dir
    matches = [m for m in training.load_matches() if m.tour == "atp"]
    frame, _, _ = training.build_feature_rows(matches, temporal_mode="round_safe")
    model = artifact["model"]
    features = model["feature_names"]
    frame[features] = frame[features].replace([np.inf, -np.inf], 0).fillna(0)
    cached_check = None
    if cached_rows:
        cached = pd.read_csv(cached_rows)
        same_metadata = (
            frame[["date", "player1", "player2", "label"]]
            .astype(str)
            .equals(cached[["date", "player1", "player2", "label"]].astype(str))
        )
        cached_check = bool(
            len(frame) == len(cached)
            and same_metadata
            and np.allclose(frame[features], cached[features], rtol=0, atol=1e-10)
        )
        for year in sorted(frame.year.unique()):
            mask = frame.year == year
            delta = np.abs(frame.loc[mask, features].to_numpy() - cached.loc[mask, features].to_numpy())
            print(
                f"Cached comparison {year}: max_delta={delta.max()}, differing_cells={(delta > 1e-10).sum()}",
                flush=True,
            )
    # Refit only to verify the existing serialized parameters; no output artifact is written.
    fitted = training.final_train_eval(frame, features)["model"]
    differences = {
        key: float(np.max(np.abs(np.asarray(fitted[key]) - np.asarray(model[key]))))
        for key in ("coefficients", "center", "scale", "intercept")
    }
    parameter_match = max(differences.values()) <= 1e-10 and fitted["calibration"] == model["calibration"]
    test = frame[frame.year == 2025]
    x = test[features].to_numpy(dtype=float)
    z = np.nan_to_num((x - np.asarray(model["center"])) / np.asarray(model["scale"]))
    logits = z @ np.asarray(model["coefficients"]) + model["intercept"]
    calibrated = logits * model["calibration"]["slope"] + model["calibration"]["intercept"]
    p = 1 / (1 + np.exp(-np.clip(calibrated, -40, 40)))
    result = independent_metrics(test.label.to_numpy(), p)
    rounded = {k: round(v, 4) for k, v in result.items()}
    reported_metrics = artifact.get("unverified_evaluation", {}).get("reported_metrics") or artifact["metrics"]
    metric_match = rounded == reported_metrics
    if artifact_path.read_bytes() != original:
        raise ValueError("Artifact changed during the read-only audit")
    return {
        "status": "reproduced" if parameter_match and metric_match and cached_check is not False else "unverified",
        "model_version": artifact["model_version"],
        "model_sha256": canonical_hash(model),
        "temporal_policy_version": artifact["temporal_policy_version"],
        "metrics": rounded,
        "unrounded_metrics": result,
        "test_sample_size": len(test),
        "test_dates": [str(test.date.min()), str(test.date.max())],
        "splits": {
            name: {
                "rows": len(part),
                "first_tournament_start": str(part.date.min()),
                "last_tournament_start": str(part.date.max()),
            }
            for name, part in [
                ("training", frame[frame.year <= 2023]),
                ("calibration", frame[frame.year == 2024]),
                ("evaluation", test),
            ]
        },
        "reported_metrics": reported_metrics,
        "raw_matches": len(matches),
        "source_files_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data_dir.glob("atp*.csv"))
        },
        "source": "Locally supplied Jeff Sackmann ATP CSVs; raw rows are not redistributed",
        "verification": {
            "regenerated_from_raw": True,
            "cached_rows_match": cached_check,
            "refitted_parameters_match": parameter_match,
            "maximum_parameter_difference": max(differences.values()),
            "parameter_differences": differences,
            "calibration_matches": fitted["calibration"] == model["calibration"],
            "rounded_metrics_match_reported": metric_match,
            "independent_pairwise_auc_and_metric_formulas": True,
        },
        "code_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in [
                "scripts/verify_atp_evaluation.py",
                "scripts/final_modeling_pass.py",
                "backend/app/services/tennis_math.py",
            ]
        },
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
        "audited_at": datetime.now(UTC).isoformat(),
        "limitations": [
            "Retrospective tournament-start dates, not exact match timestamps or a new prospective holdout.",
            "Round-safe partial order: prior rounds may update later rounds; same-round results are batched.",
            "This reuses the original feature generator; independent metric formulas and parameter refit do not prove every source-data assumption.",
            "Legacy equality is not itself proof of contamination. TENSOR candidates are separate and not promoted.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--artifact", type=Path, default=ROOT / "output/models/courtiq_model_atp.json")
    parser.add_argument("--cached-rows", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit("Refusing to overwrite an evaluation report")
    report = run(args.data_dir, args.artifact, args.cached_rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in ["status", "model_version", "metrics", "test_sample_size", "splits", "verification"]
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
