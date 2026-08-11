from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from uuid import uuid4

from backend.app.config import Settings


class SecurityValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SafeUpload:
    safe_filename: str
    extension: str
    content_type: str
    size_bytes: int


class RequestLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        bucket = self._events[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


def make_request_id() -> str:
    return uuid4().hex[:16]


def safe_video_filename(original_filename: str, settings: Settings) -> str:
    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in settings.allowed_video_extensions:
        raise SecurityValidationError("unsupported_extension", "Unsupported video extension.")
    return f"{uuid4().hex}{suffix}"


def validate_video_upload_metadata(
    *,
    original_filename: str,
    content_type: str | None,
    size_bytes: int,
    settings: Settings,
) -> SafeUpload:
    content_type = (content_type or "").split(";")[0].strip().lower()
    if content_type not in settings.allowed_video_mime_types:
        raise SecurityValidationError("unsupported_mime_type", "Unsupported video type.")
    if size_bytes <= 0:
        raise SecurityValidationError("empty_upload", "Uploaded video is empty.")
    if size_bytes > settings.upload_limit_bytes:
        raise SecurityValidationError("upload_too_large", "Uploaded video is too large.")
    safe_name = safe_video_filename(original_filename, settings)
    return SafeUpload(
        safe_filename=safe_name,
        extension=Path(safe_name).suffix,
        content_type=content_type,
        size_bytes=size_bytes,
    )
