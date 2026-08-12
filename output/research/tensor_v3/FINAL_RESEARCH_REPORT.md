# COURTIQ / TENSOR V3 Research Report

Production ATP/WTA artifacts were not modified. Model selection used pre-2024 walk-forward folds; 2024 was calibration-only and 2025 was an external benchmark.

## Final candidate table

| Tour | Candidate | Accuracy | ROC-AUC | Log Loss | Brier | ECE | Test N | Promotion |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ATP | M8 | 0.6547 | 0.7136 | 0.6181 | 0.2152 | 0.0223 | 2861 | Do not promote |
| WTA | M5 | 0.6600 | 0.7232 | 0.6129 | 0.2122 | 0.0219 | 2365 | Do not promote |

## ATP ablation ladder

| Model | Added component | Accuracy | AUC | Log Loss | Brier | ECE | Δ Log Loss | 95% block-bootstrap CI | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| M0 | leakage-safe rating/ranking baseline | 0.6492 | 0.7118 | 0.6175 | 0.2151 | 0.0099 | +0.0000 | — to — | KEEP_BASELINE |
| M1 | uncertainty-aware surface rating | 0.6491 | 0.7132 | 0.6163 | 0.2147 | 0.0091 | -0.0012 | -0.002039 to -0.000233 | KEEP |
| M2 | shrunk first/second serve and opponent-adjusted return | 0.6560 | 0.7174 | 0.6136 | 0.2134 | 0.0098 | -0.0027 | -0.003967 to -0.001571 | KEEP |
| M3 | multi-timescale residual state | 0.6552 | 0.7171 | 0.6137 | 0.2135 | 0.0105 | +0.0001 | -0.000396 to 0.0006 | DELETE |
| M4 | cached structural scoring expert | 0.6560 | 0.7175 | 0.6133 | 0.2134 | 0.0115 | -0.0004 | -0.00074 to 2.4e-05 | KEEP |
| M5 | dominance and workload | 0.6580 | 0.7199 | 0.6114 | 0.2126 | 0.0120 | -0.0019 | -0.002682 to -0.001036 | KEEP |
| M6 | H2H surprise and common-opponent residual | 0.6578 | 0.7220 | 0.6099 | 0.2119 | 0.0131 | -0.0015 | -0.002398 to -0.000635 | KEEP |
| M7 | simple temporal graph | 0.6578 | 0.7220 | 0.6099 | 0.2119 | 0.0131 | +0.0000 | 0.0 to 0.0 | DELETE |
| M8 | retained structural ensemble | 0.6619 | 0.7271 | 0.6064 | 0.2103 | 0.0164 | -0.0035 | -0.004646 to -0.002219 | KEEP |

### ATP confidence versus coverage

| Threshold | Coverage | Accuracy | Log Loss | Brier |
|---:|---:|---:|---:|---:|
| 0.55 | 0.8277 | 0.6845 | 0.6024 | 0.2079 |
| 0.60 | 0.6550 | 0.7102 | 0.5830 | 0.1991 |
| 0.65 | 0.4977 | 0.7346 | 0.5599 | 0.1888 |
| 0.70 | 0.3649 | 0.7577 | 0.5342 | 0.1776 |
| 0.75 | 0.2394 | 0.8044 | 0.4773 | 0.1529 |
| 0.80 | 0.1409 | 0.8486 | 0.4094 | 0.1251 |

### ATP surface performance

| Surface | N | Accuracy | AUC | Log Loss | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|
| clay | 787 | 0.6341 | 0.7018 | 0.6244 | 0.2182 | 0.0348 |
| grass | 297 | 0.6734 | 0.7231 | 0.6112 | 0.2121 | 0.0406 |
| hard | 1777 | 0.6607 | 0.7169 | 0.6165 | 0.2144 | 0.0271 |

## WTA ablation ladder

