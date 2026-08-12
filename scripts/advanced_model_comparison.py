from __future__ import annotations

import base64
import json
import math
import os
import pickle
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.final_modeling_pass import (
    DATA_DIR,
    MODEL_PATH,
    ROUND_ORDER,
    RUNTIME_COMPATIBLE_FEATURES,
    build_feature_rows,
    calibrated_probs,
    candidate_sets,
    fit_logistic,
    fit_platt,
    load_matches,
    metrics,
    promote_corrected_model,
    safe_logit,
    sigmoid,
)

REPORT_PATH = ROOT / "output/backtests/advanced_model_comparison_report.json"
ROWS_PATH = ROOT / "output/backtests/advanced_model_feature_rows.csv"
OOF_PATH = ROOT / "output/backtests/advanced_model_oof_predictions.csv"
CANDIDATE_ARTIFACT_PATH = ROOT / "output/models/courtiq_advanced_candidate.pkl"

VALID_PRODUCTION_BENCHMARK = {
    "accuracy": 0.655,
    "roc_auc": 0.7124,
    "log_loss": 0.6191,
    "brier_score": 0.2156,
    "ece": 0.0283,
}

META_COLUMNS = {
    "index",
    "date",
    "year",
    "tour",
    "tournament",
    "surface",
    "level",
    "round",
    "player1",
    "player2",
    "label",
}


@dataclass
class OpponentMemory:
    wins: float = 0.0
    count: float = 0.0
    residual_sum: float = 0.0
    residual_weight: float = 0.0
    surface_wins: dict[str, float] = field(default_factory=dict)
    surface_count: dict[str, float] = field(default_factory=dict)
    surface_residual_sum: dict[str, float] = field(default_factory=dict)
    surface_residual_weight: dict[str, float] = field(default_factory=dict)
    last_date: date | None = None

    def snapshot(self, current_date: date, surface: str) -> dict[str, float]:
        decay = 1.0
        if self.last_date is not None:
            decay = 2 ** (-max(0, (current_date - self.last_date).days) / 730.0)
        count = self.count * decay
        residual_weight = self.residual_weight * decay
        surface_count = self.surface_count.get(surface, 0.0) * decay
        surface_residual_weight = self.surface_residual_weight.get(surface, 0.0) * decay
        return {
            "count": count,
            "winrate": (self.wins * decay + 0.5 * 6.0) / (count + 6.0),
            "residual": (self.residual_sum * decay) / residual_weight if residual_weight > 0 else 0.0,
            "surface_count": surface_count,
            "surface_winrate": (self.surface_wins.get(surface, 0.0) * decay + 0.5 * 4.0) / (surface_count + 4.0),
            "surface_residual": (self.surface_residual_sum.get(surface, 0.0) * decay) / surface_residual_weight
            if surface_residual_weight > 0
            else 0.0,
        }

    def add(self, result: float, expected: float, match_date: date, surface: str) -> None:
        if self.last_date is not None:
            decay = 2 ** (-max(0, (match_date - self.last_date).days) / 730.0)
            self.wins *= decay
            self.count *= decay
            self.residual_sum *= decay
            self.residual_weight *= decay
            for store in (
                self.surface_wins,
                self.surface_count,
                self.surface_residual_sum,
                self.surface_residual_weight,
            ):
                for key in list(store):
                    store[key] *= decay
        residual = result - expected
        self.wins += result
        self.count += 1.0
        self.residual_sum += residual
        self.residual_weight += 1.0
        self.surface_wins[surface] = self.surface_wins.get(surface, 0.0) + result
        self.surface_count[surface] = self.surface_count.get(surface, 0.0) + 1.0
        self.surface_residual_sum[surface] = self.surface_residual_sum.get(surface, 0.0) + residual
        self.surface_residual_weight[surface] = self.surface_residual_weight.get(surface, 0.0) + 1.0
        self.last_date = match_date


def _row_date(value: Any) -> date:
    return pd.Timestamp(value).date()


