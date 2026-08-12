from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.train_match_model import FEATURE_NAMES


def count_files(patterns: tuple[str, ...]) -> int:
    ignored_parts = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        "site-packages",
        "dist-packages",
        "output",
        "outputs",
        "tmp",
    }
    total = 0
    for pattern in patterns:
        total += sum(1 for path in ROOT.rglob(pattern) if ignored_parts.isdisjoint(path.relative_to(ROOT).parts))
    return total


def load_backtest() -> dict:
    reports = []
    for tour in ("atp", "wta"):
        path = ROOT / f"output/backtests/courtiq_backtest_report_{tour}.json"
        artifact_path = ROOT / f"output/models/courtiq_model_{tour}.json"
        if path.exists():
            report = json.loads(path.read_text(encoding="utf-8"))
            artifact = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.exists() else {}
            report["_players_from_artifact"] = len(artifact.get("players", {}))
            reports.append(report)
    if reports:
        return {
            "status": "ok" if all(item.get("status") == "ok" for item in reports) else "partial",
            "matches": sum(int(item.get("matches", 0)) for item in reports),
            "players": sum(int(item.get("_players_from_artifact", item.get("players", 0))) for item in reports),
            "tours": {str(item.get("tour", "unknown")): item for item in reports},
        }
    return {"status": "missing"}


def discover_tests() -> int:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    count = 0
    stack = [suite]
    while stack:
        item = stack.pop()
        if isinstance(item, unittest.TestSuite):
            stack.extend(list(item))
        else:
            count += 1
    return count


def main() -> None:
    backtest = load_backtest()
    stats = {
        "historical_matches_processed": backtest.get("matches", 0) if backtest.get("status") == "ok" else 0,
        "unique_player_profiles_from_backtest": backtest.get("players", 0) if backtest.get("status") == "ok" else 0,
        "backtest_status": backtest.get("status", "missing"),
        "model_features_defined": len(FEATURE_NAMES),
        "automated_tests_discovered": discover_tests(),
        "python_source_files": count_files(("*.py",)),
        "javascript_source_files": count_files(("*.js",)),
        "database_tables_defined": len(re.findall(r"CREATE TABLE IF NOT EXISTS", (ROOT / "backend/database/schema.sql").read_text(encoding="utf-8"))),
        "ci_workflow_present": (ROOT / ".github/workflows/ci.yml").exists(),
        "docker_compose_present": (ROOT / "docker-compose.yml").exists(),
    }
    out = ROOT / "output/benchmarks/project_stats.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
