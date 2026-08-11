# CourtIQ deployment runtime files

The public application is a single FastAPI process serving both `/api/*` and the existing static frontend. The Dockerfile copies only the following runtime material.

## Required application code

- `backend/__init__.py`, `backend/main.py`, and `backend/app/**`: FastAPI entry point, schemas, middleware, prediction/simulation services, and OpenCV/MediaPipe analysis.
- `requirements.txt`: authoritative production-only Python dependencies.

## Required production artifacts

- `output/models/courtiq_model_atp.json`: active ATP model and player snapshots.
- `output/models/courtiq_model_wta.json`: active WTA model and player snapshots.

The candidate artifacts, generic legacy model, baseline artifact, research reports, reproducibility tables, and historical match datasets are not read by the live service.

## Required frontend files

- `outputs/tennis-ai-app/index.html`
- `outputs/tennis-ai-app/app.js`
- `outputs/tennis-ai-app/styles.css`
- `outputs/tennis-ai-app/js/api.js`
- `outputs/tennis-ai-app/js/router.js`
- `outputs/tennis-ai-app/js/storage.js`
- `outputs/tennis-ai-app/assets/player-stats.js`

The hidden Gear catalog and its product images are preserved in the development repository but are not loaded by the current UI and are excluded from deployment.

## Runtime behavior and storage

- Uploaded videos stream into an operating-system temporary directory, are bounded before analysis, and are removed when each request finishes or fails.
- No database is required by the current live paths. Profiles and generated plans remain device-local browser data.
- The process needs a writable system temporary directory, but no persistent filesystem volume.
- `/api/health` reports service status and ATP/WTA artifact availability without filesystem paths.

## Packaging estimate

The application source and live artifacts are approximately 7.5 MB before Python dependencies. The Python image layer is materially larger because OpenCV and MediaPipe include native libraries. Budget roughly 450–700 MB for the compressed/uncompressed container layers and at least 512 MB RAM; 1 GB RAM is safer for concurrent pose-analysis requests.
