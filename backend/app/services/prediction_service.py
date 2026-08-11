from __future__ import annotations

import math

from backend.app.config import get_settings
from backend.app.schemas.prediction import PredictionFactor, PredictionRequest, PredictionResponse
from backend.app.services.elo_service import PlayerRating, blended_rating, expected_score
from backend.app.services.model_store import ModelUnavailableError, get_player_record, load_tour_model
from backend.app.services.tennis_math import clamp, game_win_probability, match_win_from_set, set_win_probability_from_hold, sigmoid


EVENT_SURFACE = {
    "hard court": "hard",
    "clay court": "clay",
    "grass court": "grass",
    "australian open": "hard",
    "roland garros": "clay",
    "french open": "clay",
    "wimbledon": "grass",
    "us open": "hard",
}


def event_surface(event: str, explicit_surface: str | None = None) -> str:
    if explicit_surface:
        return explicit_surface
    surface = EVENT_SURFACE.get(event.strip().lower())
    if surface is None:
        raise ValueError("Unknown event surface; provide surface explicitly as hard, clay, or grass.")
    return surface


def demo_rating(name: str, tour: str) -> PlayerRating:
    seed = 0
    for char in name:
        seed = (seed * 31 + ord(char)) % 9973
    base = 1510 if tour == "wta" else 1520
    rating = PlayerRating(overall=base + (seed % 180) - 90)
    rating.surface["hard"] = rating.overall + ((seed * 3) % 70) - 35
    rating.surface["clay"] = rating.overall + ((seed * 5) % 70) - 35
    rating.surface["grass"] = rating.overall + ((seed * 7) % 70) - 35
    return rating


def _rating_from_record(name: str, tour: str) -> PlayerRating:
    record = get_player_record(name, tour)
    rating = PlayerRating(overall=record.overall_elo, matches=record.matches, uncertainty=max(28.0, 90.0 / max(record.matches, 1) ** 0.35))
    for surface in ("hard", "clay", "grass"):
        rating.surface[surface] = record.surface_elo.get(surface, record.overall_elo)
    return rating


def predict_from_ratings(p1: PlayerRating, p2: PlayerRating, surface: str, best_of: int) -> tuple[float, dict[str, float]]:
    p1_rating = blended_rating(p1, surface)
    p2_rating = blended_rating(p2, surface)
    elo_prior = expected_score(p1_rating, p2_rating)
    point_edge = clamp((p1_rating - p2_rating) / 1150.0, -0.11, 0.11)
    p1_serve_point = clamp(0.635 + point_edge, 0.50, 0.78)
    p2_serve_point = clamp(0.635 - point_edge, 0.50, 0.78)
    p1_hold = game_win_probability(p1_serve_point)
    p2_hold = game_win_probability(p2_serve_point)
    set_probability = set_win_probability_from_hold(p1_hold, p2_hold)
    markov_match = match_win_from_set(set_probability, best_of)
    probability = clamp(0.62 * markov_match + 0.38 * elo_prior, 0.02, 0.98)
    return probability, {
        "p1_blended_rating": round(p1_rating, 2),
        "p2_blended_rating": round(p2_rating, 2),
        "elo_prior": round(elo_prior, 4),
        "p1_hold": round(p1_hold, 4),
        "p2_hold": round(p2_hold, 4),
        "markov_match": round(markov_match, 4),
    }


