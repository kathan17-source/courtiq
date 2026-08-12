#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import train_match_model as trainer


def artifact_paths(root: Path, tour: str) -> tuple[Path, Path, Path]:
    suffix = "" if tour == "all" else f"_{tour}"
    return (
        root / f"output/models/courtiq_model{suffix}.json",
        root / f"output/backtests/courtiq_backtest_report{suffix}.json",
        root / f"output/backtests/courtiq_feature_rows{suffix}.csv",
    )


def train_atp_round_safe(root: Path) -> dict[str, object]:
    from scripts import final_modeling_pass as atp_trainer

    model_path, backtest_path, feature_path = artifact_paths(root, "atp")
    temporal_mode = "round_safe"
    matches = [match for match in atp_trainer.load_matches() if match.tour == "atp"]
    if not matches:
        raise SystemExit("No ATP matches found. Put ATP CSVs in work/tennis-data/ or work/tennis-data/atp/.")
    frame, players, _ = atp_trainer.build_feature_rows(matches, temporal_mode=temporal_mode)
    feature_cols = [
        col
        for col in frame.columns
        if col not in {"index", "date", "year", "tour", "tournament", "surface", "level", "round", "player1", "player2", "label"}
    ]
    frame[feature_cols] = frame[feature_cols].replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    features = atp_trainer.candidate_sets(feature_cols)["enhanced_runtime_safe"]
    final = atp_trainer.final_train_eval(frame, features)

    atp_trainer.MODEL_PATH = model_path
    atp_trainer.REPORT_PATH = backtest_path
    atp_trainer.ENHANCED_ROWS_PATH = feature_path
    atp_trainer.SAVED_FEATURE_ROWS_PATH = feature_path
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(feature_path, index=False)
    atp_trainer.promote_corrected_model(final, players, "enhanced_runtime_safe", len(matches), temporal_mode)

    report = {
        "status": "ok",
        "tour": "atp",
        "temporal_mode": temporal_mode,
        "temporal_policy": "round-safe tournament batches: earlier rounds update later rounds; same-round matches are snapshotted before same-round updates",
        "matches": len(matches),
        "feature_rows": int(len(frame)),
        "players": len(players),
        "splits": {
            "train": int((frame["year"] <= 2023).sum()),
            "validation": int((frame["year"] == 2024).sum()),
            "test": int((frame["year"] == 2025).sum()),
            "train_rule": "date <= 2023",
            "calibration_rule": "date == 2024",
            "final_holdout_rule": "date == 2025",
            "split_type": "fixed_modern_holdout",
        },
        "models": {"enhanced_runtime_safe": {"test": final["metrics_2025"], "calibration": final["calibration"]}},
    }
    backtest_path.parent.mkdir(parents=True, exist_ok=True)
    backtest_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "tour": "atp",
        "model": str(model_path),
        "backtest": str(backtest_path),
        "feature_rows": str(feature_path),
        "test": final["metrics_2025"],
    }


def train_basic_tour(root: Path, tour: str) -> dict[str, object]:
    matches = trainer.load_matches(trainer.DATA_DIR)
    matches = [match for match in matches if match.tour == tour]
    if not matches:
        raise SystemExit(f"No {tour.upper()} matches found. Put CSVs in work/tennis-data/{tour}/ or use {tour}_matches_YYYY.csv.")
    rows, players = trainer.process_matches(matches)
    if len(rows) < 1000:
        raise SystemExit(f"Need at least 1000 chronological rows for {tour.upper()} training. Found {len(rows)}.")

    model_path, backtest_path, feature_path = artifact_paths(root, tour)
    trainer.MODEL_PATH = model_path
    trainer.BACKTEST_PATH = backtest_path
    trainer.FEATURE_ROWS_PATH = feature_path

    train, validation, _ = trainer.split_rows(rows)
    weights, intercept = trainer.fit_logistic(train)
    calibrator = trainer.fit_platt_calibrator(validation, weights, intercept)
    report = trainer.write_outputs(matches, rows, players, weights, intercept, calibrator)
    return {
        "tour": tour,
        "model": str(model_path),
        "backtest": str(backtest_path),
        "feature_rows": str(feature_path),
        "test": report["models"]["logistic_regression"]["test"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train CourtIQ match models from Jeff Sackmann-style ATP/WTA CSVs.")
    parser.add_argument("--tour", choices=["all", "atp", "wta"], default="all")
    args = parser.parse_args()

    if args.tour == "atp":
        print(json.dumps(train_atp_round_safe(trainer.ROOT), indent=2))
        return 0

    if args.tour == "all":
        print(json.dumps({"atp": train_atp_round_safe(trainer.ROOT), "wta": train_basic_tour(trainer.ROOT, "wta")}, indent=2))
        return 0

    print(json.dumps(train_basic_tour(trainer.ROOT, args.tour), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
