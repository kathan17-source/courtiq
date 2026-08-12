from __future__ import annotations

import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.config import Settings
from backend.app.services.security import RequestLimiter, safe_request_id

LOGGER = logging.getLogger("courtiq.api")


def error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
    )


class ProductionGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = settings
        self.limiter = RequestLimiter(settings.rate_limit_per_minute)
        self.expensive_limiters = {
            "/api/video/validate-upload": RequestLimiter(10),
            "/api/video/analyze": RequestLimiter(5),
            "/api/simulate/tournament": RequestLimiter(20),
            "/api/predict": RequestLimiter(60),
        }

    def secure(self, response: Response, request_id: str, path: str) -> Response:
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["content-security-policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if path.startswith("/api/") or path == "/health":
            response.headers["cache-control"] = "no-store"
        elif path == "/" or response.headers.get("content-type", "").startswith("text/html"):
            response.headers["cache-control"] = "no-cache"
        else:
            response.headers.setdefault("cache-control", "public, max-age=3600")
        if self.settings.environment != "development":
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        return response

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = safe_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = perf_counter()

        client = request.client.host if request.client else "unknown"
        if not self.limiter.allow(client):
            return self.secure(error_response(429, "rate_limited", "Too many requests. Try again shortly.", request_id), request_id, request.url.path)
        endpoint_limiter = self.expensive_limiters.get(request.url.path)
        if endpoint_limiter and not endpoint_limiter.allow(client):
            return self.secure(error_response(429, "rate_limited", "Too many requests. Try again shortly.", request_id), request_id, request.url.path)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                return self.secure(error_response(400, "invalid_content_length", "Invalid content length.", request_id), request_id, request.url.path)
            limit = (self.settings.upload_limit_bytes + 1024 * 1024) if request.url.path.startswith("/api/video/") else self.settings.request_body_limit_bytes
            if length > limit:
                return self.secure(error_response(413, "request_too_large", "Request body is too large.", request_id), request_id, request.url.path)
        elif request.method in {"POST", "PUT", "PATCH"}:
            return self.secure(error_response(411, "length_required", "Content-Length is required.", request_id), request_id, request.url.path)

        response = await call_next(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        self.secure(response, request_id, request.url.path)
        LOGGER.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
                "cf_ray": (request.headers.get("cf-ray") or "")[:80].replace("\r", "").replace("\n", ""),
            },
        )
        return response
