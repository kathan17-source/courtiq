from __future__ import annotations

from collections import deque
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
    def __init__(self, limit: int, window_seconds: int = 60, max_keys: int = 10_000) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        stale = [key for key, bucket in self._events.items() if not bucket or bucket[-1] < cutoff]
        for key in stale:
            self._events.pop(key, None)
        if len(self._events) >= self.max_keys:
            oldest = min(self._events, key=lambda key: self._events[key][-1])
            self._events.pop(oldest, None)

    def allow(self, key: str) -> bool:
        now = monotonic()
        if key not in self._events:
            self._prune(now)
        bucket = self._events.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True


def make_request_id() -> str:
    return uuid4().hex[:16]


def safe_request_id(candidate: str | None) -> str:
    if candidate and 1 <= len(candidate) <= 64 and all(character.isalnum() or character in "-_" for character in candidate):
        return candidate
    return make_request_id()


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


def validate_video_signature(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(16)
    valid = False
    if extension in {".mp4", ".mov", ".m4v"}:
        valid = len(header) >= 12 and header[4:8] == b"ftyp"
    elif extension == ".webm":
        valid = header.startswith(b"\x1aE\xdf\xa3")
    if not valid:
        raise SecurityValidationError("invalid_video_signature", "Uploaded content is not a supported video container.")