def predict_match(request: PredictionRequest) -> PredictionResponse:
    settings = get_settings()
    surface = event_surface(request.event, request.surface)
    best_of = request.best_of or (5 if request.tour == "atp" and request.event.strip().lower() in EVENT_SURFACE else 3)

    model = None
    if request.allow_demo:
        p1 = demo_rating(request.player1, request.tour)
        p2 = demo_rating(request.player2, request.tour)
        model_version = f"{settings.model_version}-explicit-demo"
        data_status = "explicit_demo_not_production"
    else:
        model = load_tour_model(request.tour)
        p1 = _rating_from_record(request.player1, request.tour)
        p2 = _rating_from_record(request.player2, request.tour)
        model_version = model.version
        data_status = "real_artifact_loaded"
    probability, features = predict_from_ratings(p1, p2, surface, best_of)

    if model is not None:
        record1 = get_player_record(request.player1, request.tour)
        record2 = get_player_record(request.player2, request.tour)
        advanced1 = record1.advanced_state or {}
        advanced2 = record2.advanced_state or {}
        stat1 = record1.stat_averages
        stat2 = record2.stat_averages
        rd1 = float(advanced1.get("rd", 120.0))
        rd2 = float(advanced2.get("rd", 120.0))
        surface_matches1 = float((advanced1.get("surface_matches") or {}).get(surface, 0.0))
        surface_matches2 = float((advanced2.get("surface_matches") or {}).get(surface, 0.0))
        shrunk_surface1 = shrink_surface_rating(record1.overall_elo, record1.surface_elo.get(surface, record1.overall_elo), surface_matches1)
        shrunk_surface2 = shrink_surface_rating(record2.overall_elo, record2.surface_elo.get(surface, record2.overall_elo), surface_matches2)
        serve1 = service_point_from_stats(stat1)
        serve2 = service_point_from_stats(stat2)
        return1 = stat1.get("return_point_won", 0.365)
        return2 = stat2.get("return_point_won", 0.365)
        structural_probability = structural_match_probability(record1, record2, surface, best_of)
        engineered = {
            "overall_elo_diff": (p1.overall - p2.overall) / 400.0,
            "surface_elo_diff": (p1.surface[surface] - p2.surface[surface]) / 400.0,
            "surface_elo_shrunk_diff": (shrunk_surface1 - shrunk_surface2) / 400.0,
            "rating_rd_diff": (rd2 - rd1) / 350.0,
            "rating_uncertainty_sum": (rd1 + rd2) / 700.0,
            "form_5_diff": record1.form_5 - record2.form_5,
            "form_10_diff": record1.form_10 - record2.form_10,
            "form_20_diff": record1.form_20 - record2.form_20,
            "surface_form_diff": record1.surface_form.get(surface, 0.5) - record2.surface_form.get(surface, 0.5),
            "matches_diff": (min(record1.matches, 300) - min(record2.matches, 300)) / 300.0,
            "match_count_log_diff": math.log1p(record1.matches) - math.log1p(record2.matches),
            "ranking_diff": ((record2.ranking or 999.0) - (record1.ranking or 999.0)) / 998.0,
            "ranking_points_diff": ((record1.ranking_points or 0.0) - (record2.ranking_points or 0.0)) / 12000.0,
            "rank_known": float(record1.ranking is not None and record2.ranking is not None),
            "age_diff": ((advanced1.get("age") or 27.0) - (advanced2.get("age") or 27.0)) / 15.0,
            "height_diff": ((advanced1.get("height") or 185.0) - (advanced2.get("height") or 185.0)) / 30.0,
            "lefty_matchup": float(advanced1.get("hand") == "L") - float(advanced2.get("hand") == "L"),
            "same_hand": float(bool(advanced1.get("hand")) and advanced1.get("hand") == advanced2.get("hand")),
            "serve_strength_diff": serve1 - serve2,
            "return_strength_diff": return1 - return2,
            "serve_return_edge": (serve1 - (1.0 - return2)) - (serve2 - (1.0 - return1)),
            "ace_rate_diff": record1.stat_averages.get("ace_rate", 0.5) - record2.stat_averages.get("ace_rate", 0.5),
            "df_rate_diff": record1.stat_averages.get("df_rate", 0.5) - record2.stat_averages.get("df_rate", 0.5),
            "first_in_diff": record1.stat_averages.get("first_in", 0.5) - record2.stat_averages.get("first_in", 0.5),
            "first_won_diff": record1.stat_averages.get("first_won", 0.5) - record2.stat_averages.get("first_won", 0.5),
            "second_won_diff": record1.stat_averages.get("second_won", 0.5) - record2.stat_averages.get("second_won", 0.5),
            "bp_save_diff": record1.stat_averages.get("bp_save", 0.5) - record2.stat_averages.get("bp_save", 0.5),
            "bp_convert_diff": record1.stat_averages.get("bp_convert", 0.5) - record2.stat_averages.get("bp_convert", 0.5),
            "return_point_won_diff": record1.stat_averages.get("return_point_won", 0.365) - record2.stat_averages.get("return_point_won", 0.365),
            "serve_point_won_diff": record1.stat_averages.get("serve_point_won", 0.635) - record2.stat_averages.get("serve_point_won", 0.635),
            "stat_sample_diff": record1.stat_averages.get("stat_sample", 0.0) - record2.stat_averages.get("stat_sample", 0.0),
            "days_rest_diff": 0.0,
            "recovery_curve_diff": 0.0,
            "workload_3d_diff": 0.0,
            "workload_7d_diff": 0.0,
            "workload_14d_diff": 0.0,
            "residual_form_short_diff": float(advanced1.get("residual_form_short", 0.0)) - float(advanced2.get("residual_form_short", 0.0)),
            "residual_form_medium_diff": float(advanced1.get("residual_form_medium", 0.0)) - float(advanced2.get("residual_form_medium", 0.0)),
            "surface_residual_form_diff": float((advanced1.get("surface_residual_form") or {}).get(surface, 0.0))
            - float((advanced2.get("surface_residual_form") or {}).get(surface, 0.0)),
            "score_dominance_diff": float(advanced1.get("score_dominance", 0.0)) - float(advanced2.get("score_dominance", 0.0)),
            "set_dominance_diff": float(advanced1.get("set_dominance", 0.0)) - float(advanced2.get("set_dominance", 0.0)),
            "tiebreak_strength_diff": float(advanced1.get("tiebreak_strength", 0.0)) - float(advanced2.get("tiebreak_strength", 0.0)),
            "h2h_prior_diff": 0.0,
            "surface_h2h_prior_diff": 0.0,
            "best_of_5": float(best_of == 5),
            "surface_sample_diff": (surface_matches1 - surface_matches2) / 80.0,
            "data_strength_diff": (
                math.log1p(record1.matches) + math.log1p(stat1.get("stat_sample", 0.0) * 6000.0)
                - math.log1p(record2.matches) - math.log1p(stat2.get("stat_sample", 0.0) * 6000.0)
            ) / 10.0,
            "structural_match_logit": safe_logit(structural_probability),
        }
        logit = production_logit(model, engineered)
        probability = clamp(sigmoid(logit), 0.01, 0.99)
        features.update({key: round(value, 4) for key, value in engineered.items()})

    winner = request.player1 if probability >= 0.5 else request.player2
    surface_edge = (p1.surface[surface] - p2.surface[surface]) / 400

    factors = [
        PredictionFactor(
            feature="surface_elo",
            advantage=request.player1 if surface_edge >= 0 else request.player2,
            impact=round(surface_edge, 4),
            explanation="Difference between pre-match surface-specific Elo ratings.",
        ),
        PredictionFactor(
            feature="hold_probability",
            advantage=request.player1 if features["p1_hold"] >= features["p2_hold"] else request.player2,
            impact=round(features["p1_hold"] - features["p2_hold"], 4),
            explanation="Estimated service hold edge derived from point-to-game tennis math.",
        ),
    ]

    return PredictionResponse(
        player1=request.player1,
        player2=request.player2,
        event=request.event,
        surface=surface,
        player1_win_probability=round(probability, 4),
        winner=winner,
        model_version=model_version,
        data_status=data_status,
        factors=factors,
        features={
            **features,
            "p1_surface_elo": round(p1.surface[surface], 1),
            "p2_surface_elo": round(p2.surface[surface], 1),
            "p1_overall_elo": round(p1.overall, 1),
            "p2_overall_elo": round(p2.overall, 1),
            "best_of": best_of,
        },
        diagnostics={
            "artifact_as_of": model.state_cutoff if model is not None else None,
            "requested_as_of": request.as_of.isoformat() if request.as_of else None,
            "training_cutoff": model.training_cutoff if model is not None else None,
            "evaluation_cutoff": model.evaluation_cutoff if model is not None else None,
            "artifact_created_at": model.generated_at if model is not None else None,
            "temporal_policy": model.temporal_policy if model is not None else "demo",
            "feature_availability": "serialized latest player state; workload, rest, and H2H request-time features use explicit neutral defaults",
            "warnings": (["Requested as-of state is not reconstructed; prediction uses the serialized artifact state."] if request.as_of else []),
        },
    )


