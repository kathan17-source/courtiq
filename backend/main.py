"""Compatibility entry point for local and hosted API runners.

Use either:
    uvicorn backend.main:app
or:
    uvicorn backend.app.main:app
"""

from backend.app.main import app

__all__ = ["app"]