| Model | Added component | Accuracy | AUC | Log Loss | Brier | ECE | Δ Log Loss | 95% block-bootstrap CI | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| M0 | leakage-safe rating/ranking baseline | 0.6488 | 0.7101 | 0.6211 | 0.2163 | 0.0082 | +0.0000 | — to — | KEEP_BASELINE |
| M1 | uncertainty-aware surface rating | 0.6488 | 0.7101 | 0.6211 | 0.2163 | 0.0082 | +0.0000 | 0.0 to 0.0 | DELETE |
| M2 | shrunk first/second serve and opponent-adjusted return | 0.6488 | 0.7101 | 0.6211 | 0.2163 | 0.0082 | +0.0000 | 0.0 to 0.0 | DELETE |
| M3 | multi-timescale residual state | 0.6541 | 0.7136 | 0.6184 | 0.2151 | 0.0058 | -0.0027 | -0.003884 to -0.001516 | KEEP |
| M4 | cached structural scoring expert | 0.6541 | 0.7136 | 0.6184 | 0.2151 | 0.0058 | +0.0000 | -0.0 to 0.0 | DELETE |
| M5 | dominance and workload | 0.6559 | 0.7170 | 0.6158 | 0.2140 | 0.0042 | -0.0026 | -0.003587 to -0.001694 | KEEP |
| M6 | H2H surprise and common-opponent residual | 0.6575 | 0.7162 | 0.6164 | 0.2143 | 0.0055 | +0.0006 | 0.000177 to 0.001231 | DELETE |
| M7 | simple temporal graph | 0.6575 | 0.7162 | 0.6164 | 0.2143 | 0.0055 | +0.0000 | 0.0 to 0.0 | DELETE |
| M8 | retained structural ensemble | 0.6575 | 0.7162 | 0.6164 | 0.2143 | 0.0055 | +0.0000 | 0.0 to 0.0 | DELETE |

### WTA confidence versus coverage

| Threshold | Coverage | Accuracy | Log Loss | Brier |
|---:|---:|---:|---:|---:|
| 0.55 | 0.8207 | 0.6909 | 0.5952 | 0.2038 |
| 0.60 | 0.6520 | 0.7211 | 0.5727 | 0.1933 |
| 0.65 | 0.4943 | 0.7519 | 0.5457 | 0.1809 |
| 0.70 | 0.3594 | 0.7871 | 0.5097 | 0.1644 |
| 0.75 | 0.2410 | 0.8228 | 0.4663 | 0.1450 |
| 0.80 | 0.1501 | 0.8394 | 0.4414 | 0.1341 |

### WTA surface performance

| Surface | N | Accuracy | AUC | Log Loss | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|
| clay | 553 | 0.6926 | 0.7580 | 0.5840 | 0.2000 | 0.0391 |
| grass | 295 | 0.6576 | 0.6887 | 0.6412 | 0.2248 | 0.0485 |
| hard | 1517 | 0.6486 | 0.7175 | 0.6179 | 0.2142 | 0.0367 |

## Scientific decisions

- ATP M1 uncertainty-aware ratings, M2 shrunk serve/return, M4 scoring expert, M5 dominance/workload, M6 common-opponent/H2H residuals, and M8 contextual residuals survived pre-2024 walk-forward evaluation. Naive additional multi-timescale form was deleted.
- WTA retained multi-timescale form and workload. Serve decomposition and point-process scoring were unavailable because the supplied WTA rows do not contain serve-point observations. H2H/common-opponent additions worsened development log loss and were deleted.
- A separate exact point→game→tiebreak→set→match engine and posterior Beta propagation passed symmetry, antisymmetry, bounds, temporal-purity, and reproducibility tests. It was not mislabeled as a data ablation: the cached candidate rows contain an older structural-score feature, and regenerating exact pre-match service posteriors remains necessary before empirical promotion testing.
- Simple temporal graph features were not available in the frozen feature rows. Therefore GNN, topology, sequence, and mixture-of-experts stages were not attempted.
- ATP's external log-loss improvement is small and Brier is 0.0002 worse than the stated production benchmark. WTA's paired 2025 CI versus M0 includes zero. Neither candidate meets the promotion gate.

## Limitations

Cold-start bins cannot be reconstructed exactly from the cached rows because only match-count differences—not each player's absolute pre-match history—were persisted. Point-level observations, exact match chronology, travel, altitude, duration, retirement flags, and WTA serve statistics are absent. These are recorded as unavailable rather than imputed.
