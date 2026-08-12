from __future__ import annotations

import importlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROWS_PATH = ROOT / "output/backtests/courtiq_feature_rows_atp.csv"
MODEL_PATH = ROOT / "output/models/courtiq_model_atp.json"
PRE_PROMOTION_BACKUP_PATH = ROOT / "output/models/courtiq_pre_promotion_backup.json"
REPORT_PATH = ROOT / "output/backtests/predictor_improvement_report.json"

CURRENT_PRODUCTION_BENCHMARK = {
    "accuracy": 0.6550,
    "roc_auc": 0.7132,
    "log_loss": 0.6185,
    "brier_score": 0.2154,
    "ece": 0.0271,
}

FEATURE_FAMILIES = {
    "elo": ["overall_elo_diff", "surface_elo_diff"],
    "surface": ["surface_elo_diff", "surface_form_diff", "surface_h2h_prior_diff"],
    "recent_form": ["form_5_diff", "form_10_diff", "form_20_diff", "surface_form_diff"],
    "serve_return": [
        "ace_rate_diff",
        "df_rate_diff",
        "first_in_diff",
        "first_won_diff",
        "second_won_diff",
        "bp_save_diff",
        "bp_convert_diff",
        "return_point_won_diff",
        "serve_point_won_diff",
        "stat_sample_diff",
    ],
    "fatigue_rest": ["days_rest_diff", "workload_14d_diff"],
    "h2h": ["h2h_prior_diff", "surface_h2h_prior_diff"],
    "ranking": ["ranking_diff", "ranking_points_diff"],
}


@dataclass
class LogisticModel:
    features: list[str]
    weights: np.ndarray
    intercept: float

    def logits(self, frame: pd.DataFrame) -> np.ndarray:
        return self.intercept + frame[self.features].to_numpy(dtype=float) @ self.weights

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return sigmoid(self.logits(frame))


def sigmoid(values: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35, 35)))