def add_common_opponent_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in (
        "common_opponent_count",
        "common_opponent_winrate_A",
        "common_opponent_winrate_B",
        "common_opponent_difference",
        "common_opponent_adjusted_edge",
        "surface_common_opponent_count",
        "surface_common_opponent_adjusted_edge",
    ):
        out[column] = 0.0

    history: dict[str, dict[str, OpponentMemory]] = {}
    ordered = out.assign(
        _row_date=pd.to_datetime(out["date"]),
        _round_order=out["round"].map(lambda value: ROUND_ORDER.get(str(value), 0)),
    ).sort_values(["_row_date", "tour", "tournament", "_round_order", "index"])

    for _, batch in ordered.groupby(["tour", "_row_date", "tournament", "_round_order"], sort=False):
        pending: list[tuple[str, str, float, float, date, str]] = []
        for idx, row in batch.iterrows():
            p1 = str(row["player1"])
            p2 = str(row["player2"])
            current_date = _row_date(row["date"])
            surface = str(row["surface"])
            h1 = history.get(p1, {})
            h2 = history.get(p2, {})
            common = sorted(set(h1).intersection(h2))
            weighted_raw = []
            weighted_resid = []
            weighted_surface_resid = []
            raw_a = []
            raw_b = []
            surface_common = 0.0
            for opponent in common:
                s1 = h1[opponent].snapshot(current_date, surface)
                s2 = h2[opponent].snapshot(current_date, surface)
                pair_weight = min(2.0, math.sqrt(max(0.0, min(s1["count"], s2["count"]))))
                if pair_weight <= 0:
                    continue
                raw_a.append((s1["winrate"], pair_weight))
                raw_b.append((s2["winrate"], pair_weight))
                weighted_raw.append(((s1["winrate"] - s2["winrate"]), pair_weight))
                weighted_resid.append(((s1["residual"] - s2["residual"]), pair_weight))
                surface_weight = min(1.5, math.sqrt(max(0.0, min(s1["surface_count"], s2["surface_count"]))))
                if surface_weight > 0:
                    surface_common += 1.0
                    weighted_surface_resid.append(((s1["surface_residual"] - s2["surface_residual"]), surface_weight))

            total_weight = sum(weight for _, weight in weighted_resid)
            surface_weight_sum = sum(weight for _, weight in weighted_surface_resid)
            shrink = len(common) / (len(common) + 8.0) if common else 0.0
            surface_shrink = surface_common / (surface_common + 6.0) if surface_common else 0.0
            out.at[idx, "common_opponent_count"] = float(len(common))
            if total_weight > 0:
                out.at[idx, "common_opponent_winrate_A"] = sum(value * weight for value, weight in raw_a) / total_weight
                out.at[idx, "common_opponent_winrate_B"] = sum(value * weight for value, weight in raw_b) / total_weight
                out.at[idx, "common_opponent_difference"] = shrink * sum(value * weight for value, weight in weighted_raw) / total_weight
                out.at[idx, "common_opponent_adjusted_edge"] = shrink * sum(value * weight for value, weight in weighted_resid) / total_weight
            out.at[idx, "surface_common_opponent_count"] = surface_common
            if surface_weight_sum > 0:
                out.at[idx, "surface_common_opponent_adjusted_edge"] = (
                    surface_shrink * sum(value * weight for value, weight in weighted_surface_resid) / surface_weight_sum
                )

            expected_p1 = float(sigmoid(float(row.get("structural_match_logit", 0.0))))
            actual_p1 = float(row["label"])
            pending.append((p1, p2, actual_p1, expected_p1, current_date, surface))

        for p1, p2, actual_p1, expected_p1, match_date, surface in pending:
            history.setdefault(p1, {}).setdefault(p2, OpponentMemory()).add(actual_p1, expected_p1, match_date, surface)
            history.setdefault(p2, {}).setdefault(p1, OpponentMemory()).add(1.0 - actual_p1, 1.0 - expected_p1, match_date, surface)

    return out.drop(columns=[col for col in ("_row_date", "_round_order") if col in out.columns])


def feature_columns(frame: pd.DataFrame) -> list[str]:
    return [col for col in frame.columns if col not in META_COLUMNS]


def clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    features = feature_columns(frame)
    cleaned = frame.copy()
    cleaned[features] = cleaned[features].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return cleaned


