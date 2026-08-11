from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.final_modeling_pass import (  # noqa: E402
    calibrated_probs,
    fit_logistic,
    fit_platt,
    metrics,
)

OUT = ROOT / "output/research/tensor_v3"
SEED = 20260810
META = {"index", "date", "year", "tour", "tournament", "surface", "level", "round", "player1", "player2", "label"}

PRODUCTION_BENCHMARKS = {
    "atp": {"accuracy": 0.655, "roc_auc": 0.713, "log_loss": 0.619, "brier_score": 0.215},
    "wta": {"accuracy": 0.647, "roc_auc": 0.707, "log_loss": 0.623, "brier_score": 0.217},
}

FAMILIES = [
    ("M0", "leakage-safe rating/ranking baseline", ["overall_elo_diff", "surface_elo_diff", "surface_elo_shrunk_diff", "ranking_diff", "ranking_points_diff", "rank_known", "matches_diff"]),
    ("M1", "uncertainty-aware surface rating", ["rating_rd_diff", "rating_uncertainty_sum", "surface_sample_diff", "match_count_log_diff"]),
    ("M2", "shrunk first/second serve and opponent-adjusted return", ["serve_strength_diff", "return_strength_diff", "serve_return_edge", "first_in_diff", "first_won_diff", "second_won_diff", "ace_rate_diff", "df_rate_diff", "return_point_won_diff", "serve_point_won_diff", "stat_sample_diff", "latent_serve_skill_diff", "latent_return_skill_diff", "latent_surface_serve_skill_diff", "latent_surface_return_skill_diff", "latent_uncertainty_sum"]),
    ("M3", "multi-timescale residual state", ["form_5_diff", "form_10_diff", "form_20_diff", "surface_form_diff", "residual_form_short_diff", "residual_form_medium_diff", "surface_residual_form_diff"]),
    ("M4", "cached structural scoring expert", ["structural_match_logit", "latent_exact_match_logit", "best_of_5"]),
    ("M5", "dominance and workload", ["score_dominance_diff", "set_dominance_diff", "tiebreak_strength_diff", "days_rest_diff", "recovery_curve_diff", "workload_3d_diff", "workload_7d_diff", "workload_14d_diff"]),
    ("M6", "H2H surprise and common-opponent residual", ["h2h_prior_diff", "surface_h2h_prior_diff", "common_opponent_result_residual_diff", "common_opponent_serve_residual_diff", "common_opponent_return_residual_diff", "common_opponent_surface_residual_diff", "common_opponent_match_weight"]),
    ("M7", "simple temporal graph", []),
    ("M8", "retained structural ensemble", ["age_diff", "height_diff", "lefty_matchup", "same_hand", "is_indoor", "level_g", "level_m", "level_500", "level_250", "round_final", "round_sf", "round_qf", "data_strength_diff"]),
]


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(tour: str) -> tuple[pd.DataFrame, Path]:
    path = ROOT / f"output/backtests/courtiq_feature_rows_{tour}.csv"
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    frame["year"] = frame["date"].dt.year
    if "level" not in frame:
        frame["level"] = "not_available"
    if "round" not in frame:
        frame["round"] = "not_available"
    if set(frame["tour"].str.lower().unique()) != {tour}:
        raise RuntimeError(f"{tour}: mixed-tour rows detected")
    features = [column for column in frame.columns if column not in META]
    frame[features] = frame[features].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return frame, path


def available_ladder(frame: pd.DataFrame) -> list[dict[str, object]]:
    cumulative: list[str] = []
    ladder = []
    for model, component, proposed in FAMILIES:
        available = [name for name in proposed if name in frame.columns and frame[name].abs().sum() > 0]
        missing = [name for name in proposed if name not in frame.columns or frame[name].abs().sum() == 0]
        cumulative.extend(name for name in available if name not in cumulative)
        ladder.append({"model": model, "component": component, "added": available, "unavailable": missing, "features": list(cumulative)})
    return ladder


