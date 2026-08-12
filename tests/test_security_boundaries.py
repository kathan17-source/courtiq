from __future__ import annotations

from unittest.mock import patch

from backend.app.services.security import RequestLimiter, safe_request_id


def test_request_limiter_enforces_boundary() -> None:
    limiter = RequestLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client") is True
    assert limiter.allow("client") is True
    assert limiter.allow("client") is False


def test_request_limiter_expires_stale_buckets_and_bounds_keys() -> None:
    limiter = RequestLimiter(limit=2, window_seconds=10, max_keys=2)
    with patch("backend.app.services.security.monotonic", side_effect=[0, 1, 20, 21]):
        assert limiter.allow("first") is True
        assert limiter.allow("second") is True
        assert limiter.allow("third") is True
        assert limiter.allow("fourth") is True
    assert len(limiter._events) <= 2


def test_untrusted_request_ids_are_replaced() -> None:
    assert safe_request_id("safe-id_123") == "safe-id_123"
    assert safe_request_id("line\r\nbreak") != "line\r\nbreak"
    assert safe_request_id("x" * 65) != "x" * 65
