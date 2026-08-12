from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlayerSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    tour: str
    ranking: float | None = None
    ranking_points: float | None = None
    matches: int | None = None
    last_date: str | None = None
    overall_elo: float | None = None
    hard_elo: float | None = None
    clay_elo: float | None = None
    grass_elo: float | None = None
    status: str = "trained"


class PlayerSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    results: list[PlayerSummary]