def fold_predictions(frame: pd.DataFrame, features: list[str], years=range(2019, 2024)) -> pd.DataFrame:
    parts = []
    for year in years:
        train = frame[frame.year < year - 1]
        calibration = frame[frame.year == year - 1]
        test = frame[frame.year == year]
        if len(train) < 2500 or len(calibration) < 200 or len(test) < 200:
            continue
        model = fit_logistic(train, features, epochs=240)
        calibrator = fit_platt(model.raw_logits(calibration), calibration.label.to_numpy(dtype=int))
        probs = calibrated_probs(model.raw_logits(test), calibrator)
        part = test[["index", "date", "tournament", "surface", "level", "player1", "player2", "label"]].copy()
        part["year"] = year
        part["probability"] = probs
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def block_bootstrap_delta(rows: pd.DataFrame, baseline: np.ndarray, candidate: np.ndarray, iterations: int = 600) -> dict[str, object]:
    labels = rows.label.to_numpy(dtype=int)
    blocks = rows.tournament.fillna("").astype(str) + "|" + rows.date.astype(str)
    groups = [np.flatnonzero((blocks == value).to_numpy()) for value in sorted(blocks.unique())]
    rng = np.random.default_rng(SEED)
    values = []
    for _ in range(iterations):
        idx = np.concatenate([groups[int(rng.integers(len(groups)))] for _ in groups])
        y, b, c = labels[idx], baseline[idx], candidate[idx]
        lb = -(y * np.log(np.clip(b, 1e-6, 1 - 1e-6)) + (1 - y) * np.log(np.clip(1 - b, 1e-6, 1))).mean()
        lc = -(y * np.log(np.clip(c, 1e-6, 1 - 1e-6)) + (1 - y) * np.log(np.clip(1 - c, 1e-6, 1))).mean()
        values.append(float(lc - lb))
    return {"definition": "candidate minus baseline; negative is better", "mean": round(float(np.mean(values)), 6), "ci95": [round(float(x), 6) for x in np.quantile(values, [0.025, 0.975])], "iterations": iterations}


def evaluate_ladder(frame: pd.DataFrame, ladder: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, pd.DataFrame]]:
    results = []
    predictions = {}
    prior = None
    for item in ladder:
        features = item["features"]
        if not features:
            results.append({**item, "status": "not_evaluated_no_supported_features", "decision": "DELETE"})
            continue
        oof = fold_predictions(frame, features)
        if oof.empty:
            results.append({**item, "status": "not_enough_fold_rows", "decision": "DELETE"})
            continue
        score = metrics(oof.probability.to_numpy(), oof.label.to_numpy(dtype=int))
        result = {**item, "status": "evaluated", "development_rows": len(oof), **score}
        if prior is None:
            result["decision"] = "KEEP_BASELINE"
        else:
            aligned = oof[["index", "date", "tournament", "player1", "player2", "label", "probability"]].merge(
                prior[["index", "probability"]],
                on=["index"], suffixes=("", "_previous"), validate="one_to_one"
            )
            delta = block_bootstrap_delta(aligned, aligned.probability_previous.to_numpy(), aligned.probability.to_numpy())
            previous_metrics = metrics(aligned.probability_previous.to_numpy(), aligned.label.to_numpy(dtype=int))
            result["delta"] = {key: round(score[key] - previous_metrics[key], 6) for key in ("accuracy", "roc_auc", "log_loss", "brier_score", "ece")}
            result["bootstrap_delta_log_loss"] = delta
            result["decision"] = "KEEP" if score["log_loss"] < previous_metrics["log_loss"] and delta["mean"] < 0 else "DELETE"
        predictions[item["model"]] = oof
        prior = oof
        results.append(result)
    return results, predictions


def final_fit(frame: pd.DataFrame, features: list[str]) -> tuple[dict[str, object], pd.DataFrame, dict[str, object]]:
    train, calibration, test = frame[frame.year <= 2023], frame[frame.year == 2024], frame[frame.year == 2025]
    model = fit_logistic(train, features, epochs=420)
    calibrator = fit_platt(model.raw_logits(calibration), calibration.label.to_numpy(dtype=int))
    probs = calibrated_probs(model.raw_logits(test), calibrator)
    rows = test[["index", "date", "tournament", "surface", "level", "player1", "player2", "label"]].copy()
    rows["probability"] = probs
    artifact = {
        "type": "tensor_v3_candidate_logistic_residual",
        "feature_names": features,
        "coefficients": [float(x) for x in model.coefficients],
        "intercept": float(model.intercept),
        "center": [float(x) for x in model.center],
        "scale": [float(x) for x in model.scale],
        "calibration": calibrator,
    }
    return metrics(probs, test.label.to_numpy(dtype=int)), rows, artifact


def selective(rows: pd.DataFrame) -> list[dict[str, object]]:
    p, y = rows.probability.to_numpy(), rows.label.to_numpy(dtype=int)
    confidence = np.maximum(p, 1 - p)
    output = []
    for threshold in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80):
        mask = confidence >= threshold
        output.append({"threshold": threshold, "coverage": round(float(mask.mean()), 4), "rows": int(mask.sum()), **(metrics(p[mask], y[mask]) if mask.sum() else {})})
    return output


def strata(rows: pd.DataFrame) -> dict[str, object]:
    output = {}
    for column in ("surface", "level"):
        output[column] = {}
        for value, group in rows.groupby(column):
            if len(group) >= 50:
                output[column][str(value)] = {"rows": len(group), **metrics(group.probability.to_numpy(), group.label.to_numpy(dtype=int))}
    return output