def production_logit(model: object, engineered: dict[str, float]) -> float:
    if getattr(model, "model_type", "") == "time_safe_stacked_ensemble":
        ensemble = getattr(model, "ensemble", {}) or {}
        full = ensemble.get("full_logistic") or {}
        full_logit = float(full.get("intercept", 0.0))
        for coefficient, feature_name in zip(full.get("coefficients", []), full.get("feature_names", []), strict=False):
            full_logit += float(coefficient) * engineered.get(str(feature_name), 0.0)
        meta_values = {
            "full_logistic": full_logit,
            "overall_elo": safe_logit(sigmoid(2.2 * engineered.get("overall_elo_diff", 0.0))),
            "surface_elo": safe_logit(sigmoid(2.2 * engineered.get("surface_elo_diff", 0.0))),
            "ranking": safe_logit(sigmoid(2.2 * engineered.get("ranking_diff", 0.0))),
            "serve_return": safe_logit(sigmoid(9.0 * engineered.get("serve_point_won_diff", 0.0))),
        }
        stacker = ensemble.get("stacker") or {}
        logit = float(stacker.get("intercept", 0.0))
        for coefficient, feature_name in zip(stacker.get("coefficients", []), stacker.get("feature_names", []), strict=False):
            logit += float(coefficient) * meta_values.get(str(feature_name), 0.0)
    else:
        coefficients = getattr(model, "coefficients", [])
        feature_names = getattr(model, "feature_names", [])
        ensemble = getattr(model, "ensemble", {}) or {}
        center = ensemble.get("center") or []
        scale = ensemble.get("scale") or []
        logit = getattr(model, "intercept", 0.0)
        for index, (coefficient, feature_name) in enumerate(zip(coefficients, feature_names, strict=False)):
            value = engineered.get(feature_name, 0.0)
            if center and scale and index < len(center) and index < len(scale):
                divisor = float(scale[index]) or 1.0
                value = (value - float(center[index])) / divisor
            logit += coefficient * value
    calibration = getattr(model, "calibration", {}) or {}
    if calibration:
        logit = calibration.get("slope", 1.0) * logit + calibration.get("intercept", 0.0)
    return float(logit)


