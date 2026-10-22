from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services.simulation_service import benchmark_simulations

if __name__ == "__main__":
    results = benchmark_simulations()
    print(
        json.dumps(
            {
                "seed": results[0].seed,
                "benchmarks": [result.__dict__ for result in results],
            },
            indent=2,
        )
    )
