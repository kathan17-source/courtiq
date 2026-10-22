from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.final_modeling_pass import (
    ROOT,
    RUNTIME_COMPATIBLE_FEATURES,
    build_feature_rows,
    candidate_sets,
    final_test_probabilities,
    load_matches,
    metrics,
)

OUT = ROOT / "output/research/temporal_sensitivity"


def paired_delta(round_probs, frozen_probs, labels, rows, iterations=500):
    blocks = rows["tournament"].astype(str) + "|" + rows["date"].astype(str)
    groups = [np.flatnonzero((blocks == block).to_numpy()) for block in sorted(blocks.unique())]
    rng = np.random.default_rng(23)
    values = {"log_loss": [], "brier": []}
    for _ in range(iterations):
        sample = np.concatenate([groups[int(rng.integers(len(groups)))] for _ in groups])
        y, a, b = labels[sample], round_probs[sample], frozen_probs[sample]
        values["log_loss"].append(float(np.mean(-(y*np.log(b)+(1-y)*np.log(1-b))) - np.mean(-(y*np.log(a)+(1-y)*np.log(1-a)))))
        values["brier"].append(float(np.mean((b-y)**2) - np.mean((a-y)**2)))
    return {key: {"mean_delta_frozen_minus_round_safe": round(float(np.mean(val)), 6), "ci_95": [round(float(x), 6) for x in np.quantile(val, [0.025, 0.975])]} for key, val in values.items()}


def main():
    matches = load_matches()
    results = {}
    probability_sets = {}
    for mode in ("round_safe", "tournament_frozen"):
        frame, _, _ = build_feature_rows(matches, temporal_mode=mode)
        feature_cols = [c for c in frame.columns if c not in {"index","date","year","tour","tournament","surface","level","round","player1","player2","label"}]
        frame[feature_cols] = frame[feature_cols].replace([np.inf,-np.inf],0).fillna(0)
        features = [f for f in candidate_sets(feature_cols)["enhanced_runtime_safe"] if f in RUNTIME_COMPATIBLE_FEATURES]
        probs, labels, rows = final_test_probabilities(frame, features)
        order = np.argsort(rows["index"].to_numpy(), kind="stable")
        probs, labels, rows = probs[order], labels[order], rows.iloc[order].reset_index(drop=True)
        results[mode] = {"held_out_rows": len(labels), **metrics(probs, labels)}
        probability_sets[mode] = (np.clip(probs,1e-6,1-1e-6), labels, rows)
    rp, labels, rows = probability_sets["round_safe"]
    fp, frozen_labels, frozen_rows = probability_sets["tournament_frozen"]
    if not np.array_equal(labels, frozen_labels) or list(rows["index"]) != list(frozen_rows["index"]):
        raise RuntimeError("Temporal modes produced non-aligned held-out rows")
    payload = {"status":"research_only_no_promotion","method":"same fixed enhanced_runtime_safe specification; train <=2023, calibrate 2024, test 2025","metrics":results,"paired_tournament_block_bootstrap":paired_delta(rp,fp,labels,rows)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "metrics.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
    (OUT / "METHODOLOGY.md").write_text("# ATP temporal sensitivity\n\nRound-safe updates player state only after every match in an earlier round has been snapshotted. Tournament-frozen snapshots every match in a tournament from player state at tournament entry and applies results only after all tournament predictions. Both modes use the identical fixed enhanced-runtime-safe feature specification, training years through 2023, 2024-only calibration, and the 2025 held-out benchmark. No production artifact is written or promoted.\n\nThe evaluation uses the locally supplied ATP match CSVs in Jeff Sackmann's `tennis_atp` format, with `tourney_date` interpreted as the tournament start date.\n\nReproduce: `.venv/bin/python scripts/run_temporal_sensitivity.py`\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