def safe_logit(probability: float) -> float:
    p = clamp(probability, 0.000001, 0.999999)
    from math import log

    return log(p / (1.0 - p))


def shrink_surface_rating(overall: float, surface_rating_value: float, surface_matches: float, k: float = 18.0) -> float:
    weight = surface_matches / (surface_matches + k) if surface_matches > 0 else 0.0
    return weight * surface_rating_value + (1.0 - weight) * overall


def service_point_from_stats(stats: dict[str, float]) -> float:
    first_in = stats.get("first_in", 0.62)
    first_won = stats.get("first_won", 0.72)
    second_won = stats.get("second_won", 0.52)
    return clamp(first_in * first_won + (1.0 - first_in) * second_won, 0.48, 0.78)


def structural_match_probability(record1: object, record2: object, surface: str, best_of: int) -> float:
    stats1 = getattr(record1, "stat_averages", {}) or {}
    stats2 = getattr(record2, "stat_averages", {}) or {}
    advanced1 = getattr(record1, "advanced_state", {}) or {}
    advanced2 = getattr(record2, "advanced_state", {}) or {}
    surface_matches1 = float((advanced1.get("surface_matches") or {}).get(surface, 0.0))
    surface_matches2 = float((advanced2.get("surface_matches") or {}).get(surface, 0.0))
    rating1 = shrink_surface_rating(
        getattr(record1, "overall_elo", 1500.0),
        getattr(record1, "surface_elo", {}).get(surface, getattr(record1, "overall_elo", 1500.0)),
        surface_matches1,
    )
    rating2 = shrink_surface_rating(
        getattr(record2, "overall_elo", 1500.0),
        getattr(record2, "surface_elo", {}).get(surface, getattr(record2, "overall_elo", 1500.0)),
        surface_matches2,
    )
    serve1 = 0.72 * service_point_from_stats(stats1) + 0.28 * (1.0 - stats2.get("return_point_won", 0.365))
    serve2 = 0.72 * service_point_from_stats(stats2) + 0.28 * (1.0 - stats1.get("return_point_won", 0.365))
    edge = clamp((rating1 - rating2) / 2400.0, -0.05, 0.05)
    hold1 = game_win_probability(clamp(serve1 + edge, 0.50, 0.80))
    hold2 = game_win_probability(clamp(serve2 - edge, 0.50, 0.80))
    set_probability = set_win_probability_from_hold(hold1, hold2)
    return clamp(match_win_from_set(set_probability, best_of), 0.01, 0.99)
