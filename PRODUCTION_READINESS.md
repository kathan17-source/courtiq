# CourtIQ production-readiness report

Updated: 2026-08-12

## Verdict

CourtIQ is publicly deployed as a controlled prototype. It loads versioned ATP and WTA artifacts and exposes their held-out metrics, but it has no authenticated account system, shared persistence, production database, distributed rate limit or isolated media worker.

## Architecture summary

- Frontend: static HTML/CSS/JavaScript app in `outputs/tennis-ai-app`.
- API: FastAPI app in `backend/app`, exposed through `backend.main:app`.
- Database target: PostgreSQL with normalized players, tournaments, matches, point events, Elo history, model versions, model backtests and upload-job lifecycle tables.
- ML target: chronological surface-Elo and tennis scoring math. Demo predictions are disabled by default unless explicitly requested.
- Data import: CSV-oriented import/backtest path under `work/tennis-data` and `work/backtest_courtiq_model.js`.
- Deployment: Docker-based Render service with GitHub Actions CI.

## Security decisions added

| Area | Decision |
|---|---|
| Error handling | API errors now return a consistent JSON envelope with `error.code`, `error.message` and `request_id`. Stack traces are not returned to users. |
| Request IDs | Every API request gets an `x-request-id` response header for traceability. |
| Rate limiting | Added simple in-process per-client rate limiting. This is enough for a single-node prototype; production should move it to a proxy or shared cache. |
| Request limits | Configurable request and upload byte limits are exposed through environment variables. |
| CORS | CORS origins are explicit and configured by `COURTIQ_CORS_ORIGINS`. Wildcard CORS is avoided. |
| Security headers | Added `nosniff`, `DENY` frame policy, no-referrer policy, permissions policy and HSTS outside development. |
| Upload filenames | Original filenames are never trusted. Video uploads receive UUID-based server filenames. |
| Upload validation | Video uploads validate MIME type, extension, size and supported container signature before decoding. Unsupported formats fail safely. |
| Temp cleanup | Uploads stream to UUID-named temporary files and are deleted on success and error paths. Production should still isolate media work in a bounded worker. |
| SQL safety | Current code does not build raw SQL from user input. The schema now includes constraints and indexes for upload-job lifecycle cleanup. |
| Secrets | Variable names are documented in the README and deployment guide. Values belong only in Render and environment files are never committed. |

## Production audit fixes

| Issue | Severity | Fix |
|---|---:|---|
| API had no standardized error response | 8 | Added exception handlers for HTTP, validation and unhandled failures. |
| No request IDs for debugging failures | 7 | Added request ID middleware and response header. |
| Video upload validation was underspecified | 9 | Added MIME, extension, size and safe-name validation helper plus endpoint. |
| Request body/rate limits were missing | 8 | Added configurable body/upload limits and in-process rate limiting. |
| Prediction schema allowed invalid `best_of=4` | 6 | Added strict schema validator for best-of-3/best-of-5 only. |
| Upload job table allowed arbitrary status strings | 6 | Added database status constraint and cleanup indexes. |
| Backtest report wrote machine-specific absolute paths | 4 | Changed output paths to repository-relative paths. |
| Monte Carlo performance was not measured | 6 | Added deterministic benchmark script and saved results. |
| CI did not cover new upload/security helpers | 5 | Added upload-security and simulation reproducibility tests. |
| Demo predictions could appear too real | 8 | Backend continues to reject unvalidated predictions unless demo is explicitly enabled. |

## API reliability behavior

- Invalid player/tour/best-of inputs are rejected by strict schemas or explicit endpoint checks.
- Missing real model data returns `503` for prediction unless `allow_demo=true`.
- Validation errors avoid leaking framework details.
- Uploads that are empty, too large, wrong MIME type, wrong extension or path-like filenames are rejected.
- The API logs method, path, status code, latency and request ID.

## Video-processing limits

Current backend upload validation supports:

- Allowed extensions: `.mp4`, `.mov`, `.m4v`, `.webm`
- Allowed MIME types: `video/mp4`, `video/quicktime`, `video/x-m4v`, `video/webm`
- Default upload cap: 80 MB
- Chunked reading: 1 MB chunks
- Safe UUID filename generation

Production requirement before real user uploads:

