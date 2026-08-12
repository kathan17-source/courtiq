# Legacy ATP baseline

**RETIRED / INVALID — temporal leakage made this result unusable.**

The removed `courtiq_logistic_baseline.json` reported approximately 70.05% accuracy and 0.7703 ROC-AUC. Same-tournament ordering leaked future information into its evaluation, so those values are not valid production or research benchmarks.

The authoritative production metrics are the leakage-safe chronological ATP/WTA values documented in the root README and the TENSOR v3 research report. The retired binary-sized JSON artifact is preserved only in the local, Git-ignored archive `.local-archives/courtiq-retired-model-candidates-2026-08-12.tar.gz`.