def logit(probs: np.ndarray) -> np.ndarray:
    p = np.clip(probs.astype(float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def fit_logistic(frame: pd.DataFrame, features: list[str], epochs: int = 260, lr: float = 0.08, l2: float = 0.002) -> LogisticModel:
    x = frame[features].to_numpy(dtype=float)
    y = frame["label"].to_numpy(dtype=float)
    weights = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        z = intercept + x @ weights
        pred = sigmoid(z)
        error = pred - y
        intercept -= lr * float(error.mean())
        weights -= lr * ((x.T @ error) / n + l2 * weights)
    return LogisticModel(features=features, weights=weights, intercept=float(intercept))


def fit_platt(raw_logits: np.ndarray, y: np.ndarray, epochs: int = 900, lr: float = 0.03) -> dict[str, float | str]:
    slope = 1.0
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        pred = sigmoid(slope * raw_logits + intercept)
        error = pred - y
        slope -= lr * (float((error * raw_logits).sum()) / n + 0.002 * (slope - 1.0))
        intercept -= lr * float(error.mean())
    return {"method": "platt", "slope": round(float(slope), 6), "intercept": round(float(intercept), 6)}


def apply_calibration_from_logits(raw_logits: np.ndarray, calibration: dict[str, Any]) -> np.ndarray:
    return sigmoid(float(calibration.get("slope", 1.0)) * raw_logits + float(calibration.get("intercept", 0.0)))


def metrics(probs: np.ndarray, y: np.ndarray) -> dict[str, float]:
    p = np.clip(probs.astype(float), 1e-6, 1 - 1e-6)
    labels = y.astype(int)
    return {
        "accuracy": round(float(((p >= 0.5) == labels).mean()), 4),
        "roc_auc": round(float(roc_auc(p, labels)), 4),
        "log_loss": round(float(-(labels * np.log(p) + (1 - labels) * np.log(1 - p)).mean()), 4),
        "brier_score": round(float(((p - labels) ** 2).mean()), 4),
        "ece": round(float(expected_calibration_error(p, labels)), 4),
    }


def roc_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return 0.5
    order = np.argsort(probs)
    sorted_probs = probs[order]
    sorted_labels = labels[order]
    ranks = np.empty(len(probs), dtype=float)
    i = 0
    while i < len(probs):
        j = i + 1
        while j < len(probs) and sorted_probs[j] == sorted_probs[i]:
            j += 1
        ranks[i:j] = (i + 1 + j) / 2.0
        i = j
    rank_sum = float(ranks[sorted_labels == 1].sum())
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, buckets: int = 10) -> float:
    error = 0.0
    for bucket in range(buckets):
        low, high = bucket / buckets, (bucket + 1) / buckets
        mask = (probs >= low) & (probs < high if bucket < buckets - 1 else probs <= high)
        if mask.any():
            error += float(mask.mean()) * abs(float(probs[mask].mean()) - float(labels[mask].mean()))
    return error


def load_frame() -> pd.DataFrame:
    frame = pd.read_csv(FEATURE_ROWS_PATH)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["year"] = frame["date"].dt.year
    return frame


def load_artifact() -> dict[str, Any]:
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def artifact_raw_logits(artifact: dict[str, Any], rows: pd.DataFrame) -> np.ndarray:
    model = artifact["model"]
    if model.get("type") == "time_safe_stacked_ensemble":
        ensemble = model["ensemble"]
        full = ensemble["full_logistic"]
        full_logits = np.full(len(rows), float(full.get("intercept", 0.0)))
        for coefficient, feature in zip(full["coefficients"], full["feature_names"], strict=False):
            full_logits += float(coefficient) * rows[str(feature)].to_numpy(dtype=float)
        meta = pd.DataFrame(index=rows.index)
        meta["full_logistic"] = full_logits
        meta["overall_elo"] = logit(sigmoid(2.2 * rows["overall_elo_diff"].to_numpy(dtype=float)))
        meta["surface_elo"] = logit(sigmoid(2.2 * rows["surface_elo_diff"].to_numpy(dtype=float)))
        meta["ranking"] = logit(sigmoid(2.2 * rows["ranking_diff"].to_numpy(dtype=float)))
        meta["serve_return"] = logit(sigmoid(9.0 * rows["serve_point_won_diff"].to_numpy(dtype=float)))
        stacker = ensemble["stacker"]
        logits = np.full(len(rows), float(stacker.get("intercept", 0.0)))
        for coefficient, feature in zip(stacker["coefficients"], stacker["feature_names"], strict=False):
            logits += float(coefficient) * meta[str(feature)].to_numpy(dtype=float)
        return logits

    logits = np.full(len(rows), float(model.get("intercept", 0.0)))
    for coefficient, feature in zip(model["coefficients"], model["feature_names"], strict=False):
        logits += float(coefficient) * rows[str(feature)].to_numpy(dtype=float)
    return logits


def artifact_probs(artifact: dict[str, Any], rows: pd.DataFrame) -> np.ndarray:
    model = artifact["model"]
    logits = artifact_raw_logits(artifact, rows)
    calibration = model.get("calibration") or {}
    return apply_calibration_from_logits(logits, calibration)


def base_features() -> list[str]:
    return [str(item) for item in load_artifact()["model"]["feature_names"]]


def candidate_feature_sets(features: list[str]) -> dict[str, list[str]]:
    out = {"full_current_features": features}
    for family, removed in FEATURE_FAMILIES.items():
        remove = set(removed)
        out[f"remove_{family}"] = [feature for feature in features if feature not in remove]
    for feature in features:
        out[f"remove_feature::{feature}"] = [item for item in features if item != feature]
    out["compact_no_recent_no_h2h"] = [
        feature for feature in features if feature not in set(FEATURE_FAMILIES["recent_form"] + FEATURE_FAMILIES["h2h"])
    ]
    out["compact_no_recent_no_serve_return"] = [
        feature for feature in features if feature not in set(FEATURE_FAMILIES["recent_form"] + FEATURE_FAMILIES["serve_return"])
    ]
    out["rating_rank_rest_only"] = [
        feature for feature in features
        if feature in set(FEATURE_FAMILIES["elo"] + FEATURE_FAMILIES["ranking"] + FEATURE_FAMILIES["fatigue_rest"] + ["matches_diff", "best_of_5"])
    ]
    return out


def walk_forward_feature_eval(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    fold_rows = []
    all_probs = []
    all_labels = []
    for validation_year in range(2018, 2024):
        calibration_year = validation_year - 1
        train = frame[frame["year"] < calibration_year]
        calibration = frame[frame["year"] == calibration_year]
        validation = frame[frame["year"] == validation_year]
        if len(train) < 3000 or calibration.empty or validation.empty:
            continue
        model = fit_logistic(train, features)
        calibration_logits = model.logits(calibration)
        calibrator = fit_platt(calibration_logits, calibration["label"].to_numpy(dtype=int))
        probs = apply_calibration_from_logits(model.logits(validation), calibrator)
        labels = validation["label"].to_numpy(dtype=int)
        fold_rows.append({"year": validation_year, "rows": int(len(validation)), **metrics(probs, labels)})
        all_probs.append(probs)
        all_labels.append(labels)

    if not fold_rows:
        return {"status": "no_folds"}
    pooled_probs = np.concatenate(all_probs)
    pooled_labels = np.concatenate(all_labels)
    return {
        "status": "evaluated",
        "folds": fold_rows,
        "mean_log_loss": round(float(np.mean([row["log_loss"] for row in fold_rows])), 4),
        "mean_brier_score": round(float(np.mean([row["brier_score"] for row in fold_rows])), 4),
        "mean_accuracy": round(float(np.mean([row["accuracy"] for row in fold_rows])), 4),
        "pooled_metrics": metrics(pooled_probs, pooled_labels),
    }


def train_calibrate_test(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    train = frame[frame["year"] <= 2023]
    calibration = frame[frame["year"] == 2024]
    test = frame[frame["year"] == 2025]
    start = time.perf_counter()
    model = fit_logistic(train, features, epochs=360)
    calibrator = fit_platt(model.logits(calibration), calibration["label"].to_numpy(dtype=int))
    probs = apply_calibration_from_logits(model.logits(test), calibrator)
    return {
        "features": features,
        "feature_count": len(features),
        "calibration": calibrator,
        "metrics": metrics(probs, test["label"].to_numpy(dtype=int)),
        "season_breakdown": season_breakdown(frame[frame["year"].between(2020, 2025)], model, calibrator),
        "surface_breakdown": subgroup(frame=test, probs=probs, column="surface"),
        "runtime_seconds": round(time.perf_counter() - start, 3),
        "model": {
            "feature_names": features,
            "coefficients": [float(value) for value in model.weights],
            "intercept": float(model.intercept),
        },
    }


def season_breakdown(rows: pd.DataFrame, model: LogisticModel, calibrator: dict[str, Any]) -> dict[str, dict[str, float | int]]:
    out = {}
    for year, group in rows.groupby("year", sort=True):
        probs = apply_calibration_from_logits(model.logits(group), calibrator)
        out[str(year)] = {"rows": int(len(group)), **metrics(probs, group["label"].to_numpy(dtype=int))}
    return out


def subgroup(frame: pd.DataFrame, probs: np.ndarray, column: str) -> dict[str, dict[str, float | int]]:
    out = {}
    labels = frame["label"].to_numpy(dtype=int)
    positions = pd.Series(range(len(frame)), index=frame.index)
    for value, group in frame.groupby(column, sort=True):
        idx = positions.loc[group.index].to_numpy()
        out[str(value)] = {"rows": int(len(group)), **metrics(probs[idx], labels[idx])}
    return out


def optional_booster_status() -> dict[str, str]:
    status = {}
    for package in ("lightgbm", "xgboost", "catboost"):
        try:
            importlib.import_module(package)
            status[package] = "available"
        except Exception as exc:
            status[package] = f"unavailable_in_runtime: {type(exc).__name__}"
    return status


def promote_if_better(artifact: dict[str, Any], candidate: dict[str, Any], candidate_name: str) -> bool:
    metric = candidate["metrics"]
    better = (
        float(metric["log_loss"]) < CURRENT_PRODUCTION_BENCHMARK["log_loss"] - 0.0005
        and float(metric["brier_score"]) < CURRENT_PRODUCTION_BENCHMARK["brier_score"] - 0.0005
    )
    if not better:
        return False
    if not PRE_PROMOTION_BACKUP_PATH.exists():
        PRE_PROMOTION_BACKUP_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    promoted = dict(artifact)
    base_version = str(artifact.get("model_version", "courtiq-real")).split("-stacked")[0]
    promoted["model_version"] = f"{base_version}-{candidate_name}"
    promoted["model"] = {
        "type": "logistic_regression",
        "feature_names": candidate["model"]["feature_names"],
        "coefficients": candidate["model"]["coefficients"],
        "intercept": candidate["model"]["intercept"],
        "calibration": candidate["calibration"],
    }
    promoted["metrics"] = metric
    promoted["promotion_source"] = {
        "report": str(REPORT_PATH),
        "selection_rule": "candidate selected by 2018-2023 walk-forward validation; final calibration 2024; final comparison 2025",
        "pre_promotion_backup": str(PRE_PROMOTION_BACKUP_PATH),
    }
    MODEL_PATH.write_text(json.dumps(promoted, indent=2, sort_keys=True), encoding="utf-8")
    return True


def main() -> int:
    started = time.perf_counter()
    frame = load_frame()
    features = base_features()
    artifact = load_artifact()
    test = frame[frame["year"] == 2025]
    current_probs = artifact_probs(artifact, test)
    current_eval = {
        "artifact_type": artifact["model"].get("type", "logistic_regression"),
        "metrics": metrics(current_probs, test["label"].to_numpy(dtype=int)),
        "surface_breakdown": subgroup(test, current_probs, "surface"),
    }

    candidates: dict[str, Any] = {}
    for name, feature_set in candidate_feature_sets(features).items():
        candidates[name] = {
            "feature_count": len(feature_set),
            "removed_features": [feature for feature in features if feature not in feature_set],
            "walk_forward_2018_2023": walk_forward_feature_eval(frame, feature_set),
        }

    selectable = [
        (name, payload["walk_forward_2018_2023"])
        for name, payload in candidates.items()
        if payload["walk_forward_2018_2023"].get("status") == "evaluated"
    ]
    selected_name, selected_walk = min(selectable, key=lambda item: (
        float(item[1]["mean_log_loss"]),
        float(item[1]["mean_brier_score"]),
        -float(item[1]["mean_accuracy"]),
    ))
    final_candidate = train_calibrate_test(frame, candidate_feature_sets(features)[selected_name])
    production_changed = promote_if_better(artifact, final_candidate, selected_name.replace("::", "-").replace("_", "-"))

    comparison = [
        {"model": "Existing production", **current_eval["metrics"]},
        {"model": f"Selected logistic ({selected_name})", **final_candidate["metrics"]},
    ]
    report = {
        "status": "ok",
        "important_note": "2025 metrics had been inspected in prior work. This run uses 2018-2023 walk-forward validation for feature/model selection, then performs the final 2025 comparison after freezing the selected candidate.",
        "data_contract": {
            "rows": int(len(frame)),
            "date_min": frame["date"].min().date().isoformat(),
            "date_max": frame["date"].max().date().isoformat(),
            "selection_folds": "train < calibration year, calibration = year-1, validation = 2018..2023",
            "final_train": "year <= 2023",
            "final_calibration": "year == 2024",
            "final_test": "year == 2025",
        },
        "optional_boosters": {
            "status": optional_booster_status(),
            "result": "LightGBM/XGBoost/CatBoost could not be genuinely evaluated because packages are unavailable and network package installation is blocked in this runtime.",
        },
        "current_production": current_eval,
        "candidate_search": candidates,
        "selected_by_walk_forward": {
            "name": selected_name,
            "walk_forward": selected_walk,
        },
        "final_2025_candidate": final_candidate,
        "comparison_table": comparison,
        "production_decision": {
            "production_model_changed": production_changed,
            "winning_model": f"Selected logistic ({selected_name})" if production_changed else "Existing production",
            "improvement_vs_existing": {
                "accuracy": round(final_candidate["metrics"]["accuracy"] - current_eval["metrics"]["accuracy"], 4),
                "roc_auc": round(final_candidate["metrics"]["roc_auc"] - current_eval["metrics"]["roc_auc"], 4),
                "log_loss": round(current_eval["metrics"]["log_loss"] - final_candidate["metrics"]["log_loss"], 4),
                "brier_score": round(current_eval["metrics"]["brier_score"] - final_candidate["metrics"]["brier_score"], 4),
                "ece": round(current_eval["metrics"]["ece"] - final_candidate["metrics"]["ece"], 4),
            },
            "artifact_path": str(MODEL_PATH),
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT_PATH),
        "selected": selected_name,
        "comparison_table": comparison,
        "production_decision": report["production_decision"],
        "optional_boosters": report["optional_boosters"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
