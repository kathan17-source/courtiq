from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.app.config import get_settings


class ModelUnavailableError(RuntimeError):
    """Raised when production prediction data is not loaded."""


@dataclass(frozen=True)
class PlayerRecord:
    key: str
    name: str
    tour: str
    overall_elo: float
    surface_elo: dict[str, float]
    form_5: float
    form_10: float
    form_20: float
    surface_form: dict[str, float]
    stat_averages: dict[str, float]
    last_date: str | None
    matches: int
    ranking: float | None = None
    ranking_points: float | None = None
    advanced_state: dict[str, Any] | None = None


@dataclass(frozen=True)
class LoadedModel:
    path: Path
    version: str
    model_type: str
    feature_names: list[str]
    coefficients: list[float]
    intercept: float
    calibration: dict[str, float]
    ensemble: dict[str, Any]
    metrics: dict[str, Any]
    generated_at: str
    matches_processed: int
    players: dict[str, PlayerRecord]
    tour: str
    training_cutoff: str
    evaluation_cutoff: str
    state_cutoff: str
    temporal_policy: str


def normalize_player_key(name: str, tour: str) -> str:
    cleaned = " ".join(name.strip().lower().replace("_", " ").split())
    return f"{tour.strip().lower()}::{cleaned}"


def abbreviated_name_candidates(name: str) -> list[str]:
    parts = [part.strip(" ,.") for part in name.split() if part.strip(" ,.")]
    if len(parts) < 2:
        return []
    first = parts[0]
    last = parts[-1]
    if not first or not last:
        return []
    return [f"{last} {first[0]}.", f"{last}, {first[0]}."]


def _player_from_payload(key: str, payload: dict[str, Any]) -> PlayerRecord:
    return PlayerRecord(
        key=key,
        name=str(payload["name"]),
        tour=str(payload["tour"]),
        overall_elo=float(payload.get("overall_elo", 1500.0)),
        surface_elo={surface: float(value) for surface, value in payload.get("surface_elo", {}).items()},
        form_5=float(payload.get("form_5", 0.5)),
        form_10=float(payload.get("form_10", 0.5)),
        form_20=float(payload.get("form_20", 0.5)),
        surface_form={surface: float(value) for surface, value in payload.get("surface_form", {}).items()},
        stat_averages={key: float(value) for key, value in payload.get("stat_averages", {}).items()},
        last_date=payload.get("last_date"),
        matches=int(payload.get("matches", 0)),
        ranking=float(payload["ranking"]) if payload.get("ranking") is not None else None,
        ranking_points=float(payload["ranking_points"]) if payload.get("ranking_points") is not None else None,
        advanced_state=payload.get("advanced_state") or {},
    )


