from __future__ import annotations

import csv
import sys
from pathlib import Path


REQUIRED_COLUMNS = {"winner", "loser", "tourney_name", "surface", "tourney_date"}


def inspect_csv(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fields)
        rows = sum(1 for _ in reader)
    return {"path": str(path), "rows": rows, "missing_required_columns": missing}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_tennis_csv.py path/to/matches.csv")
        return 2
    report = inspect_csv(Path(sys.argv[1]))
    print(report)
    return 1 if report["missing_required_columns"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