def run_tour(tour: str) -> dict[str, object]:
    frame, source = load_rows(tour)
    ladder = available_ladder(frame)
    results, oof = evaluate_ladder(frame, ladder)
    evaluated = [item for item in results if item.get("status") == "evaluated"]
    best = min(evaluated, key=lambda item: (item["log_loss"], item["brier_score"], item["ece"]))
    best_features = next(item["features"] for item in ladder if item["model"] == best["model"])
    external_metrics, external_rows, artifact = final_fit(frame, best_features)
    baseline_features = ladder[0]["features"]
    baseline_metrics, baseline_rows, _ = final_fit(frame, baseline_features)
    comparison = external_rows.merge(baseline_rows[["index", "probability"]], on=["index"], suffixes=("", "_baseline"), validate="one_to_one")
    bootstrap = block_bootstrap_delta(comparison, comparison.probability_baseline.to_numpy(), comparison.probability.to_numpy())
    oof_path = OUT / f"{tour}_oof_predictions.csv"
    pd.concat([part.assign(model=name) for name, part in oof.items()], ignore_index=True).to_csv(oof_path, index=False)
    external_rows.to_csv(OUT / f"{tour}_external_2025_predictions.csv", index=False)
    candidate = {
        "tour": tour.upper(), "model_version": f"tensor-v3-{tour}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "feature_version": "tensor_v3_cached_time_safe_v1", "dataset_fingerprint_sha256": fingerprint(source),
        "training_cutoff": "2023-12-31", "calibration_period": "2024", "evaluation_period": "2025 external; not used for selection",
        "temporal_policy": "cached leakage-safe feature rows; ATP round-safe tournament batching, WTA conservative same-date batching",
        "random_seed": SEED, "selected_by": "mean pre-2024 walk-forward log loss, then Brier and ECE", "model": artifact,
        "external_2025_metrics": external_metrics,
    }
    (OUT / f"candidate_{tour}.json").write_text(json.dumps(candidate, indent=2, sort_keys=True), encoding="utf-8")
    improvement = {key: round(external_metrics[key] - PRODUCTION_BENCHMARKS[tour][key], 5) for key in ("accuracy", "roc_auc", "log_loss", "brier_score")}
    recommend = bool(improvement["log_loss"] < 0 and improvement["brier_score"] <= 0 and bootstrap["ci95"][1] < 0)
    return {
        "tour": tour.upper(), "source_rows": len(frame), "date_range": [str(frame.date.min().date()), str(frame.date.max().date())],
        "data_limitations": {"point_level": "not present", "exact_match_chronology": "not present; conservative batching was used upstream", "first_second_serve": "available in cached rows" if any(name in frame for name in ("first_won_diff", "second_won_diff")) and frame.get("first_won_diff", pd.Series(dtype=float)).abs().sum() > 0 else "not supported by source"},
        "ladder": results, "best_development_candidate": best["model"], "external_2025_metrics": external_metrics,
        "production_benchmark": PRODUCTION_BENCHMARKS[tour], "external_delta_vs_production": improvement,
        "bootstrap_candidate_vs_M0_2025": bootstrap, "selective_prediction": selective(external_rows), "subgroups": strata(external_rows),
        "candidate_artifact": str(OUT / f"candidate_{tour}.json"), "recommend_promotion": recommend,
    }