def load_model_from_path(path: Path) -> LoadedModel:
    if not path.exists():
        raise ModelUnavailableError(f"Model artifact not found: {path}")
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    model = payload.get("model") or {}
    required = ("model_version", "generated_at", "tour", "training_cutoff", "temporal_policy_version")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ModelUnavailableError(f"Model artifact is missing required metadata: {', '.join(missing)}")
    tour = str(payload["tour"]).lower()
    if tour not in {"atp", "wta"}:
        raise ModelUnavailableError("Model artifact tour must be ATP or WTA.")
    players_payload = payload.get("players") or {}
    players = {key: _player_from_payload(key, value) for key, value in players_payload.items()}
    if not players:
        raise ModelUnavailableError("Model artifact has no player records.")
    if not model.get("feature_names") or not model.get("coefficients"):
        raise ModelUnavailableError("Model artifact is missing logistic model parameters.")
    feature_names = [str(item) for item in model["feature_names"]]
    coefficients = [float(item) for item in model["coefficients"]]
    if len(feature_names) != len(coefficients) or len(set(feature_names)) != len(feature_names):
        raise ModelUnavailableError("Model artifact feature and coefficient arrays are inconsistent.")
    if not all(math.isfinite(value) for value in [*coefficients, float(model.get("intercept", 0.0))]):
        raise ModelUnavailableError("Model artifact contains non-finite parameters.")
    for key in ("center", "scale"):
        values = model.get(key) or []
        if values and len(values) != len(feature_names):
            raise ModelUnavailableError(f"Model artifact {key} length does not match feature count.")
        if values and not all(math.isfinite(float(value)) for value in values):
            raise ModelUnavailableError(f"Model artifact {key} contains non-finite values.")
    calibration = {str(key): float(value) for key, value in (model.get("calibration") or {}).items() if isinstance(value, (int, float))}
    if calibration and (not math.isfinite(calibration.get("slope", 1.0)) or calibration.get("slope", 1.0) <= 0 or not math.isfinite(calibration.get("intercept", 0.0))):
        raise ModelUnavailableError("Model artifact calibration parameters are invalid.")
    if any(player.tour.lower() != tour for player in players.values()):
        raise ModelUnavailableError("Model artifact contains player records from the wrong tour.")
    state_cutoff = max((player.last_date or "" for player in players.values()), default="")

    return LoadedModel(
        path=path,
        version=str(payload.get("model_version") or "courtiq-unversioned"),
        model_type=str(model.get("type") or "logistic_regression"),
        feature_names=feature_names,
        coefficients=coefficients,
        intercept=float(model.get("intercept", 0.0)),
        calibration=calibration,
        ensemble=model.get("ensemble") or {"center": model.get("center") or [], "scale": model.get("scale") or []},
        metrics=payload.get("metrics") or {},
        generated_at=str(payload.get("generated_at") or ""),
        matches_processed=int(payload.get("matches_processed", 0)),
        players=players,
        tour=tour,
        training_cutoff=str(payload["training_cutoff"]),
        evaluation_cutoff=str(payload.get("evaluation_period") or payload.get("calibration_period") or "not recorded"),
        state_cutoff=state_cutoff or "not recorded",
        temporal_policy=str(payload["temporal_policy_version"]),
    )


@lru_cache(maxsize=1)
def load_current_model() -> LoadedModel:
    return load_model_from_path(get_settings().model_artifact_path)


def tour_model_path(tour: str) -> Path:
    tour_key = tour.strip().lower()
    base_path = get_settings().model_artifact_path
    model_dir = base_path.parent
    if tour_key == "wta":
        return model_dir / "courtiq_model_wta.json"
    if tour_key == "atp":
        atp_path = model_dir / "courtiq_model_atp.json"
        return atp_path if atp_path.exists() else base_path
    raise ModelUnavailableError("tour must be 'atp' or 'wta'")


@lru_cache(maxsize=4)
def load_tour_model(tour: str) -> LoadedModel:
    return load_model_from_path(tour_model_path(tour))


def clear_model_cache() -> None:
    load_current_model.cache_clear()
    load_tour_model.cache_clear()


def has_current_model() -> bool:
    try:
        load_current_model()
    except ModelUnavailableError:
        return False
    return True


def has_tour_model(tour: str) -> bool:
    try:
        model = load_tour_model(tour)
    except ModelUnavailableError:
        return False
    return any(player.tour == tour.strip().lower() for player in model.players.values())


def get_player_record(name: str, tour: str) -> PlayerRecord:
    tour_key = tour.strip().lower()
    model = load_tour_model(tour_key)
    key = normalize_player_key(name, tour_key)
    if key in model.players:
        return model.players[key]
    for candidate in abbreviated_name_candidates(name):
        candidate_key = normalize_player_key(candidate, tour_key)
        if candidate_key in model.players:
            return model.players[candidate_key]
    query = " ".join(name.strip().lower().split())
    matches = [
        player
        for player in model.players.values()
        if player.name.strip().lower() == query
        or any(player.name.strip().lower() == candidate.lower() for candidate in abbreviated_name_candidates(name))
    ]
    if len(matches) == 1:
        return matches[0]
    raise ModelUnavailableError(f"Player is not in the trained {tour_key.upper()} model artifact: {name}")