- Move full video analysis to a background worker.
- Add antivirus or media probing in an isolated process.
- Use a temp directory outside the web root.
- Enforce TTL deletion even if processing fails.
- Add worker-level CPU and memory limits.

## Database readiness

Existing useful indexes:

- `idx_matches_date`
- `idx_matches_players`
- `idx_matches_surface`
- `idx_point_events_match`
- `idx_point_events_server`
- `idx_elo_player_date`
- `idx_uploaded_jobs_status_created`
- `idx_uploaded_jobs_expires_at`

Constraints now cover:

- ATP/WTA tour values
- Surface enumerations
- Best-of values
- Point uniqueness within a match
- Player aliases
- Upload-job lifecycle states

Remaining database work:

- Add real migration runner such as Alembic.
- Add transaction-wrapped import jobs.
- Add upsert conflict handling for public tennis CSV imports.
- Add query benchmarks against a populated PostgreSQL database.

## ML inference readiness

Current model state:

- Separate checked-in ATP and WTA artifacts load at startup and are validated for schema, dimensions, finite parameters, calibration and tour consistency.
- Training/evaluation/state cutoffs are returned with prediction diagnostics so freshness is visible.
- ATP 2025 held-out metrics are accuracy 0.655, log loss 0.6185, Brier 0.2154 and ROC-AUC 0.7132; WTA metrics are 0.6469, 0.6232, 0.2172 and 0.7069.
- Unknown event names require an explicit surface; they do not silently default to hard court.
- Current-state artifacts cannot reconstruct a genuinely historical player snapshot for arbitrary `as_of` dates.

Requirements for future model releases:

- Preserve separate versioned ATP/WTA artifact validation at startup.
- Reject stale or incompatible artifacts.
- Store feature-version metadata with predictions.
- Run chronological walk-forward evaluation only.
- Report accuracy, log loss, Brier score, ROC-AUC and calibration from saved backtest rows.

## Monte Carlo validation

Benchmark command:

```bash
python3 scripts/benchmark_simulation.py
```

Results are intentionally not checked in as machine-independent performance claims. Public requests are bounded at 10,000 simulations. Tournament requests are bounded to 128 players and precompute each pair once.

## Observability

Added or documented:

- Request latency
- Prediction latency
- Simulation latency
- Video validation duration
- Error responses with request IDs
- Structured logging fields

Still needed for real deployment:

- OpenTelemetry or hosted log/metric export
- Error-rate dashboards
- Upload failure dashboard
- Model-failure alerts
- Database failure alerts

## Stress-test summary

Local checks run:

- Canonical test command: `.venv/bin/python -m pytest -q`; the project virtual environment includes the API test dependencies.
- Python compile check: passed.
- JavaScript syntax check: passed.
- No-data backtest path: passed and writes an honest `no_data` report.
- Monte Carlo benchmark: 100K simulations completed in roughly 100 ms.
- Upload/rate-limit stress helper: 5,000 malformed upload metadata attempts rejected, 0 unexpected accepts, 150 rapid requests limited to 120 allowed / 30 rejected in 2.85 ms.

Browser flows must be exercised against the supported local HTTP server, never the `file://` page.

## Known risks

- No real production auth system exists yet; the current app behaves like a private prototype.
- Artifacts are file-backed rather than served from a governed model registry.
- The static frontend is not a hardened production SPA.
- In-process rate limiting resets on process restart and does not work across multiple replicas.
- Upload validation includes metadata, container signatures and bounded probing; full antivirus/transcoding isolation is not implemented.
- No verified live schedule feed is currently connected.
- CI installs backend dependencies, but this local workstation does not have all optional Python packages installed globally.

## Deployment assumptions

- Run behind HTTPS.
- Use a managed PostgreSQL instance with backups.
- Configure CORS to the exact production domain.
- Keep `COURTIQ_ALLOW_DEMO=false` in production.
- Put upload processing behind a worker if videos are stored or analyzed server-side.
- Store secrets in environment/secret manager only.

## Final answer to “Would this survive real users?”

For a controlled public prototype, yes: HTTPS deployment, explicit same-origin CORS, validated ATP/WTA artifacts, bounded inputs, CI and live browser QA are active. A broader multi-user service would still need authentication where accounts are introduced, production observability, shared persistence/rate limiting, migrations and isolated video processing.