def calibration_slope_intercept(probs: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    logits = np.array([safe_logit(float(p)) for p in np.clip(probs, 1e-6, 1 - 1e-6)])
    cal = fit_platt(logits, labels.astype(int), epochs=500, lr=0.015)
    return {
        "calibration_slope": round(float(cal["slope"]), 4),
        "calibration_intercept": round(float(cal["intercept"]), 4),
    }


def metric_bundle(probs: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    out = metrics(probs, labels)
    out.update(calibration_slope_intercept(probs, labels))
    return out


class CandidateModel:
    def fit(self, train: pd.DataFrame, features: list[str]) -> None:
        raise NotImplementedError

    def raw_logits(self, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
        raise NotImplementedError

    def payload(self) -> dict[str, Any]:
        return {}


class LogisticCandidate(CandidateModel):
    def __init__(self, l2: float = 0.004, epochs: int = 420) -> None:
        self.l2 = l2
        self.epochs = epochs
        self.model: Any = None

    def fit(self, train: pd.DataFrame, features: list[str]) -> None:
        self.model = fit_logistic(train, features, epochs=self.epochs, l2=self.l2)

    def raw_logits(self, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
        return self.model.raw_logits(rows)

    def payload(self) -> dict[str, Any]:
        return {
            "kind": "logistic",
            "l2": self.l2,
            "features": self.model.features,
            "coefficients": [float(x) for x in self.model.coefficients],
            "intercept": float(self.model.intercept),
            "center": [float(x) for x in self.model.center],
            "scale": [float(x) for x in self.model.scale],
        }


class LightGBMCandidate(CandidateModel):
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.model: Any = None

    def fit(self, train: pd.DataFrame, features: list[str]) -> None:
        import lightgbm as lgb

        dtrain = lgb.Dataset(train[features].to_numpy(dtype=float), label=train["label"].to_numpy(dtype=int))
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "verbosity": -1,
            "seed": 17,
            "num_threads": max(1, min(4, os.cpu_count() or 1)),
            **self.params,
        }
        self.model = lgb.train(params, dtrain, num_boost_round=int(params.pop("num_boost_round", 220)))

    def raw_logits(self, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
        probs = np.clip(self.model.predict(rows[features].to_numpy(dtype=float)), 1e-6, 1 - 1e-6)
        return np.array([safe_logit(float(p)) for p in probs])

    def payload(self) -> dict[str, Any]:
        return {"kind": "lightgbm", "params": self.params, "model_text": self.model.model_to_string()}


class XGBoostCandidate(CandidateModel):
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.model: Any = None

    def fit(self, train: pd.DataFrame, features: list[str]) -> None:
        import xgboost as xgb

        dtrain = xgb.DMatrix(train[features].to_numpy(dtype=float), label=train["label"].to_numpy(dtype=int), feature_names=features)
        params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "seed": 19,
            "nthread": max(1, min(4, os.cpu_count() or 1)),
            "tree_method": "hist",
            **self.params,
        }
        rounds = int(params.pop("num_boost_round", 180))
        self.model = xgb.train(params, dtrain, num_boost_round=rounds)

    def raw_logits(self, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
        import xgboost as xgb

        dtest = xgb.DMatrix(rows[features].to_numpy(dtype=float), feature_names=features)
        probs = np.clip(self.model.predict(dtest), 1e-6, 1 - 1e-6)
        return np.array([safe_logit(float(p)) for p in probs])

    def payload(self) -> dict[str, Any]:
        raw = self.model.save_raw(raw_format="json")
        return {"kind": "xgboost", "params": self.params, "model_json_b64": base64.b64encode(raw).decode("ascii")}


class CatBoostCandidate(CandidateModel):
    def __init__(self, params: dict[str, Any]) -> None:
        self.params = params
        self.model: Any = None

    def fit(self, train: pd.DataFrame, features: list[str]) -> None:
        from catboost import CatBoostClassifier

        self.model = CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="Logloss",
            random_seed=23,
            verbose=False,
            allow_writing_files=False,
            thread_count=max(1, min(4, os.cpu_count() or 1)),
            **self.params,
        )
        self.model.fit(train[features], train["label"])

    def raw_logits(self, rows: pd.DataFrame, features: list[str]) -> np.ndarray:
        probs = np.clip(self.model.predict_proba(rows[features])[:, 1], 1e-6, 1 - 1e-6)
        return np.array([safe_logit(float(p)) for p in probs])

    def payload(self) -> dict[str, Any]:
        return {"kind": "catboost", "params": self.params, "model_pickle_b64": base64.b64encode(pickle.dumps(self.model)).decode("ascii")}


def model_factory(name: str, params: dict[str, Any] | None = None) -> CandidateModel:
    params = params or {}
    if name == "logistic":
        return LogisticCandidate(**params)
    if name == "lightgbm":
        return LightGBMCandidate(params)
    if name == "xgboost":
        return XGBoostCandidate(params)
    if name == "catboost":
        return CatBoostCandidate(params)
    raise ValueError(name)


def evaluate_fold(frame: pd.DataFrame, features: list[str], name: str, params: dict[str, Any], year: int) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    train = frame[frame["year"] < year - 1]
    cal = frame[frame["year"] == year - 1]
    test = frame[frame["year"] == year]
    model = model_factory(name, params)
    model.fit(train, features)
    calibrator = fit_platt(model.raw_logits(cal, features), cal["label"].to_numpy(dtype=int))
    probs = calibrated_probs(model.raw_logits(test, features), calibrator)
    labels = test["label"].to_numpy(dtype=int)
    return probs, labels, metric_bundle(probs, labels)


def walk_forward_model(frame: pd.DataFrame, features: list[str], name: str, params: dict[str, Any], years: list[int]) -> dict[str, Any]:
    started = time.perf_counter()
    folds = []
    pooled_probs = []
    pooled_labels = []
    for year in years:
        if (frame["year"] < year - 1).sum() < 5000 or (frame["year"] == year - 1).sum() < 500 or (frame["year"] == year).sum() < 500:
            continue
        probs, labels, fold_metrics = evaluate_fold(frame, features, name, params, year)
        folds.append({"year": year, "rows": int((frame["year"] == year).sum()), **fold_metrics})
        pooled_probs.append(probs)
        pooled_labels.append(labels)
    if not folds:
        return {"status": "no_folds"}
    pooled = metric_bundle(np.concatenate(pooled_probs), np.concatenate(pooled_labels))
    return {
        "status": "evaluated",
        "folds": folds,
        "pooled_metrics": pooled,
        "mean_log_loss": round(float(np.mean([fold["log_loss"] for fold in folds])), 4),
        "mean_brier_score": round(float(np.mean([fold["brier_score"] for fold in folds])), 4),
        "mean_ece": round(float(np.mean([fold["ece"] for fold in folds])), 4),
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }


def tune_params(frame: pd.DataFrame, features: list[str], name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if name == "logistic":
        candidates = [{"l2": value, "epochs": 420} for value in (0.0015, 0.003, 0.006, 0.012)]
    elif name == "lightgbm":
        candidates = [
            {"learning_rate": 0.035, "num_leaves": 15, "min_data_in_leaf": 90, "feature_fraction": 0.82, "bagging_fraction": 0.82, "bagging_freq": 1, "lambda_l2": 4.0, "num_boost_round": 160},
            {"learning_rate": 0.025, "num_leaves": 23, "min_data_in_leaf": 120, "feature_fraction": 0.78, "bagging_fraction": 0.84, "bagging_freq": 1, "lambda_l2": 7.0, "num_boost_round": 220},
            {"learning_rate": 0.05, "num_leaves": 11, "min_data_in_leaf": 160, "feature_fraction": 0.9, "bagging_fraction": 0.9, "bagging_freq": 1, "lambda_l2": 10.0, "num_boost_round": 130},
        ]
    elif name == "xgboost":
        candidates = [
            {"eta": 0.035, "max_depth": 2, "min_child_weight": 24, "subsample": 0.82, "colsample_bytree": 0.82, "lambda": 8.0, "alpha": 0.2, "num_boost_round": 150},
            {"eta": 0.025, "max_depth": 3, "min_child_weight": 35, "subsample": 0.78, "colsample_bytree": 0.78, "lambda": 12.0, "alpha": 0.4, "num_boost_round": 210},
            {"eta": 0.055, "max_depth": 2, "min_child_weight": 50, "subsample": 0.9, "colsample_bytree": 0.9, "lambda": 16.0, "alpha": 0.8, "num_boost_round": 120},
        ]
    elif name == "catboost":
        candidates = [
            {"iterations": 170, "learning_rate": 0.035, "depth": 3, "l2_leaf_reg": 12.0},
            {"iterations": 220, "learning_rate": 0.025, "depth": 4, "l2_leaf_reg": 16.0},
            {"iterations": 130, "learning_rate": 0.05, "depth": 3, "l2_leaf_reg": 24.0},
        ]
    else:
        raise ValueError(name)

    fold_years = [2020, 2021, 2022, 2023]
    scored = []
    for params in candidates:
        result = walk_forward_model(frame, features, name, params, fold_years)
        scored.append({"params": params, "walk_forward": result})
    valid = [item for item in scored if item["walk_forward"].get("status") == "evaluated"]
    best = min(valid, key=lambda item: (item["walk_forward"]["mean_log_loss"], item["walk_forward"]["mean_brier_score"]))
    return best["params"], {"candidates": scored, "selected": best}


def final_eval(frame: pd.DataFrame, features: list[str], name: str, params: dict[str, Any]) -> tuple[dict[str, Any], CandidateModel, dict[str, Any]]:
    started = time.perf_counter()
    train = frame[frame["year"] <= 2023]
    cal = frame[frame["year"] == 2024]
    test = frame[frame["year"] == 2025]
    model = model_factory(name, params)
    model.fit(train, features)
    calibrator = fit_platt(model.raw_logits(cal, features), cal["label"].to_numpy(dtype=int))
    probs = calibrated_probs(model.raw_logits(test, features), calibrator)
    labels = test["label"].to_numpy(dtype=int)
    result = {
        "feature_count": len(features),
        "features": features,
        "params": params,
        "calibration": calibrator,
        "metrics_2025": metric_bundle(probs, labels),
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    p2026 = np.array([])
    if (frame["year"] == 2026).sum() >= 50:
        rows_2026 = frame[frame["year"] == 2026]
        p2026 = calibrated_probs(model.raw_logits(rows_2026, features), calibrator)
        result["prospective_2026"] = {"rows": int(len(rows_2026)), **metric_bundle(p2026, rows_2026["label"].to_numpy(dtype=int))}
    return result, model, {"test_probs": probs, "test_labels": labels, "p2026": p2026}


def bucket_breakdowns(frame_2025: pd.DataFrame, probs: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    temp = frame_2025.copy()
    temp["_prob"] = probs
    temp["_label"] = labels
    temp["_favorite_prob"] = np.maximum(temp["_prob"], 1.0 - temp["_prob"])
    rank_edge = temp.get("ranking_diff", pd.Series(np.zeros(len(temp)), index=temp.index)).abs()
    temp["_rank_band"] = pd.cut(rank_edge, [-1, 0.03, 0.12, 0.35, 10], labels=["near", "small", "medium", "large"])
    temp["_fav_band"] = pd.cut(temp["_favorite_prob"], [0.5, 0.55, 0.6, 0.7, 0.8, 1.0], labels=["50-55", "55-60", "60-70", "70-80", "80-100"], include_lowest=True)
    out: dict[str, Any] = {}
    for group_name, column in {"surface": "surface", "ranking_band": "_rank_band", "favorite_probability_band": "_fav_band", "tournament_level": "level"}.items():
        values = {}
        for key, group in temp.groupby(column, observed=False):
            if len(group) < 20:
                continue
            values[str(key)] = {"rows": int(len(group)), **metrics(group["_prob"].to_numpy(float), group["_label"].to_numpy(int))}
        out[group_name] = values
    return out


def ablation_report(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    groups = {
        "elo_features": ["overall_elo_diff", "surface_elo_diff", "surface_elo_shrunk_diff", "rating_rd_diff", "rating_uncertainty_sum"],
        "surface_features": ["surface_elo_diff", "surface_elo_shrunk_diff", "surface_residual_form_diff", "surface_h2h_prior_diff", "surface_sample_diff"],
        "recent_form": ["residual_form_short_diff", "residual_form_medium_diff", "surface_residual_form_diff", "score_dominance_diff", "set_dominance_diff", "tiebreak_strength_diff"],
        "serve_return": ["serve_strength_diff", "return_strength_diff", "serve_return_edge", "first_in_diff", "first_won_diff", "second_won_diff", "ace_rate_diff", "df_rate_diff", "bp_save_diff", "bp_convert_diff", "return_point_won_diff", "serve_point_won_diff", "stat_sample_diff", "structural_match_logit"],
        "fatigue_rest": ["days_rest_diff", "recovery_curve_diff", "workload_3d_diff", "workload_7d_diff", "workload_14d_diff"],
        "h2h": ["h2h_prior_diff", "surface_h2h_prior_diff"],
        "common_opponents": ["common_opponent_count", "common_opponent_difference", "common_opponent_adjusted_edge", "surface_common_opponent_count", "surface_common_opponent_adjusted_edge"],
    }
    base = walk_forward_model(frame, features, "logistic", {"l2": 0.004, "epochs": 360}, [2021, 2022, 2023])
    report = {"full_logistic": base, "drop_groups": {}}
    for name, cols in groups.items():
        reduced = [feature for feature in features if feature not in cols]
        if not reduced or len(reduced) == len(features):
            continue
        result = walk_forward_model(frame, reduced, "logistic", {"l2": 0.004, "epochs": 360}, [2021, 2022, 2023])
        if result.get("status") == "evaluated" and base.get("status") == "evaluated":
            result["delta_log_loss_vs_full"] = round(result["mean_log_loss"] - base["mean_log_loss"], 4)
        report["drop_groups"][name] = result
    return report


def make_oof_predictions(frame: pd.DataFrame, features: list[str], model_specs: dict[str, tuple[str, dict[str, Any]]]) -> pd.DataFrame:
    pieces = []
    for year in [2020, 2021, 2022, 2023]:
        fold_rows = frame[frame["year"] == year][["index", "date", "year", "player1", "player2", "label"]].copy()
        for label, (model_name, params) in model_specs.items():
            probs, _, _ = evaluate_fold(frame, features, model_name, params, year)
            fold_rows[f"{label}_prob"] = probs
        pieces.append(fold_rows)
    return pd.concat(pieces, ignore_index=True)


def ensemble_from_oof(oof: pd.DataFrame, candidate_labels: list[str]) -> dict[str, Any]:
    y = oof["label"].to_numpy(dtype=int)
    prob_matrix = np.column_stack([oof[f"{label}_prob"].to_numpy(float) for label in candidate_labels])
    rng = np.random.default_rng(29)
    best_weights = np.ones(len(candidate_labels)) / len(candidate_labels)
    best_loss = float("inf")
    for _ in range(1200):
        weights = rng.dirichlet(np.ones(len(candidate_labels)))
        probs = np.clip(prob_matrix @ weights, 1e-6, 1 - 1e-6)
        loss = float(-(y * np.log(probs) + (1 - y) * np.log(1 - probs)).mean())
        if loss < best_loss:
            best_loss = loss
            best_weights = weights
    return {"labels": candidate_labels, "weights": [float(x) for x in best_weights], "oof_log_loss": round(best_loss, 4)}


def final_ensemble_eval(frame: pd.DataFrame, features: list[str], ensemble: dict[str, Any], specs: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    base_outputs = {}
    raw_logits_by_label = {}
    for label in ensemble["labels"]:
        model_name, params = specs[label]
        result, model, outputs = final_eval(frame, features, model_name, params)
        base_outputs[label] = result
        raw_logits_by_label[label] = model.raw_logits(frame[frame["year"] == 2025], features)
    probs_by_label = [calibrated_probs(raw_logits_by_label[label], base_outputs[label]["calibration"]) for label in ensemble["labels"]]
    probs = np.clip(np.column_stack(probs_by_label) @ np.array(ensemble["weights"]), 1e-6, 1 - 1e-6)
    labels = frame.loc[frame["year"] == 2025, "label"].to_numpy(dtype=int)
    return {
        "weights": dict(zip(ensemble["labels"], [round(float(x), 4) for x in ensemble["weights"]], strict=False)),
        "base_models": base_outputs,
        "metrics_2025": metric_bundle(probs, labels),
    }


def main() -> int:
    started = time.perf_counter()
    np.random.seed(11)
    matches = load_matches()
    if len(matches) < 1000:
        raise SystemExit("No real local match data found in work/tennis-data.")

    base_frame, players, _ = build_feature_rows(matches, temporal_mode="round_safe")
    frame = clean_frame(add_common_opponent_features(base_frame))
    ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(ROWS_PATH, index=False)

    all_features = feature_columns(frame)
    runtime_plus_common = [
        feature
        for feature in all_features
        if feature in RUNTIME_COMPATIBLE_FEATURES
        or feature
        in {
            "common_opponent_count",
            "common_opponent_difference",
            "common_opponent_adjusted_edge",
            "surface_common_opponent_count",
            "surface_common_opponent_adjusted_edge",
        }
    ]
    full_features = all_features
    family_features = candidate_sets(all_features)
    family_features["runtime_plus_common"] = runtime_plus_common
    family_features["common_opponents_only"] = [
        "common_opponent_count",
        "common_opponent_winrate_A",
        "common_opponent_winrate_B",
        "common_opponent_difference",
        "common_opponent_adjusted_edge",
        "surface_common_opponent_count",
        "surface_common_opponent_adjusted_edge",
    ]
    family_features["full_plus_common"] = full_features

    feature_family_scores = {}
    for family, features in family_features.items():
        feature_family_scores[family] = walk_forward_model(frame, features, "logistic", {"l2": 0.004, "epochs": 360}, [2020, 2021, 2022, 2023])

    best_family_name, best_family_result = min(
        [(name, result) for name, result in feature_family_scores.items() if result.get("status") == "evaluated"],
        key=lambda item: (item[1]["mean_log_loss"], item[1]["mean_brier_score"]),
    )
    modeling_features = family_features[best_family_name]

    tuning = {}
    final_models = {}
    specs: dict[str, tuple[str, dict[str, Any]]] = {}
    for model_name in ("logistic", "lightgbm", "xgboost", "catboost"):
        params, search = tune_params(frame, modeling_features, model_name)
        tuning[model_name] = search
        final_result, model, outputs = final_eval(frame, modeling_features, model_name, params)
        final_models[model_name] = final_result
        specs[model_name] = (model_name, params)
        CANDIDATE_ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if model_name != "logistic":
            (CANDIDATE_ARTIFACT_PATH.parent / f"courtiq_{model_name}_candidate.json").write_text(
                json.dumps(
                    {
                        "model_name": model_name,
                        "features": modeling_features,
                        "metrics_2025": final_result["metrics_2025"],
                        "payload_note": "Native model payload stored in advanced_model_comparison_report when practical; production API remains JSON-logistic unless promoted safely.",
                    },
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

    oof = make_oof_predictions(frame, modeling_features, specs)
    oof.to_csv(OOF_PATH, index=False)
    ensemble_spec = ensemble_from_oof(oof, list(specs))
    final_models["time_safe_weighted_ensemble"] = final_ensemble_eval(frame, modeling_features, ensemble_spec, specs)
    ensemble_candidate_path = CANDIDATE_ARTIFACT_PATH.parent / "courtiq_time_safe_weighted_ensemble_candidate.json"
    ensemble_candidate_path.write_text(
        json.dumps(
            {
                "model_name": "time_safe_weighted_ensemble",
                "features": modeling_features,
                "ensemble": ensemble_spec,
                "metrics_2025": final_models["time_safe_weighted_ensemble"]["metrics_2025"],
                "production_note": "Candidate only. It blends calibrated base-model probabilities and is not loaded by the current JSON-logistic production API.",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    comparison = []
    for name, result in final_models.items():
        row = {"model": name, **result["metrics_2025"]}
        comparison.append(row)
    comparison.sort(key=lambda row: (row["log_loss"], row["brier_score"], row["ece"]))
    winner = comparison[0]["model"]
    production_changed = False
    production_reason = "Existing JSON production predictor kept."
    artifact_path = str(MODEL_PATH)
    winning_metrics = comparison[0]
    baseline_metrics = final_models["logistic"]["metrics_2025"]

    if winner == "logistic" and set(modeling_features).issubset(RUNTIME_COMPATIBLE_FEATURES):
        # Only a runtime-compatible logistic can be promoted without changing the API contract.
        if winning_metrics["log_loss"] < VALID_PRODUCTION_BENCHMARK["log_loss"] and winning_metrics["brier_score"] <= VALID_PRODUCTION_BENCHMARK["brier_score"] + 0.002:
            final_logistic, _, _ = final_eval(frame, modeling_features, "logistic", specs["logistic"][1])
            production_model = fit_logistic(frame[frame["year"] <= 2023], modeling_features, epochs=420, l2=specs["logistic"][1].get("l2", 0.004))
            cal = fit_platt(production_model.raw_logits(frame[frame["year"] == 2024]), frame.loc[frame["year"] == 2024, "label"].to_numpy(dtype=int))
            final_logistic["model"] = {
                "type": "enhanced_logistic_regression",
                "feature_names": modeling_features,
                "coefficients": [float(x) for x in production_model.coefficients],
                "intercept": float(production_model.intercept),
                "center": [float(x) for x in production_model.center],
                "scale": [float(x) for x in production_model.scale],
                "calibration": cal,
            }
            promote_corrected_model(final_logistic, players, "advanced_runtime_logistic", len(matches), "round_safe")
            production_changed = True
            production_reason = "Runtime-compatible logistic beat the corrected production benchmark on 2025 log loss and Brier."
    elif winner != "logistic":
        artifact_path = str(ensemble_candidate_path if winner == "time_safe_weighted_ensemble" else CANDIDATE_ARTIFACT_PATH.parent / f"courtiq_{winner}_candidate.json")
        production_reason = "Best probability model is non-logistic; saved as candidate but not promoted because current API loads JSON logistic artifacts only."

    frame_2025 = frame[frame["year"] == 2025]
    best_name, best_spec = (winner, specs[winner]) if winner in specs else ("logistic", specs["logistic"])
    if winner in specs:
        _, _, best_outputs = final_eval(frame, modeling_features, best_spec[0], best_spec[1])
        best_probs = best_outputs["test_probs"]
    else:
        # Ensemble probabilities are reconstructed from its calibrated base models.
        probs_by_label = []
        for label in ensemble_spec["labels"]:
            _, model, _ = final_eval(frame, modeling_features, specs[label][0], specs[label][1])
            cal = final_models["time_safe_weighted_ensemble"]["base_models"][label]["calibration"]
            probs_by_label.append(calibrated_probs(model.raw_logits(frame_2025, modeling_features), cal))
        best_probs = np.clip(np.column_stack(probs_by_label) @ np.array(ensemble_spec["weights"]), 1e-6, 1 - 1e-6)

    report = {
        "status": "ok",
        "run_id": f"advanced-model-comparison-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "data": {
            "source_dir": str(DATA_DIR),
            "matches_processed": len(matches),
            "rows": len(frame),
            "years": [int(frame["year"].min()), int(frame["year"].max())],
            "tours": frame["tour"].value_counts().to_dict(),
            "note": "Only fields present in local CSVs were used; no weather, injury, odds, or point-by-point data were fabricated.",
        },
        "temporal_safety": {
            "train": "all rows through 2023",
            "calibration": "2024 only",
            "test": "2025 untouched until final evaluation",
            "prospective": "2026 reported when available, not used for selection",
            "round_guard": "Rows use round-safe tournament-start-date ordering; matches in the same round are snapshotted before same-round updates.",
        },
        "valid_production_benchmark_from_brief": VALID_PRODUCTION_BENCHMARK,
        "feature_family_scores": feature_family_scores,
        "selected_feature_family": {"name": best_family_name, **best_family_result},
        "tuning": tuning,
        "final_models": final_models,
        "ablation": ablation_report(frame, modeling_features),
        "breakdowns_2025": bucket_breakdowns(frame_2025, best_probs, frame_2025["label"].to_numpy(dtype=int)),
        "comparison_table": comparison,
        "decision": {
            "winning_model": winner,
            "production_model_changed": production_changed,
            "artifact_path": artifact_path,
            "production_reason": production_reason,
            "improvement_vs_logistic_2025": {
                "log_loss": round(winning_metrics["log_loss"] - baseline_metrics["log_loss"], 4),
                "brier_score": round(winning_metrics["brier_score"] - baseline_metrics["brier_score"], 4),
                "ece": round(winning_metrics["ece"] - baseline_metrics["ece"], 4),
            },
            "improvement_vs_valid_benchmark": {
                "log_loss": round(winning_metrics["log_loss"] - VALID_PRODUCTION_BENCHMARK["log_loss"], 4),
                "brier_score": round(winning_metrics["brier_score"] - VALID_PRODUCTION_BENCHMARK["brier_score"], 4),
                "ece": round(winning_metrics["ece"] - VALID_PRODUCTION_BENCHMARK["ece"], 4),
            },
        },
        "outputs": {
            "feature_rows": str(ROWS_PATH),
            "oof_predictions": str(OOF_PATH),
            "report": str(REPORT_PATH),
        },
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH), "comparison_table": comparison, "decision": report["decision"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
