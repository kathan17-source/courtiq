# CourtIQ Backend

The production-facing API now lives under `backend/app`.

## Entry points

- `backend.main:app` — compatibility entry point
- `backend.app.main:app` — direct app entry point

## API routes

- `GET /health`
- `GET /api/model/version`
- `GET /api/model/metrics`
- `GET /api/players/search`
- `POST /api/predict`
- `GET /api/head-to-head`
- `POST /api/video/validate-upload`
- `POST /api/video/analyze`
- `POST /api/simulate/tournament`

## Database

PostgreSQL schema:

```text
backend/database/schema.sql
```

The schema is designed for real player rosters, match results, point/match statistics, model versions, predictions, backtests and video-analysis jobs.

## Model inference

Production prediction loads the checked-in, separately validated ATP and WTA artifacts. It uses their chronological ratings and model coefficients; it does not use placeholder ratings. `COURTIQ_ALLOW_DEMO` remains disabled in production.

PostgreSQL is a documented future persistence target, not a dependency of the currently deployed inference path.
