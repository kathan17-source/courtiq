#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATHS = [
    ROOT / "output/models/courtiq_model_atp.json",
    ROOT / "output/models/courtiq_model_wta.json",
]
OUTPUT_PATH = ROOT / "outputs/tennis-ai-app/assets/player-stats.js"


def round_or_none(value: Any, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def player_rows() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    directory: list[dict[str, Any]] = []
    stats: dict[str, dict[str, Any]] = {}
    for path in MODEL_PATHS:
        if not path.exists():
            continue
        artifact = json.loads(path.read_text(encoding="utf-8"))
        for key, player in (artifact.get("players") or {}).items():
            tour = str(player.get("tour") or "").upper()
            name = str(player.get("name") or "").strip()
            if tour not in {"ATP", "WTA"} or not name:
                continue
            surface_elo = player.get("surface_elo") or {}
            averages = player.get("stat_averages") or {}
            row = {
                "id": key.replace("::", ":"),
                "name": name,
                "tour": tour,
                "country": "",
                "handedness": "",
                "age": None,
                "ranking": round_or_none(player.get("ranking"), 0),
                "ranking_points": round_or_none(player.get("ranking_points"), 0),
                "matches": int(player.get("matches") or 0),
                "last_date": player.get("last_date"),
                "overall_elo": round_or_none(player.get("overall_elo"), 1),
                "hard_elo": round_or_none(surface_elo.get("hard", player.get("overall_elo")), 1),
                "clay_elo": round_or_none(surface_elo.get("clay", player.get("overall_elo")), 1),
                "grass_elo": round_or_none(surface_elo.get("grass", player.get("overall_elo")), 1),
                "serve_point_won": round_or_none(100 * float(averages.get("serve_point_won", 0.635)), 1),
                "return_point_won": round_or_none(100 * float(averages.get("return_point_won", 0.365)), 1),
                "form_5": round_or_none(100 * float(player.get("form_5", 0.5)), 1),
                "status": "trained",
            }
            directory.append(row)
            stats[name] = {
                "global": row["overall_elo"],
                "hard": row["hard_elo"],
                "clay": row["clay_elo"],
                "grass": row["grass_elo"],
                "serve": row["serve_point_won"],
                "return": row["return_point_won"],
                "form": row["form_5"],
                "pressure": round_or_none(100 * float(averages.get("bp_save", 0.58)), 1),
                "movement": 50,
                "rally": 50,
                "fatigue": 8,
                "volatility": 10,
                "matches": row["matches"],
                "ranking": row["ranking"],
                "tour": tour,
                "source": "historical",
            }
    directory.sort(key=lambda item: (item["tour"], item["ranking"] is None, item["ranking"] or 99999, item["name"]))
    return directory, stats


def main() -> int:
    directory, stats = player_rows()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "window.COURTIQ_PLAYER_DIRECTORY = "
        + json.dumps(directory, separators=(",", ":"), ensure_ascii=False)
        + ";\nwindow.COURTIQ_PLAYER_STATS = "
        + json.dumps(stats, separators=(",", ":"), ensure_ascii=False)
        + ";\n"
    )
    OUTPUT_PATH.write_text(payload, encoding="utf-8")
    print(json.dumps({"path": str(OUTPUT_PATH), "players": len(directory), "stats": len(stats)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
