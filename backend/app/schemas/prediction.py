from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    player1: str = Field(..., min_length=2, max_length=80)
    player2: str = Field(..., min_length=2, max_length=80)
    event: str = Field(default="Wimbledon", min_length=2, max_length=120)
    surface: str | None = Field(default=None)
    as_of: date | None = Field(default=None)
    tour: str = Field(default="atp")
    best_of: int | None = Field(default=None, ge=3, le=5)
    allow_demo: bool = Field(
        default=False,
        description="Allow deterministic demo prediction when no database-backed model is loaded.",
    )

    @field_validator("tour")
    @classmethod
    def tour_must_be_supported(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"atp", "wta"}:
            raise ValueError("tour must be 'atp' or 'wta'")
        return value

    @field_validator("best_of")
    @classmethod
    def best_of_must_be_three_or_five(cls, value: int | None) -> int | None:
        if value is not None and value not in {3, 5}:
            raise ValueError("best_of must be 3 or 5")
        return value

    @field_validator("surface")
    @classmethod
    def surface_must_be_supported(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().replace(" court", "")
        if normalized not in {"hard", "clay", "grass"}:
            raise ValueError("surface must be hard, clay, or grass")
        return normalized


class TournamentSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tour: str
    event: str = Field(..., min_length=2, max_length=120)
    surface: str | None = None
    players: list[str] = Field(..., min_length=2, max_length=128)
    draw_size: int = Field(..., ge=2, le=128)
    simulations: int = Field(default=10_000, ge=1, le=10_000)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @field_validator("tour")
    @classmethod
    def valid_tour(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"atp", "wta"}:
            raise ValueError("tour must be 'atp' or 'wta'")
        return normalized

    @field_validator("surface")
    @classmethod
    def valid_surface(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().replace(" court", "")
        if normalized not in {"hard", "clay", "grass"}:
            raise ValueError("surface must be hard, clay, or grass")
        return normalized

    @model_validator(mode="after")
    def valid_draw(self) -> "TournamentSimulationRequest":
        cleaned = [" ".join(player.split()) for player in self.players]
        if any(len(player) < 2 or len(player) > 80 for player in cleaned):
            raise ValueError("player names must contain 2 to 80 characters")
        if len({player.casefold() for player in cleaned}) != len(cleaned):
            raise ValueError("draw contains duplicate players")
        if self.draw_size != len(cleaned):
            raise ValueError("draw_size must equal the number of players")
        if self.draw_size & (self.draw_size - 1):
            raise ValueError("draw_size must be a supported power of two")
        self.players = cleaned
        return self


class PredictionFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature: str
    advantage: str
    impact: float
    explanation: str


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player1: str
    player2: str
    event: str
    surface: str
    player1_win_probability: float
    winner: str
    model_version: str
    data_status: str
    factors: list[PredictionFactor]
    features: dict[str, float | int | str]
    diagnostics: dict[str, object] = Field(default_factory=dict)
