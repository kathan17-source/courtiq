# CourtIQ Backend

The production-facing API now lives under `backend/app`.

## Entry points

- `backend.main:app` — compatibility entry point
- `backend.app.main:app` — direct app entry point

## API routes

- `GET /health`
- `GET /api/model/version`
- `GET /api/model/metrics`
- `GET /api/observability/health`
- `GET /api/players/search`
- `POST /api/predict`
- `GET /api/head-to-head`
- `POST /api/video/validate-upload`
- `GET /api/simulate/benchmark`

## Database

PostgreSQL schema:

```text
backend/database/schema.sql
```

The schema is designed for real player rosters, match results, point/match statistics, model versions, predictions, backtests and video-analysis jobs.

## Next integration step

Connect `prediction_service.py` to database-backed player ratings and historical features instead of placeholder ratings.

Keep `COURTIQ_ALLOW_DEMO=false` outside local demos.
