# CourtIQ Current Architecture Audit

Date: 2026-08-09

## 1. Current architecture

CourtIQ currently has two layers:

```text
outputs/tennis-ai-app/
  index.html
  app.js
  styles.css
  assets/player-stats.js

backend/
  main.py
  services/

work/
  backtest_courtiq_model.js
  fetch_tennis_data.js
  tennis-data/
```

The frontend is still the primary product surface. It is a static single-page app with a polished tennis UI, multiple pages, local storage, match predictor, puzzles, gear, training, compete and analysis flows.

The backend is an early scaffold. It contains the first real split of prediction services, Elo math and video-analysis math helpers, but it is not yet connected to a database or deployed as the source of truth.

## 2. What functionality is real

- Tennis scoring probability functions: game probability with deuce, match probability from set probability.
- Walk-forward backtest runner design: predicts each match before updating ratings.
- `player-stats.js` frontend data hook: allows real exported stats to replace demo fallback values.
- Same-tour match guard in the predictor.
- Basic backend API contract scaffold.
- Product-level UI flows for learning, training, prediction, gear, puzzles and analysis.

## 3. What is simulated/demo

- Frontend player skill profiles when no `player-stats.js` data exists.
- Video analysis report: currently a heuristic coaching report, not real computer vision.
- Tournament discovery: links/placeholders, not a complete global event database.
- Gear catalog/images: large product-like catalog, but exact verified product image coverage is incomplete.
- Chatbot behavior: not connected to a true tennis knowledge backend.

## 4. Technical debt

- `outputs/tennis-ai-app/app.js` is too large and should eventually split into modules/pages/services.
- No persistent database yet.
- No migrations yet.
- No live API integration from frontend predictor yet.
- No rigorous Python test suite before this phase.
- No CI/Docker setup before this phase.
- No model artifact/version registry yet.

## 5. Files that should be refactored later

- `outputs/tennis-ai-app/app.js`: split into frontend pages/services/components.
- `work/backtest_courtiq_model.js`: keep as smoke-tool, but move production modeling to Python `ml/`.
- `backend/services/*`: migrate to `backend/app/services/*` package.
- Gear data inside `app.js`: eventually move into database/imported catalog.

## 6. Migration plan

### Phase 1 — foundation

- Preserve static frontend.
- Add `backend/app` FastAPI architecture.
- Add PostgreSQL schema.
- Add tests for math/Elo/API contracts.
- Add Docker/CI scaffolding.

### Phase 2 — data

- Import ATP/WTA CSV data using reproducible scripts.
- Normalize players/tournaments/matches/stat rows.
- Persist chronological Elo snapshots.

### Phase 3 — models

- Build feature pipeline with no future leakage.
- Add ranking-only, overall Elo, surface Elo and logistic regression baselines.
- Add walk-forward evaluation and calibration reports.

### Phase 4 — integration

- Connect frontend predictor to backend API.
- Display real stats only when backend confirms data exists.

### Phase 5+

- Add tournament simulation, real CV video pipeline, deployment hardening.

