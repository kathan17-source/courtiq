# CourtIQ security boundaries

CourtIQ is an anonymous public portfolio application. It has no account cookies, privileged mutations, model-upload route, or active SQL connection. Report security concerns privately to the repository owner rather than including sensitive details in a public issue.

## Public API surface

All request models reject unknown fields. Non-upload bodies are capped at 2 MiB; multipart video bodies are capped at 80 MiB and streamed in 1 MiB chunks. API responses use `Cache-Control: no-store`.

| Route | Input boundary | Cost / protection |
|---|---|---|
| `GET /api/health` | No input | Lightweight model-load flags only |
| `GET /api/model/version` | No input | Read-only artifact metadata |
| `GET /api/model/metrics` | No input | Read-only held-out metrics |
| `GET /api/players/search` | Query ≤80 chars; ATP/WTA enum; limit 1–100; offset 0–10,000 | In-memory bounded search |
| `GET /api/players/{id}` and `/ratings`, `/form` | ID 2–120 chars | In-memory lookup |
| `GET /api/head-to-head` | Two names, each 2–80 chars | Placeholder, no database work |
| `POST /api/predict` | Names 2–80 chars; event 2–120; ATP/WTA, surface and best-of enums; strict schema | 60 requests/minute/client plus global limit |
| `POST /api/simulate/tournament` | 2–128 unique players; power-of-two draw; 1–10,000 simulations; bounded seed; strict schema | Pair probabilities reused; worker thread; 20 requests/minute/client |
| `POST /api/video/validate-upload` | Supported extension, MIME, signature, decodable metadata, byte/duration/frame/FPS/pixel bounds | Streamed temporary file; worker probe; 10 requests/minute/client |
| `POST /api/video/analyze` | Same upload controls | Bounded sampled pose analysis in worker thread; 5 requests/minute/client |

## Deployment assumptions

- The browser and API are same-origin. Production CORS has no wildcard and does not require a cross-origin allowlist.
- Uvicorn/Render supplies `request.client`; CourtIQ does not independently trust arbitrary application headers as identity. A shared proxy-aware limiter is still required before multi-instance scaling.
- Uploaded videos live only in UUID-named temporary directories and are removed on success and handled failures. They are never exposed as static files.
- ATP/WTA artifacts are schema-validated JSON. Public routes cannot upload, replace, or reload them.
- The checked-in PostgreSQL schema is not connected to the active deployment, so SQL injection is not an active runtime surface.
- Classic authenticated CSRF is not applicable because CourtIQ has no cookie-authenticated state-changing operation.
- Profile, plan, and analysis history are device-local browser state, not an authenticated account or cloud record.

## Accepted limitations

- Rate limiting is in process and resets on restart. It is suitable for the current single-instance deployment, not distributed enforcement.
- Native video decoding and pose inference are bounded by input metadata and sampled frames, but Python threads cannot forcibly terminate a stuck native decoder. A process-isolated media worker is recommended before accepting sustained untrusted upload traffic.
- Inline style attributes are used for bounded visualization percentages, requiring `style-src 'unsafe-inline'`. Scripts remain self-hosted and CSP does not permit `unsafe-eval` or inline script execution.