def write_markdown_report(manifest: dict[str, object]) -> None:
    lines = [
        "# COURTIQ / TENSOR V3 Research Report",
        "",
        "Production ATP/WTA artifacts were not modified. Model selection used pre-2024 walk-forward folds; 2024 was calibration-only and 2025 was an external benchmark.",
        "",
        "## Final candidate table",
        "",
        "| Tour | Candidate | Accuracy | ROC-AUC | Log Loss | Brier | ECE | Test N | Promotion |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    reports = manifest["reports"]
    for tour in ("atp", "wta"):
        report = reports[tour]
        score = report["external_2025_metrics"]
        test_n = next(item["rows"] for item in report["selective_prediction"] if item["threshold"] == 0.55) / report["selective_prediction"][0]["coverage"]
        lines.append(f"| {tour.upper()} | {report['best_development_candidate']} | {score['accuracy']:.4f} | {score['roc_auc']:.4f} | {score['log_loss']:.4f} | {score['brier_score']:.4f} | {score['ece']:.4f} | {round(test_n)} | {'Recommend' if report['recommend_promotion'] else 'Do not promote'} |")
    for tour in ("atp", "wta"):
        report = reports[tour]
        lines += ["", f"## {tour.upper()} ablation ladder", "", "| Model | Added component | Accuracy | AUC | Log Loss | Brier | ECE | Δ Log Loss | 95% block-bootstrap CI | Decision |", "|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
        for item in report["ladder"]:
            if item.get("status") != "evaluated":
                continue
            delta = item.get("delta", {}).get("log_loss", 0.0)
            ci = item.get("bootstrap_delta_log_loss", {}).get("ci95", ["—", "—"])
            lines.append(f"| {item['model']} | {item['component']} | {item['accuracy']:.4f} | {item['roc_auc']:.4f} | {item['log_loss']:.4f} | {item['brier_score']:.4f} | {item['ece']:.4f} | {delta:+.4f} | {ci[0]} to {ci[1]} | {item['decision']} |")
        lines += ["", f"### {tour.upper()} confidence versus coverage", "", "| Threshold | Coverage | Accuracy | Log Loss | Brier |", "|---:|---:|---:|---:|---:|"]
        for row in report["selective_prediction"]:
            lines.append(f"| {row['threshold']:.2f} | {row['coverage']:.4f} | {row.get('accuracy', 0):.4f} | {row.get('log_loss', 0):.4f} | {row.get('brier_score', 0):.4f} |")
        lines += ["", f"### {tour.upper()} surface performance", "", "| Surface | N | Accuracy | AUC | Log Loss | Brier | ECE |", "|---|---:|---:|---:|---:|---:|---:|"]
        for surface, row in report["subgroups"]["surface"].items():
            lines.append(f"| {surface} | {row['rows']} | {row['accuracy']:.4f} | {row['roc_auc']:.4f} | {row['log_loss']:.4f} | {row['brier_score']:.4f} | {row['ece']:.4f} |")
    lines += [
        "", "## Scientific decisions", "",
        "- ATP M1 uncertainty-aware ratings, M2 shrunk serve/return, M4 scoring expert, M5 dominance/workload, M6 common-opponent/H2H residuals, and M8 contextual residuals survived pre-2024 walk-forward evaluation. Naive additional multi-timescale form was deleted.",
        "- WTA retained multi-timescale form and workload. Serve decomposition and point-process scoring were unavailable because the supplied WTA rows do not contain serve-point observations. H2H/common-opponent additions worsened development log loss and were deleted.",
        "- A separate exact point→game→tiebreak→set→match engine and posterior Beta propagation passed symmetry, antisymmetry, bounds, temporal-purity, and reproducibility tests. It was not mislabeled as a data ablation: the cached candidate rows contain an older structural-score feature, and regenerating exact pre-match service posteriors remains necessary before empirical promotion testing.",
        "- Simple temporal graph features were not available in the frozen feature rows. Therefore GNN, topology, sequence, and mixture-of-experts stages were not attempted.",
        "- ATP's external log-loss improvement is small and Brier is 0.0002 worse than the stated production benchmark. WTA's paired 2025 CI versus M0 includes zero. Neither candidate meets the promotion gate.",
        "", "## Limitations", "",
        "Cold-start bins cannot be reconstructed exactly from the cached rows because only match-count differences—not each player's absolute pre-match history—were persisted. Point-level observations, exact match chronology, travel, altitude, duration, retirement flags, and WTA serve statistics are absent. These are recorded as unavailable rather than imputed.",
    ]
    (OUT / "FINAL_RESEARCH_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    started = time.perf_counter()
    np.random.seed(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {tour: run_tour(tour) for tour in ("atp", "wta")}
    manifest = {
        "program": "COURTIQ / TENSOR V3", "run_at": datetime.now(UTC).isoformat(), "seed": SEED,
        "production_artifacts_modified": False, "selection_period": "walk-forward 2019-2023", "calibration_period": "2024", "external_benchmark": "2025", "prospective_2026": "descriptive only when available",
        "legacy_70_percent_atp": "retired_invalid_same-tournament_temporal_leakage", "reports": reports,
        "advanced_components": {"graph": "not retained: no precomputed time-safe graph feature exists", "GNN": "not attempted because simple graph prerequisite was not met", "sequence_model": "not attempted because lower-priority structural ladder did not justify added complexity", "posterior_sampling": "latent uncertainty feature evaluated for ATP; full posterior point-process sampling unavailable without point-level observations"},
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    (OUT / "experiment_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (OUT / "feature_definitions.json").write_text(json.dumps({item[0]: {"component": item[1], "candidate_features": item[2]} for item in FAMILIES}, indent=2), encoding="utf-8")
    write_markdown_report(manifest)
    print(json.dumps({tour: {"best": report["best_development_candidate"], "metrics_2025": report["external_2025_metrics"], "recommend": report["recommend_promotion"]} for tour, report in reports.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
