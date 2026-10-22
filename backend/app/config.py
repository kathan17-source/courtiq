from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from os import getenv
from pathlib import Path


def _env(primary: str, fallback: str, default: str) -> str:
    return getenv(primary) or getenv(fallback) or default


def _cors_origins() -> tuple[str, ...]:
    environment = _env("COURTIQ_ENV", "ENVIRONMENT", "development").lower()
    default = "http://localhost:5173,http://localhost:8000,http://127.0.0.1:8000" if environment == "development" else ""
    value = _env("COURTIQ_CORS_ORIGINS", "ALLOWED_ORIGINS", default)
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = "CourtIQ Match Engine"
    environment: str = _env("COURTIQ_ENV", "ENVIRONMENT", "development")
    model_version: str = getenv("COURTIQ_MODEL_VERSION", "courtiq-v2-surface-elo")
    model_artifact_path: Path = Path(getenv("COURTIQ_MODEL_ARTIFACT", "output/models/courtiq_model_atp.json"))
    allow_demo_predictions: bool = getenv("COURTIQ_ALLOW_DEMO", "false").lower() == "true"
    cors_origins: tuple[str, ...] = field(default_factory=_cors_origins)
    request_body_limit_bytes: int = int(getenv("COURTIQ_REQUEST_BODY_LIMIT_BYTES", str(2 * 1024 * 1024)))
    upload_limit_bytes: int = int(_env("COURTIQ_UPLOAD_LIMIT_BYTES", "MAX_UPLOAD_BYTES", str(80 * 1024 * 1024)))
    video_max_duration_seconds: float = float(_env("COURTIQ_VIDEO_MAX_DURATION_SECONDS", "MAX_VIDEO_DURATION", "30"))
    video_max_pixels: int = int(_env("COURTIQ_VIDEO_MAX_PIXELS", "MAX_VIDEO_PIXELS", str(3840 * 2160)))
    video_max_frames: int = int(_env("COURTIQ_VIDEO_MAX_FRAMES", "MAX_VIDEO_FRAMES", "1800"))
    video_max_fps: float = float(getenv("COURTIQ_VIDEO_MAX_FPS", "120"))
    rate_limit_per_minute: int = int(getenv("COURTIQ_RATE_LIMIT_PER_MINUTE", "120"))
    max_simulations: int = min(10_000, max(1, int(_env("COURTIQ_MAX_SIMULATIONS", "MAX_SIMULATIONS", "10000"))))
    allowed_video_extensions: tuple[str, ...] = (".mp4", ".mov", ".m4v", ".webm")
    allowed_video_mime_types: tuple[str, ...] = ("video/mp4", "video/quicktime", "video/x-m4v", "video/webm")
    log_level: str = getenv("COURTIQ_LOG_LEVEL", "INFO")
    gemini_api_key: str = getenv("GEMINI_API_KEY", "")
    gemini_model: str = getenv("COURTIQ_GEMINI_MODEL", "gemini-3.5-flash")
    gemini_timeout_seconds: float = min(30.0, max(2.0, float(getenv("COURTIQ_GEMINI_TIMEOUT_SECONDS", "12"))))


@lru_cache
def get_settings() -> Settings:
    return Settings()
