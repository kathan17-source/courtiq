from __future__ import annotations

import logging
from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.config import Settings
from backend.app.services.security import RequestLimiter, make_request_id


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

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or make_request_id()
        request.state.request_id = request_id
        started = perf_counter()

        client = request.client.host if request.client else "unknown"
        if not self.limiter.allow(client):
            return error_response(429, "rate_limited", "Too many requests. Try again shortly.", request_id)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
            except ValueError:
                return error_response(400, "invalid_content_length", "Invalid content length.", request_id)
            if length > max(self.settings.request_body_limit_bytes, self.settings.upload_limit_bytes):
                return error_response(413, "request_too_large", "Request body is too large.", request_id)

        response = await call_next(request)
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["permissions-policy"] = "camera=(), microphone=(), geolocation=()"
        if self.settings.environment != "development":
            response.headers["strict-transport-security"] = "max-age=31536000; includeSubDomains"
        LOGGER.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": elapsed_ms,
            },
        )
        return response
