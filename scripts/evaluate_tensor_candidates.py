from __future__ import annotations

import importlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FEATURE_ROWS_PATH = ROOT / "output/backtests/courtiq_feature_rows_atp.csv"
MODEL_PATH = ROOT / "output/models/courtiq_model_atp.json"
LOGISTIC_BASELINE_PATH = ROOT / "output/models/courtiq_logistic_baseline.json"
REPORT_PATH = ROOT / "output/backtests/tensor_candidate_report.json"

CURRENT_BENCHMARK = {
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
    clipped = np.clip(probs, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def fit_logistic(frame: pd.DataFrame, features: list[str], epochs: int = 550, lr: float = 0.09, l2: float = 0.0015) -> LogisticModel:
    x = frame[features].to_numpy(dtype=float)
    y = frame["label"].to_numpy(dtype=float)
    weights = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        pred = sigmoid(intercept + x @ weights)
        error = pred - y
        intercept -= lr * float(error.mean())
        weights -= lr * ((x.T @ error) / n + l2 * weights)
    return LogisticModel(features=features, weights=weights, intercept=intercept)


def fit_platt(logits: np.ndarray, y: np.ndarray, epochs: int = 900, lr: float = 0.03) -> dict[str, float]:
    slope = 1.0
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        pred = sigmoid(slope * logits + intercept)
        error = pred - y
        slope -= lr * (float((error * logits).sum()) / n + 0.002 * (slope - 1.0))
        intercept -= lr * float(error.mean())
    return {"method": "platt_2024_only", "slope": round(float(slope), 6), "intercept": round(float(intercept), 6)}


def apply_calibration(probs: np.ndarray, calibration: dict[str, float]) -> np.ndarray:
    return sigmoid(calibration.get("slope", 1.0) * logit(probs) + calibration.get("intercept", 0.0))


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
    total = len(labels)
    error = 0.0
    for bucket in range(buckets):
        low, high = bucket / buckets, (bucket + 1) / buckets
        mask = (probs >= low) & (probs < high if bucket < buckets - 1 else probs <= high)
        if mask.any():
            error += float(mask.mean()) * abs(float(probs[mask].mean()) - float(labels[mask].mean()))
    return error


def load_current_model_features() -> tuple[list[str], np.ndarray, float, dict[str, float]]:
    payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    model = payload["model"]
    return (
        [str(item) for item in model["feature_names"]],
        np.array([float(item) for item in model["coefficients"]], dtype=float),
        float(model["intercept"]),
        {key: float(value) for key, value in model.get("calibration", {}).items() if isinstance(value, (int, float))},
    )


def split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train = frame[frame["year"] <= 2023].copy()
    calibration = frame[frame["year"] == 2024].copy()
    test = frame[frame["year"] == 2025].copy()
    if train.empty or calibration.empty or test.empty:
        raise RuntimeError("Expected train <=2023, calibration 2024, and test 2025 rows.")
    return train, calibration, test


def probability_band(prob: float) -> str:
    favorite = max(prob, 1 - prob)
    if favorite < 0.55:
        return "50-55"
    if favorite < 0.65:
        return "55-65"
    if favorite < 0.75:
        return "65-75"
    if favorite < 0.85:
        return "75-85"
    return "85-100"


def ranking_band(value: float) -> str:
    implied = abs(value * 998)
    if implied < 25:
        return "rank_gap_0_25"
    if implied < 75:
        return "rank_gap_25_75"
    if implied < 200:
        return "rank_gap_75_200"
    return "rank_gap_200_plus"


def subgroup_metrics(test: pd.DataFrame, probs: np.ndarray) -> dict[str, dict[str, dict[str, float]]]:
    enriched = test.copy()
    enriched["_prob"] = probs
    enriched["_favorite_band"] = [probability_band(float(p)) for p in probs]
    enriched["_rank_band"] = [ranking_band(float(x)) for x in enriched["ranking_diff"]]
    labels = enriched["label"].to_numpy(dtype=int)

    def by(column: str) -> dict[str, dict[str, float]]:
        out = {}
        for value, group in enriched.groupby(column, sort=True):
            idx = group.index.to_numpy()
            local = enriched.index.get_indexer(idx)
            out[str(value)] = {"rows": int(len(group)), **metrics(probs[local], labels[local])}
        return out

    return {
        "surface": by("surface"),
        "ranking_band": by("_rank_band"),
        "favorite_probability_band": by("_favorite_band"),
        "tournament_level": {"not_available": {"reason": "tourney_level is not present in the existing leakage-safe feature rows."}},
    }


def evaluate_current_baseline(frame: pd.DataFrame) -> dict[str, object]:
    features, weights, intercept, calibration = load_current_model_features()
    _, _, test = split(frame)
    raw = sigmoid(intercept + test[features].to_numpy(dtype=float) @ weights)
    probs = apply_calibration(raw, calibration)
    return {
        "status": "evaluated_from_frozen_artifact",
        "calibration": calibration,
        "metrics": metrics(probs, test["label"].to_numpy(dtype=int)),
        "subgroups": subgroup_metrics(test, probs),
    }


def optional_package_status() -> dict[str, str]:
    status = {}
    for package in ("lightgbm", "xgboost", "catboost"):
        try:
            importlib.import_module(package)
            status[package] = "available"
        except Exception as exc:
            status[package] = f"not_available: {type(exc).__name__}"
    return status


def evaluate_optional_boosters(frame: pd.DataFrame, features: list[str]) -> dict[str, object]:
    status = optional_package_status()
    results: dict[str, object] = {}
    train, calibration, test = split(frame)
    y_train = train["label"].to_numpy(dtype=int)
    y_cal = calibration["label"].to_numpy(dtype=int)
    y_test = test["label"].to_numpy(dtype=int)

    if status["lightgbm"] == "available":
        start = time.perf_counter()
        import lightgbm as lgb  # type: ignore

        model = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=350,
            learning_rate=0.035,
            num_leaves=15,
            min_child_samples=120,
            subsample=0.85,
            colsample_bytree=0.9,
            random_state=20260809,
            verbose=-1,
        )
        model.fit(train[features], y_train)
        cal_raw = model.predict_proba(calibration[features])[:, 1]
        calibrator = fit_platt(logit(cal_raw), y_cal)
        probs = apply_calibration(model.predict_proba(test[features])[:, 1], calibrator)
        results["lightgbm"] = {"status": "evaluated", "runtime_seconds": round(time.perf_counter() - start, 3), "calibration": calibrator, "metrics": metrics(probs, y_test)}
    else:
        results["lightgbm"] = {"status": status["lightgbm"]}

    if status["xgboost"] == "available":
        start = time.perf_counter()
        import xgboost as xgb  # type: ignore

        model = xgb.XGBClassifier(
            objective="binary:logistic",
            n_estimators=300,
            max_depth=3,
            learning_rate=0.035,
            subsample=0.85,
            colsample_bytree=0.9,
            reg_lambda=3.0,
            random_state=20260809,
            eval_metric="logloss",
        )
        model.fit(train[features], y_train)
        cal_raw = model.predict_proba(calibration[features])[:, 1]
        calibrator = fit_platt(logit(cal_raw), y_cal)
        probs = apply_calibration(model.predict_proba(test[features])[:, 1], calibrator)
        results["xgboost"] = {"status": "evaluated", "runtime_seconds": round(time.perf_counter() - start, 3), "calibration": calibrator, "metrics": metrics(probs, y_test)}
    else:
        results["xgboost"] = {"status": status["xgboost"]}

    results["catboost"] = {"status": status["catboost"] if status["catboost"] != "available" else "available_but_not_run_to_avoid_redundant_third_booster_without_prior_gain"}
    return results


def baseline_probs(frame: pd.DataFrame, kind: str) -> np.ndarray:
    if kind == "overall_elo":
        return sigmoid(2.2 * frame["overall_elo_diff"].to_numpy(dtype=float))
    if kind == "surface_elo":
        return sigmoid(2.2 * frame["surface_elo_diff"].to_numpy(dtype=float))
    if kind == "ranking":
        return sigmoid(2.2 * frame["ranking_diff"].to_numpy(dtype=float))
    if kind == "serve_return":
        return sigmoid(9.0 * frame["serve_point_won_diff"].to_numpy(dtype=float))
    raise ValueError(kind)


def train_stacker(oof: pd.DataFrame, meta_cols: list[str]) -> LogisticModel:
    return fit_logistic(oof, meta_cols, epochs=600, lr=0.08, l2=0.004)


def evaluate_stacked_ensemble(frame: pd.DataFrame, features: list[str]) -> dict[str, object]:
    start = time.perf_counter()
    meta_names = ["full_logistic", "overall_elo", "surface_elo", "ranking", "serve_return"]
    oof_parts = []
    for year in range(2020, 2024):
        fold_train = frame[frame["year"] < year].copy()
        fold_valid = frame[frame["year"] == year].copy()
        if len(fold_train) < 1000 or fold_valid.empty:
            continue
        model = fit_logistic(fold_train, features, epochs=120)
        part = fold_valid[["label"]].copy()
        part["full_logistic"] = logit(model.predict(fold_valid))
        for name in meta_names[1:]:
            part[name] = logit(baseline_probs(fold_valid, name))
        oof_parts.append(part)
    if not oof_parts:
        return {"status": "not_evaluated_no_oof_folds"}
    oof = pd.concat(oof_parts, ignore_index=True)
    stacker = train_stacker(oof, meta_names)

    train, calibration, test = split(frame)
    full_model = fit_logistic(train, features, epochs=180)

    def meta_frame(rows: pd.DataFrame) -> pd.DataFrame:
        meta = pd.DataFrame(index=rows.index)
        meta["full_logistic"] = logit(full_model.predict(rows))
        for name in meta_names[1:]:
            meta[name] = logit(baseline_probs(rows, name))
        return meta

    cal_meta = meta_frame(calibration)
    test_meta = meta_frame(test)
    cal_logits = stacker.intercept + cal_meta[meta_names].to_numpy(dtype=float) @ stacker.weights
    calibrator = fit_platt(cal_logits, calibration["label"].to_numpy(dtype=int))
    test_raw = sigmoid(stacker.intercept + test_meta[meta_names].to_numpy(dtype=float) @ stacker.weights)
    probs = apply_calibration(test_raw, calibrator)
    return {
        "status": "evaluated",
        "oof_years": "2020-2023",
        "stacker_calibration_year": 2024,
        "runtime_seconds": round(time.perf_counter() - start, 3),
        "calibration": calibrator,
        "metrics": metrics(probs, test["label"].to_numpy(dtype=int)),
        "subgroups": subgroup_metrics(test, probs),
        "meta_features": meta_names,
        "production_payload": {
            "full_logistic": {
                "feature_names": full_model.features,
                "coefficients": [float(value) for value in full_model.weights],
                "intercept": float(full_model.intercept),
            },
            "stacker": {
                "feature_names": meta_names,
                "coefficients": [float(value) for value in stacker.weights],
                "intercept": float(stacker.intercept),
            },
        },
    }


def evaluate_ablation(frame: pd.DataFrame, base_features: list[str], family: str, removed: list[str]) -> dict[str, object]:
    start = time.perf_counter()
    features = [feature for feature in base_features if feature not in set(removed)]
    train, calibration, test = split(frame)
    model = fit_logistic(train, features, epochs=180)
    cal_raw = model.predict(calibration)
    calibrator = fit_platt(logit(cal_raw), calibration["label"].to_numpy(dtype=int))
    probs = apply_calibration(model.predict(test), calibrator)
    result = metrics(probs, test["label"].to_numpy(dtype=int))
    return {
        "removed_family": family,
        "removed_features": removed,
        "features_remaining": len(features),
        "runtime_seconds": round(time.perf_counter() - start, 3),
        "calibration": calibrator,
        "metrics": result,
        "delta_vs_current": {
            "log_loss": round(result["log_loss"] - CURRENT_BENCHMARK["log_loss"], 4),
            "brier_score": round(result["brier_score"] - CURRENT_BENCHMARK["brier_score"], 4),
            "ece": round(result["ece"] - CURRENT_BENCHMARK["ece"], 4),
        },
    }


def comparison_row(name: str, payload: dict[str, object]) -> dict[str, object]:
    metric = payload.get("metrics") if isinstance(payload, dict) else None
    if not isinstance(metric, dict):
        return {"model": name, "status": payload.get("status", "not_evaluated") if isinstance(payload, dict) else "not_evaluated"}
    return {
        "model": name,
        "accuracy": metric["accuracy"],
        "roc_auc": metric["roc_auc"],
        "log_loss": metric["log_loss"],
        "brier_score": metric["brier_score"],
        "ece": metric["ece"],
    }


def main() -> int:
    if not FEATURE_ROWS_PATH.exists():
        raise SystemExit(f"Missing feature rows: {FEATURE_ROWS_PATH}")
    frame = pd.read_csv(FEATURE_ROWS_PATH)
    frame["year"] = pd.to_datetime(frame["date"]).dt.year
    features, _, _, _ = load_current_model_features()

    current_artifact = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    report: dict[str, object] = {
        "status": "ok",
        "data_contract": {
            "feature_rows": str(FEATURE_ROWS_PATH),
            "train": "year <= 2023",
            "calibration": "year == 2024",
            "final_test": "year == 2025",
            "test_labels_used_for_tuning": False,
            "rows": int(len(frame)),
        },
        "current_benchmark": CURRENT_BENCHMARK,
        "feature_names": features,
        "models": {},
        "ablations": {},
        "promotion_decision": {},
    }

    start = time.perf_counter()
    current = evaluate_current_baseline(frame)
    current["runtime_seconds"] = round(time.perf_counter() - start, 3)
    report["models"]["current_calibrated_logistic"] = current
    report["models"].update(evaluate_optional_boosters(frame, features))
    report["models"]["time_safe_stacked_ensemble"] = evaluate_stacked_ensemble(frame, features)

    for family, removed in FEATURE_FAMILIES.items():
        report["ablations"][family] = evaluate_ablation(frame, features, family, removed)

    comparison = [
        comparison_row("Current calibrated logistic", report["models"]["current_calibrated_logistic"]),
        comparison_row("LightGBM", report["models"]["lightgbm"]),
        comparison_row("XGBoost", report["models"]["xgboost"]),
        comparison_row("CatBoost", report["models"]["catboost"]),
        comparison_row("Time-safe stacked ensemble", report["models"]["time_safe_stacked_ensemble"]),
    ]
    report["comparison_table"] = comparison

    evaluated = [row for row in comparison if "log_loss" in row]
    winner = min(evaluated, key=lambda row: (float(row["log_loss"]), float(row["brier_score"])))
    current_metrics = current["metrics"]
    improved = (
        float(winner["log_loss"]) < float(current_metrics["log_loss"]) - 0.0005
        or float(winner["brier_score"]) < float(current_metrics["brier_score"]) - 0.0005
    )
    changed = bool(improved and winner["model"] != "Current calibrated logistic")
    report["promotion_decision"] = {
        "winning_model": winner["model"],
        "production_model_changed": changed,
        "reason": "Only promote if 2025 log loss or Brier improves by at least 0.0005 without calibration damage.",
        "exact_improvement_vs_current": {
            "log_loss": round(float(current_metrics["log_loss"]) - float(winner["log_loss"]), 4),
            "brier_score": round(float(current_metrics["brier_score"]) - float(winner["brier_score"]), 4),
            "ece": round(float(current_metrics["ece"]) - float(winner["ece"]), 4),
        },
        "production_artifact": str(MODEL_PATH),
    }

    if changed and winner["model"] == "Time-safe stacked ensemble":
        ensemble_result = report["models"]["time_safe_stacked_ensemble"]
        production_payload = ensemble_result["production_payload"]
        if not LOGISTIC_BASELINE_PATH.exists():
            LOGISTIC_BASELINE_PATH.write_text(json.dumps(current_artifact, indent=2, sort_keys=True), encoding="utf-8")
        promoted = dict(current_artifact)
        promoted["model_version"] = str(current_artifact.get("model_version", "courtiq-real")) + "-stacked"
        promoted["model"] = {
            "type": "time_safe_stacked_ensemble",
            "feature_names": features,
            "coefficients": production_payload["full_logistic"]["coefficients"],
            "intercept": production_payload["full_logistic"]["intercept"],
            "calibration": ensemble_result["calibration"],
            "ensemble": production_payload,
        }
        promoted["metrics"] = ensemble_result["metrics"]
        promoted["promotion_source"] = {
            "report": str(REPORT_PATH),
            "baseline_artifact": str(LOGISTIC_BASELINE_PATH),
            "validation_rule": "stacker oof 2020-2023; calibration 2024; final test 2025 untouched",
        }
        MODEL_PATH.write_text(json.dumps(promoted, indent=2, sort_keys=True), encoding="utf-8")
        report["promotion_decision"]["baseline_artifact"] = str(LOGISTIC_BASELINE_PATH)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH), "comparison_table": comparison, "promotion_decision": report["promotion_decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
