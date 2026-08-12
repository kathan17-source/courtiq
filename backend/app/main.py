from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.app.api.routes import router
from backend.app.config import get_settings
from backend.app.middleware import ProductionGuardMiddleware

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    description="CourtIQ tennis analytics API: players, ratings, prediction and model metadata.",
    docs_url=None if settings.environment != "development" else "/docs",
    redoc_url=None if settings.environment != "development" else "/redoc",
    openapi_url=None if settings.environment != "development" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type", "x-request-id"],
)
app.add_middleware(ProductionGuardMiddleware, settings=settings)
app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "outputs" / "tennis-ai-app"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"


PUBLIC_FRONTEND_FILES = {"app.js", "styles.css", "favicon.svg", "robots.txt"}


def frontend_file_response(path: str = "") -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="CourtIQ frontend build not found.")
    normalized = path.strip("/")
    if normalized and normalized not in PUBLIC_FRONTEND_FILES and not normalized.startswith(("js/", "assets/")):
        raise HTTPException(status_code=404, detail="Resource not found.")
    requested = (FRONTEND_DIR / normalized).resolve()
    frontend_root = FRONTEND_DIR.resolve()
    if requested.is_file() and requested.is_relative_to(frontend_root):
        return FileResponse(requested)
    if not normalized:
        return FileResponse(FRONTEND_INDEX)
    raise HTTPException(status_code=404, detail="Resource not found.")


@app.get("/", include_in_schema=False)
def frontend_root() -> FileResponse:
    return frontend_file_response()


@app.get("/{path:path}", include_in_schema=False)
def frontend_spa(path: str) -> FileResponse:
    return frontend_file_response(path)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "untracked")
    detail = exc.detail if isinstance(exc.detail, str) else "Request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": detail}, "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "untracked")
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "validation_error", "message": "Invalid request payload."}, "request_id": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "untracked")
    logging.getLogger("courtiq.api").exception("unhandled request failure", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Unexpected server error."}, "request_id": request_id},
    )
