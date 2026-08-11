# CourtIQ demo guide

This is the interview/recruiter demo path. It is intentionally short and honest: this checkout has the full app, backend scaffold, probability math, schema, validation and benchmark scripts, but no imported historical ATP/WTA CSV dataset yet. If match CSVs are added to `work/tennis-data`, the backtest script populates real backtest metrics and frontend player stats.

## 60-second recruiter demo

1. Open `outputs/tennis-ai-app/index.html`.
2. Explain the product in one sentence: “CourtIQ is a tennis analytics platform that combines match prediction, player development, video-analysis UX and gear recommendations.”
3. Go to **Match Predictor**.
4. Select two same-tour players and a Grand Slam.
5. Run the prediction.
6. Point out the honesty boundary: demo predictions are labelled; the backend refuses unvalidated predictions unless demo mode is explicitly enabled.
7. Open the repo files:
   - `backend/app/services/elo_service.py` for surface-aware Elo.
   - `backend/app/services/tennis_math.py` for game/set/match probability.
   - `work/backtest_courtiq_model.js` for chronological backtesting once CSVs are present.
8. Show `output/backtests/courtiq_backtest_report.json`. In this checkout it says `no_data`, which is intentional rather than faking accuracy.
9. Show `output/benchmarks/core_benchmarks.json` and `output/benchmarks/simulation_benchmark.json` for measured local performance.
10. If asked for a tournament simulation, show the measured `tournament_simulation_10k_brackets` benchmark in `core_benchmarks.json`; the current UI does not yet expose this as a full production endpoint.

## 3-minute technical interview demo

### 0:00–0:20 — Problem

Tennis players and fans get scattered advice, generic stats and vague prediction claims. CourtIQ turns match history, player strength, scoring math and video-derived movement signals into one explainable tennis platform.

### 0:20–0:50 — Architecture

Historical CSV data flows into an import/backtest pipeline, then into PostgreSQL tables for players, tournaments, matches, point events, Elo snapshots, model versions and backtests. The FastAPI backend exposes prediction, player and model metadata endpoints. The static frontend demonstrates the product experience.

### 0:50–1:20 — Real data pipeline

The repo expects public ATP/WTA-style match CSVs in `work/tennis-data`. The backtest script processes files named like `atp_matches_2025.csv` and `wta_matches_2025.csv`. The current local checkout has no CSVs, so the generated report correctly says `no_data`.

### 1:20–1:50 — Elo methodology

CourtIQ updates ratings chronologically. A player’s expected score is:

```text
E_A = 1 / (1 + 10^((R_B - R_A)/400))
```

The implementation tracks overall Elo and surface Elo for hard, clay and grass. Ratings are updated only after each evaluated match, which prevents future data from leaking into pre-match predictions.

### 1:50–2:15 — Match prediction and evaluation

The prediction math blends Elo prior, surface rating, hold probability and tennis scoring conversion. Real accuracy is not claimed unless a chronological backtest has run. Evaluation is designed around accuracy, Brier score, log loss and calibration rather than accuracy alone.

### 2:15–2:35 — Tournament simulation

The Monte Carlo path is deterministic with a seed. Local benchmarks show 100,000 match simulations in roughly 96 ms and 10,000 lightweight bracket simulations in roughly 203 ms on this machine.

### 2:35–2:50 — Computer vision

The implemented CV piece is biomechanical helper math for joint angles plus a video-upload UX and safe upload validation. Full ball tracking/RPM is intentionally not claimed.

### 2:50–3:00 — Engineering decisions

The project is structured to be defensible: strict API schemas, standard error responses, request IDs, upload validation, PostgreSQL constraints, CI, Docker Compose, no fake metrics, and explicit known limitations.
