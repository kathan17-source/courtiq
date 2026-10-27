# ATP evaluation provenance review

## Conclusion

**Current ATP performance metrics are unverified.** Equality with retired metrics is not proof of contamination. Independent numerical scoring reproduces the published four-decimal values, but the available raw CSVs do not regenerate the exact saved features or fitted parameters. The available evidence therefore does not certify the exact model's original leakage-safe training/evaluation chain.

The serialized model, calibration, feature order, player state, version and working inference are preserved. Active `metrics` values are null, with the original reported figures retained explicitly under `unverified_evaluation` and the unchanged retirement record. API/UI performance displays withhold those ATP figures. Schema-valid inference is distinct from independently validated predictive performance.

## Evidence inspected and executed

- Current artifact: `courtiq-real-20260809154449-enhanced_runtime_safe`, 48 features, 78,091 processed ATP matches. Its retired predecessor field names `courtiq-real-20260809152750-enhanced_runtime_safe` and contains the same reported metrics.
- Reviewed `train_models.py`, `final_modeling_pass.py`, temporal-sensitivity scripts/reports, runtime feature/serving code, synthetic temporal fixtures and TENSOR v3. The promoter recomputes metrics and also copies the previous artifact's metrics into the retirement field: repeated values can arise without demonstrating contamination.
- Located local source CSVs, the 78,091-row saved feature table and an ATP backtest report. Those raw rows are not distributed. The report alone is not independent proof. Its original `data_snapshot_hash` hashes filenames and sizes, not file contents.
- Regenerated round-safe features from the available raw files; compared them with the cache; refitted the declared training/calibration split to check the exact serialized parameters; scored the **existing** serialized parameters with independently implemented accuracy, pairwise AUC, log loss, Brier and ten-bin ECE formulas.

| Split | Rows | Tournament-start dates |
|---|---:|---|
| Training | 71,934 | 2000-01-03–2023-11-27 |
| Calibration only | 3,159 | 2024-01-01–2024-12-29 |
| Evaluation | 2,861 | 2025-01-06–2025-12-22 |

The source span extends to 2026-01-17; those rows are not the 2025 test sample. Data sources are locally supplied Jeff Sackmann-format ATP CSVs. Full source-content hashes, exact model-content hash, environment/code hashes, unrounded recomputation and failed reproduction checks are in [atp-reproduction.json](atp-reproduction.json).

## Reproduction result and limits

The reported figures—accuracy **0.6550**, ROC-AUC **0.7132**, log loss **0.6185**, Brier **0.2154**, ECE **0.0271**—are reproduced to four decimals both by independent cached-row scoring and by scoring regenerated rows with the existing model. They remain **unverified as the model's validated production benchmark**, not fabricated substitutes or proof of contamination.

The feature comparison finds six differing cells in 2003 (maximum absolute difference 0.0260521) and 107 in 2025 (maximum 0.0006), beyond the declared 1e-10 comparison tolerance. Match identities, labels and dates align. Refit maximum coefficient difference is about 1.23766e-5; scale differs by about 1.67427e-6 and intercept by 9.12721e-8. Calibration matches. The frozen historical input contents are not bound by the original filename/size hash, so the cause of these discrepancies is unresolved. Numerical rounding agreement cannot resolve that provenance gap. No claim is made that these differences prove leakage or materially change predictions.

The temporal policy batches matches by tournament start date and tournament, freezes earliest-round player metadata, snapshots same-round matches before applying results, and permits earlier-round results to update later rounds. Existing synthetic tests cover same-round and later-round/metadata contamination. Exact match timestamps are absent; tournament ordering remains an assumption. Retrospective data cannot establish contemporaneous capture, and the inspected 2025 period is not a new unseen or prospective holdout. Independent metric formulas reuse the existing feature generator and do not independently certify every feature/source assumption.

TENSOR v3's ATP M8 / WTA M5 candidate metrics and manifest are unchanged and are not current-model metrics. Its production-reference constants were rounded (e.g. ATP log loss 0.619 and Brier 0.215), so historical deltas against them do not compare the exact current artifact; no candidate is promoted in this review.

## Authorized reproduction

Install the developer dependencies, obtain only source data you are entitled to use, then run against a new report path:

```sh
python scripts/verify_atp_evaluation.py --data-dir /path/to/authorized/tennis-data --cached-rows /path/to/saved/courtiq_feature_rows_atp.csv --report /tmp/atp-audit.json
```

The command regenerates/refits for comparison and scores the current parameters, but never writes or promotes a model. `--cached-rows` is optional; full content hashes and direct raw regeneration remain necessary. It refuses an existing report path. Inspect `status` and every verification field; successful script execution is not itself a verified result. A failed raw/refit/cache check must not be bypassed by copying retired numbers or adding a status flag.

The loader exposes flagged metrics only when an independently reproduced report is content-hash-bound to the exact model, model version, temporal policy, sample and metrics. Missing, stale, inconsistent or unverified evidence fails closed for evaluation display while leaving inference available. WTA remains explicitly artifact-reported; this audit does not independently validate it. Rights and research limitations elsewhere in the repository remain in force.
