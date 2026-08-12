# CourtIQ Current Architecture Audit

Updated: 2026-08-12

## 1. Current architecture

CourtIQ has a static single-page frontend, a FastAPI application layer, and reproducible model/research tooling:

```text
outputs/tennis-ai-app/
  index.html
  app.js
  styles.css
  assets/player-stats.js

backend/
  main.py
  app/api/
  app/services/

output/models/
  courtiq_model_atp.json
  courtiq_model_wta.json

work/
  backtest_courtiq_model.js
  fetch_tennis_data.js
  tennis-data/
```

The frontend is the primary product surface. It is a static single-page app with local persistence, training, analysis, learning, puzzles and ATP/WTA prediction flows.

The backend serves the frontend and API from one origin, loads separate validated ATP/WTA artifacts, and exposes prediction, health, player and video-analysis routes. PostgreSQL remains the target schema; the deployed service currently uses file-backed artifacts and browser-local product persistence.

## 2. What functionality is real

- Tennis scoring probability functions: game probability with deuce, match probability from set probability.
- Walk-forward backtest runner design: predicts each match before updating ratings.
- `player-stats.js` frontend data hook: allows real exported stats to replace demo fallback values.
- Same-tour match guard in the predictor.
- Versioned ATP/WTA prediction artifacts with schema and integrity validation.
- FastAPI prediction, model-health, player-search and video-analysis endpoints.
- Product-level UI flows for learning, training, prediction, gear, puzzles and analysis.

## 3. What is simulated/demo

- Video analysis is a single-camera 2D pose estimate, not ball tracking or clinical biomechanics.
- Plan/profile state is browser-local and is not synchronized to an account.
- Gear catalog assets are preserved for future product work but are not loaded by the current public navigation.

## 4. Technical debt

- `outputs/tennis-ai-app/app.js` is too large and should eventually split into modules/pages/services.
- No authenticated account or cloud persistence layer.
- The checked-in database schema does not yet have an application migration runner.
- Model artifacts are file-backed rather than managed through a model registry.
- In-process rate limiting is single-instance only.

## 5. Files that should be refactored later

- `outputs/tennis-ai-app/app.js`: split into frontend pages/services/components.
- `work/backtest_courtiq_model.js`: retain as a compatibility smoke tool; production training is Python-based.
- Preserved Gear catalog assets: move to external/object storage before reactivating that product area.

## 6. Next production steps

- Add authenticated accounts and server-side persistence where product requirements justify them.
- Add a database migration runner and transactional ingestion jobs.
- Move shared rate limiting and observability to managed infrastructure before multi-instance scaling.
- Introduce a governed artifact registry and automated freshness checks.
- Keep video claims bounded to what the 2D landmark pipeline actually measures.
