# Deploying CourtIQ

CourtIQ deploys as one FastAPI service. The same process serves the existing frontend and the `/api` routes. The production entry point is:

```text
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

## A. Render

1. Push this repository to a Git provider supported by Render.
2. In Render, choose **New → Blueprint** and select the repository. Render reads `render.yaml` and builds the root `Dockerfile`.
3. Set `COURTIQ_CORS_ORIGINS` to the final HTTPS origin, for example `https://courtiq.onrender.com`. Same-origin browser requests do not require CORS, so leaving it empty is also safe until a separate frontend exists.
4. Create the service. Wait for `/api/health` to report `status: ok` with both model flags true.
5. Open the service URL. Hash routes such as `/#train/plan` are handled by the existing frontend.

Use a plan with at least 1 GB RAM if Analyze will be used by more than one person at a time. Render's ephemeral filesystem is appropriate because CourtIQ deletes temporary uploads and does not depend on persistent local files.

## B. Docker locally

```bash
docker build -t courtiq .
docker run --rm -p 8000:8000 -e PORT=8000 -e COURTIQ_ENV=production courtiq
```

Then open `http://127.0.0.1:8000/` and check `http://127.0.0.1:8000/api/health`.

## C. Custom domain

Add the domain in the hosting platform, create the DNS record it provides, and wait for HTTPS issuance. Set `COURTIQ_CORS_ORIGINS` to the exact origin, such as `https://courtiq.app`. CourtIQ uses same-origin relative API behavior and does not embed the temporary host name.

## D. Environment variables

| Variable | Production purpose | Default |
|---|---|---|
| `PORT` | Host-provided listening port | `8000` |
| `COURTIQ_ENV` | Enables production security headers | `development` outside Docker |
| `COURTIQ_CORS_ORIGINS` | Comma-separated explicit browser origins | localhost only in development; empty in production |
| `COURTIQ_MODEL_ARTIFACT` | ATP artifact path; WTA is resolved beside it | `output/models/courtiq_model_atp.json` |
| `COURTIQ_ALLOW_DEMO` | Must remain false for public use | `false` |
| `COURTIQ_REQUEST_BODY_LIMIT_BYTES` | Non-upload request cap | `2097152` |
| `COURTIQ_UPLOAD_LIMIT_BYTES` | Video upload cap | `83886080` |
| `COURTIQ_VIDEO_MAX_DURATION_SECONDS` | Video duration cap | `30` |
| `COURTIQ_VIDEO_MAX_PIXELS` | Width × height cap | `8294400` |
| `COURTIQ_VIDEO_MAX_FRAMES` | Decoded frame-count cap | `1800` |
| `COURTIQ_VIDEO_MAX_FPS` | Frame-rate cap | `120` |
| `COURTIQ_MAX_SIMULATIONS` | Public tournament simulation cap, never above 10,000 | `10000` |
| `COURTIQ_RATE_LIMIT_PER_MINUTE` | Per-process client request cap | `120` |
| `COURTIQ_LOG_LEVEL` | Server log level | `INFO` |

Aliases `ENVIRONMENT`, `ALLOWED_ORIGINS`, `MAX_UPLOAD_BYTES`, `MAX_VIDEO_DURATION`, `MAX_VIDEO_PIXELS`, `MAX_VIDEO_FRAMES`, and `MAX_SIMULATIONS` are accepted when a platform uses generic names. No secrets are required by the current application.

## E. Health checks

Use `GET /api/health`. A healthy deployment returns HTTP 200 and includes `atp_model_loaded: true` and `wta_model_loaded: true`. Render and Docker are configured to use this endpoint.

## F. Troubleshooting

- If health reports a missing model, verify both production JSON artifacts were included and `COURTIQ_MODEL_ARTIFACT` points to the ATP file.
- If the frontend loads but predictions fail, inspect `/api/health` first and confirm the browser is using the same HTTPS origin.
- If Analyze fails during startup, confirm the Docker build installed `libglib2.0-0`, `libgl1`, and `libgomp1`, and allocate more memory.
- If uploads receive HTTP 413/400, compare the clip with the byte, duration, resolution, frame, and FPS limits.
- If a separate frontend calls this API, add only that exact HTTPS origin to `COURTIQ_CORS_ORIGINS`; do not use `*`.
- If Render's first request is slow after an idle period, use an always-on instance for reliable demonstrations.

Railway, Fly.io, and a VPS can use the same root Dockerfile and inject `PORT` plus the environment values above.
