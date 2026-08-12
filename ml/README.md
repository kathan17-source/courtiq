# CourtIQ ML workspace

This folder contains reusable model-development modules used by the research and training scripts:

- `features/` — convert raw matches into model-ready rows
- `training/` — train Elo, logistic, gradient boosting and calibrated ensembles
- `evaluation/` — walk-forward backtests, calibration, log loss and Brier score

The deployed artifacts live in `output/models/`. Frontend performance numbers must match their held-out metadata and the authoritative research reports.
