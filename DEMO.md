# CourtIQ demo guide

This is a concise walkthrough of the public product and its technical foundations. The checked-in app includes separate validated ATP and WTA model artifacts, an API, a static frontend, training workflows, video-analysis support, tests, and reproducible research scripts.

## 60-second product walkthrough

1. Open https://courtiq-77cz.onrender.com/ or run `python scripts/run_courtiq.py` and open `http://127.0.0.1:8000`.
2. Explain the product in one sentence: “CourtIQ is a tennis analytics platform that combines ATP/WTA match prediction, player development and 2D pose-based movement analysis.”
3. Go to **Match Predictor**.
4. Select two same-tour players and a Grand Slam.
5. Run the prediction.
6. Open the model view and point out that metrics come from the active held-out artifacts rather than a marketing estimate.
7. For implementation details, see:
   - `backend/app/services/elo_service.py` for surface-aware Elo.
   - `backend/app/services/tennis_math.py` for game/set/match probability.
   - `scripts/train_models.py` for the reproducible ATP/WTA training entry point.
8. Review the active artifacts in `output/models/`, including their explicit training cutoffs and held-out metrics.
9. Open **Simulation**, run an eight-player tournament, and explain that the displayed champion probabilities come from the production simulation endpoint.
10. Use the benchmark scripts only for machine-local engineering checks; the repository does not publish their output as a production latency guarantee.

## 3-minute technical walkthrough

### 0:00–0:20 — Problem

Tennis players and fans get scattered advice, generic stats and vague prediction claims. CourtIQ turns match history, player strength, scoring math and video-derived movement signals into one explainable tennis platform.

### 0:20–0:50 — Architecture

Historical CSV data flows into an import/backtest pipeline, then into PostgreSQL tables for players, tournaments, matches, point events, Elo snapshots, model versions and backtests. The FastAPI backend exposes prediction, player and model metadata endpoints. The static frontend demonstrates the product experience.

### 0:50–1:20 — Real data pipeline

The repo expects public ATP/WTA-style match CSVs in `work/tennis-data`. ATP and WTA are trained independently, with separate rating populations and versioned artifacts. Raw source data stays out of Git; the current production artifacts and their evaluation metadata are checked in.

### 1:20–1:50 — Elo methodology

CourtIQ updates ratings chronologically. A player’s expected score is:

```text
E_A = 1 / (1 + 10^((R_B - R_A)/400))
```

The implementation tracks overall Elo and surface Elo for hard, clay and grass. Ratings are updated only after each evaluated match, which prevents future data from leaking into pre-match predictions.

### 1:50–2:15 — Match prediction and evaluation

The prediction math blends Elo prior, surface rating, hold probability and tennis scoring conversion. Real accuracy is not claimed unless a chronological backtest has run. Evaluation is designed around accuracy, Brier score, log loss and calibration rather than accuracy alone.

### 2:15–2:35 — Tournament simulation

The Monte Carlo path is deterministic with a seed. The public UI submits a bounded draw to the production simulation endpoint and displays only its returned probabilities.

### 2:35–2:50 — Computer vision

The implemented CV piece is biomechanical helper math for joint angles plus a video-upload UX and safe upload validation. Full ball tracking/RPM is intentionally not claimed.

### 2:50–3:00 — Engineering decisions

The project is structured to be defensible: strict API schemas, standard error responses, request IDs, upload validation, PostgreSQL constraints, CI, Docker Compose, no fake metrics, and explicit known limitations.
