#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))

    try:
        import uvicorn
    except ImportError:
        print("CourtIQ backend dependencies are missing.")
        print("Install them first: python -m pip install -r backend/requirements.txt")
        return 1

    host = os.getenv("COURTIQ_HOST", "127.0.0.1")
    port = int(os.getenv("PORT") or os.getenv("COURTIQ_PORT", "8000"))
    print(f"CourtIQ is starting at http://{host}:{port}")
    print("Open that URL, not the file:// index.html path.")
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=False, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
