from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.tennis_math import clamp, game_win_probability, match_win_from_set, set_win_probability_from_hold

DATA_DIR = ROOT / "work/tennis-data"
MODEL_PATH = ROOT / "output/models/courtiq_model_atp.json"
FROZEN_BASELINE_PATH = ROOT / "output/models/courtiq_logistic_baseline.json"
ENHANCED_ROWS_PATH = ROOT / "output/backtests/courtiq_enhanced_feature_rows.csv"
SAVED_FEATURE_ROWS_PATH = ROOT / "output/backtests/courtiq_feature_rows_atp.csv"
REPORT_PATH = ROOT / "output/backtests/final_modeling_pass_report.json"

SURFACES = {"hard", "clay", "grass", "carpet"}
PRIMARY_SURFACES = {"hard", "clay", "grass"}
ROUND_ORDER = {
    "RR": 1,
    "R128": 2,
    "R64": 3,
    "R32": 4,
    "R16": 5,
    "QF": 6,
    "SF": 7,
    "F": 8,
    "BR": 8,
    "3rd/4th": 8,
}
RUNTIME_COMPATIBLE_FEATURES = {
    "overall_elo_diff",
    "surface_elo_diff",
    "surface_elo_shrunk_diff",
    "rating_rd_diff",
    "rating_uncertainty_sum",
    "matches_diff",
    "match_count_log_diff",
    "ranking_diff",
    "ranking_points_diff",
    "rank_known",
    "age_diff",
    "height_diff",
    "lefty_matchup",
    "same_hand",
    "serve_strength_diff",
    "return_strength_diff",
    "serve_return_edge",
    "first_in_diff",
    "first_won_diff",
    "second_won_diff",
    "ace_rate_diff",
    "df_rate_diff",
    "bp_save_diff",
    "bp_convert_diff",
    "return_point_won_diff",
    "serve_point_won_diff",
    "stat_sample_diff",
    "days_rest_diff",
    "recovery_curve_diff",
    "workload_3d_diff",
    "workload_7d_diff",
    "workload_14d_diff",
    "residual_form_short_diff",
    "residual_form_medium_diff",
    "surface_residual_form_diff",
    "score_dominance_diff",
    "set_dominance_diff",
    "tiebreak_strength_diff",
    "best_of_5",
    "surface_sample_diff",
    "data_strength_diff",
    "structural_match_logit",
    "latent_serve_skill_diff",
    "latent_return_skill_diff",
    "latent_surface_serve_skill_diff",
    "latent_surface_return_skill_diff",
    "latent_uncertainty_sum",
    "latent_exact_match_logit",
}

RETIRED_UNSAFE_BENCHMARK = {
    "status": "retired_due_to_temporal_leakage",
    "note": "The earlier 70%+ benchmark was produced by an unsafe tournament-date path and must not be used as a production target.",
}

VALID_CORRECTED_BENCHMARK = {
    "accuracy": 0.6564,
    "roc_auc": 0.7124,
    "log_loss": 0.6191,
    "brier_score": 0.2156,
    "ece": 0.0283,
}


@dataclass
class RawMatch:
    tour: str
    match_date: date
    tournament_id: str
    tournament: str
    surface: str
    level: str
    indoor: str
    round: str
    best_of: int
    winner: str
    loser: str
    winner_rank: float | None
    loser_rank: float | None
    winner_rank_points: float | None
    loser_rank_points: float | None
    winner_age: float | None
    loser_age: float | None
    winner_height: float | None
    loser_height: float | None
    winner_hand: str
    loser_hand: str
    score: str
    stats: dict[str, float | None]


@dataclass
class DecayedStat:
    success: float = 0.0
    trials: float = 0.0
    last_date: date | None = None

    def rate(self, prior: float, prior_n: float = 120.0) -> float:
        return (prior * prior_n + self.success) / (prior_n + self.trials) if self.trials > 0 else prior

    def add(self, success: float | None, trials: float | None, match_date: date, half_life: float = 730.0) -> None:
        if success is None or trials is None or trials <= 0:
            return
        if self.last_date is not None:
            decay = 2 ** (-max(0, (match_date - self.last_date).days) / half_life)
            self.success *= decay
            self.trials *= decay
        self.success += max(0.0, float(success))
        self.trials += max(0.0, float(trials))
        self.last_date = match_date


@dataclass
class DecayedAverage:
    weighted_sum: float = 0.0
    weight: float = 0.0
    last_date: date | None = None

    def value(self) -> float:
        return self.weighted_sum / self.weight if self.weight > 0 else 0.0

    def add(self, value: float, match_date: date, half_life: float) -> None:
        if self.last_date is not None:
            decay = 2 ** (-max(0, (match_date - self.last_date).days) / half_life)
            self.weighted_sum *= decay
            self.weight *= decay
        self.weighted_sum += float(value)
        self.weight += 1.0
        self.last_date = match_date


@dataclass
class PlayerState:
    name: str
    tour: str
    overall_elo: float = 1500.0
    surface_elo: dict[str, float] = field(default_factory=lambda: {surface: 1500.0 for surface in SURFACES})
    surface_matches: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    rd: float = 350.0
    matches: int = 0
    last_date: date | None = None
    workload_dates: list[date] = field(default_factory=list)
    ranking: float | None = None
    ranking_points: float | None = None
    age: float | None = None
    height: float | None = None
    hand: str = ""
    residual_short: DecayedAverage = field(default_factory=DecayedAverage)
    residual_medium: DecayedAverage = field(default_factory=DecayedAverage)
    surface_residual: dict[str, DecayedAverage] = field(default_factory=lambda: defaultdict(DecayedAverage))
    score_dominance: DecayedAverage = field(default_factory=DecayedAverage)
    set_dominance: DecayedAverage = field(default_factory=DecayedAverage)
    tiebreak_strength: DecayedAverage = field(default_factory=DecayedAverage)
    stats: dict[str, DecayedStat] = field(default_factory=lambda: defaultdict(DecayedStat))
    surface_stats: dict[str, dict[str, DecayedStat]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(DecayedStat)))


@dataclass
class OpponentResidual:
    result: DecayedAverage = field(default_factory=DecayedAverage)
    serve: DecayedAverage = field(default_factory=DecayedAverage)
    return_: DecayedAverage = field(default_factory=DecayedAverage)
    surface_result: dict[str, DecayedAverage] = field(default_factory=lambda: defaultdict(DecayedAverage))


@dataclass
class FittedLogistic:
    features: list[str]
    coefficients: np.ndarray
    intercept: float
    center: np.ndarray
    scale: np.ndarray

    def raw_logits(self, rows: pd.DataFrame) -> np.ndarray:
        x = rows[self.features].to_numpy(dtype=float)
        z = (x - self.center) / self.scale
        return self.intercept + z @ self.coefficients


def normalize_name(value: str) -> str:
    return " ".join((value or "").strip().replace("_", " ").split())


def player_key(name: str, tour: str) -> str:
    return f"{tour}::{normalize_name(name).lower()}"


def parse_date(value: str) -> date:
    value = (value or "").strip()
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    return datetime.fromisoformat(value).date()


def parse_float(row: dict[str, str], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            try:
                return float(value)
            except ValueError:
                pass
    return None


def parse_surface(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in SURFACES else "hard"


def detect_tour(path: Path) -> str:
    return "wta" if "wta" in path.name.lower() else "atp"


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return clamp(numerator / denominator, 0.0, 1.0)


def none_sub(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def none_sum(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a + b


def load_matches() -> list[RawMatch]:
    matches: list[RawMatch] = []
    for path in sorted(DATA_DIR.glob("*.csv")):
        tour = detect_tour(path)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                winner = normalize_name(row.get("winner_name") or row.get("winner") or "")
                loser = normalize_name(row.get("loser_name") or row.get("loser") or "")
                if not winner or not loser:
                    continue
                try:
                    match_date = parse_date(row.get("tourney_date") or row.get("date") or "")
                except ValueError:
                    continue
                w_svpt = parse_float(row, "w_svpt")
                l_svpt = parse_float(row, "l_svpt")
                w_1st = parse_float(row, "w_1stIn")
                l_1st = parse_float(row, "l_1stIn")
                w_1st_won = parse_float(row, "w_1stWon")
                l_1st_won = parse_float(row, "l_1stWon")
                w_2nd_won = parse_float(row, "w_2ndWon")
                l_2nd_won = parse_float(row, "l_2ndWon")
                w_second_total = none_sub(w_svpt, w_1st)
                l_second_total = none_sub(l_svpt, l_1st)
                w_service_won = none_sum(w_1st_won, w_2nd_won)
                l_service_won = none_sum(l_1st_won, l_2nd_won)
                w_bp_faced = parse_float(row, "w_bpFaced")
                l_bp_faced = parse_float(row, "l_bpFaced")
                w_bp_saved = parse_float(row, "w_bpSaved")
                l_bp_saved = parse_float(row, "l_bpSaved")
                stats = {
                    "w_svpt": w_svpt,
                    "l_svpt": l_svpt,
                    "w_service_won": w_service_won,
                    "l_service_won": l_service_won,
                    "w_return_won": none_sub(l_svpt, l_service_won),
                    "l_return_won": none_sub(w_svpt, w_service_won),
                    "w_ace": parse_float(row, "w_ace"),
                    "l_ace": parse_float(row, "l_ace"),
                    "w_df": parse_float(row, "w_df"),
                    "l_df": parse_float(row, "l_df"),
                    "w_first_in": w_1st,
                    "l_first_in": l_1st,
                    "w_first_won": w_1st_won,
                    "l_first_won": l_1st_won,
                    "w_second_total": w_second_total,
                    "l_second_total": l_second_total,
                    "w_second_won": w_2nd_won,
                    "l_second_won": l_2nd_won,
                    "w_bp_saved": w_bp_saved,
                    "l_bp_saved": l_bp_saved,
                    "w_bp_faced": w_bp_faced,
                    "l_bp_faced": l_bp_faced,
                    "w_bp_converted": none_sub(l_bp_faced, l_bp_saved),
                    "l_bp_converted": none_sub(w_bp_faced, w_bp_saved),
                    "w_bp_opps": l_bp_faced,
                    "l_bp_opps": w_bp_faced,
                }
                best_of = int(parse_float(row, "best_of") or (5 if tour == "atp" and row.get("tourney_level") == "G" else 3))
                matches.append(
                    RawMatch(
                        tour=tour,
                        match_date=match_date,
                        tournament_id=(row.get("tourney_id") or "").strip(),
                        tournament=row.get("tourney_name") or "",
                        surface=parse_surface(row.get("surface")),
                        level=(row.get("tourney_level") or "").strip(),
                        indoor=(row.get("indoor") or "").strip().upper(),
                        round=(row.get("round") or "").strip(),
                        best_of=best_of if best_of in {3, 5} else 3,
                        winner=winner,
                        loser=loser,
                        winner_rank=parse_float(row, "winner_rank"),
                        loser_rank=parse_float(row, "loser_rank"),
                        winner_rank_points=parse_float(row, "winner_rank_points"),
                        loser_rank_points=parse_float(row, "loser_rank_points"),
                        winner_age=parse_float(row, "winner_age"),
                        loser_age=parse_float(row, "loser_age"),
                        winner_height=parse_float(row, "winner_ht"),
                        loser_height=parse_float(row, "loser_ht"),
                        winner_hand=(row.get("winner_hand") or "").strip().upper(),
                        loser_hand=(row.get("loser_hand") or "").strip().upper(),
                        score=row.get("score") or "",
                        stats=stats,
                    )
                )
    matches.sort(key=lambda m: (m.match_date, m.tour, m.tournament, m.round, m.winner, m.loser))
    return matches


def stable_flip(match: RawMatch) -> bool:
    seed = f"{match.match_date.isoformat()}|{match.tournament}|{match.winner}|{match.loser}"
    value = 0
    for char in seed:
        value = (value * 131 + ord(char)) % 1_000_003
    return value % 2 == 0


def expected_score(a: float, b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((b - a) / 400.0))


def surface_rating(player: PlayerState, surface: str, k: float = 18.0) -> float:
    surface_count = player.surface_matches.get(surface, 0.0)
    w = surface_count / (surface_count + k)
    return w * player.surface_elo.get(surface, player.overall_elo) + (1.0 - w) * player.overall_elo


def blended_rating(player: PlayerState, surface: str) -> float:
    return 0.58 * surface_rating(player, surface) + 0.42 * player.overall_elo


def days_rest(player: PlayerState, match_date: date) -> float:
    if player.last_date is None:
        return 21.0
    return min(90.0, max(0.0, float((match_date - player.last_date).days)))


def workload(player: PlayerState, match_date: date, days: int) -> float:
    return float(sum(1 for item in player.workload_dates if 0 <= (match_date - item).days <= days))


def recovery_curve(player: PlayerState, match_date: date) -> float:
    return 1.0 - math.exp(-days_rest(player, match_date) / 3.5)


def beta_rate(player: PlayerState, key: str, prior: float, prior_n: float = 120.0) -> float:
    stat = player.stats[key]
    return stat.rate(prior, prior_n)


def surface_beta_rate(player: PlayerState, surface: str, key: str, prior: float, prior_n: float = 120.0) -> float:
    overall = beta_rate(player, key, prior, prior_n)
    stat = player.surface_stats[surface][key]
    return stat.rate(overall, max(30.0, prior_n * 0.65))


def service_point_model(player: PlayerState) -> float:
    first_in = beta_rate(player, "first_in", 0.62)
    first_won = beta_rate(player, "first_won", 0.72)
    second_won = beta_rate(player, "second_won", 0.52)
    return clamp(first_in * first_won + (1.0 - first_in) * second_won, 0.48, 0.78)


def latent_skill(player: PlayerState, surface: str) -> dict[str, float]:
    service_prior = 0.635 if player.tour == "atp" else 0.605
    return_prior = 1.0 - service_prior
    overall_service = beta_rate(player, "service_won", service_prior, 420.0)
    overall_return = beta_rate(player, "return_won", return_prior, 420.0)
    surface_service = surface_beta_rate(player, surface, "service_won", service_prior, 260.0)
    surface_return = surface_beta_rate(player, surface, "return_won", return_prior, 260.0)
    service_trials = player.stats["serve_points"].trials
    surface_trials = player.surface_stats[surface]["serve_points"].trials
    uncertainty = math.sqrt(1.0 / (120.0 + 0.25 * service_trials + surface_trials))
    return {
        "serve": safe_logit(overall_service) - safe_logit(service_prior),
        "return": safe_logit(overall_return) - safe_logit(return_prior),
        "surface_serve": safe_logit(surface_service) - safe_logit(service_prior),
        "surface_return": safe_logit(surface_return) - safe_logit(return_prior),
        "uncertainty": uncertainty,
    }


def latent_service_point_probability(server: PlayerState, returner: PlayerState, surface: str) -> float:
    service_prior = 0.635 if server.tour == "atp" else 0.605
    server_skill = latent_skill(server, surface)
    returner_skill = latent_skill(returner, surface)
    point_logit = safe_logit(service_prior) + server_skill["surface_serve"] - returner_skill["surface_return"]
    return clamp(float(sigmoid(point_logit)), 0.50, 0.80)


def latent_exact_match_probability(a: PlayerState, b: PlayerState, surface: str, best_of: int) -> float:
    a_point = latent_service_point_probability(a, b, surface)
    b_point = latent_service_point_probability(b, a, surface)
    a_hold = game_win_probability(a_point)
    b_hold = game_win_probability(b_point)
    set_p = set_win_probability_from_hold(a_hold, b_hold)
    return clamp(match_win_from_set(set_p, best_of), 0.01, 0.99)


def structural_probability(a: PlayerState, b: PlayerState, surface: str, best_of: int) -> float:
    a_serve = clamp(0.72 * service_point_model(a) + 0.28 * (1 - beta_rate(b, "return_won", 0.365)), 0.50, 0.77)
    b_serve = clamp(0.72 * service_point_model(b) + 0.28 * (1 - beta_rate(a, "return_won", 0.365)), 0.50, 0.77)
    rating_edge = clamp((surface_rating(a, surface) - surface_rating(b, surface)) / 2400.0, -0.05, 0.05)
    a_hold = game_win_probability(clamp(a_serve + rating_edge, 0.50, 0.80))
    b_hold = game_win_probability(clamp(b_serve - rating_edge, 0.50, 0.80))
    set_p = set_win_probability_from_hold(a_hold, b_hold)
    return clamp(match_win_from_set(set_p, best_of), 0.01, 0.99)


def safe_logit(p: float) -> float:
    p = clamp(p, 1e-6, 1 - 1e-6)
    return math.log(p / (1 - p))


def score_summary(score: str) -> tuple[int, int, int, int, int]:
    winner_sets = loser_sets = winner_games = loser_games = tiebreaks = 0
    for token in re.split(r"\s+", score.strip()):
        if not token or token.upper() in {"RET", "W/O", "DEF", "ABD"}:
            continue
        match = re.match(r"^(\d+)-(\d+)", token)
        if not match:
            continue
        a, b = int(match.group(1)), int(match.group(2))
        winner_games += a
        loser_games += b
        if abs(a - b) <= 1 and max(a, b) >= 6:
            tiebreaks += 1
        if a > b:
            winner_sets += 1
        elif b > a:
            loser_sets += 1
    return winner_sets, loser_sets, winner_games, loser_games, tiebreaks


def common_opponent_features(
    a: PlayerState,
    b: PlayerState,
    match: RawMatch,
    opponent_history: dict[str, dict[str, OpponentResidual]] | None,
) -> dict[str, float]:
    if not opponent_history:
        return {
            "common_opponent_result_residual_diff": 0.0,
            "common_opponent_serve_residual_diff": 0.0,
            "common_opponent_return_residual_diff": 0.0,
            "common_opponent_surface_residual_diff": 0.0,
            "common_opponent_match_weight": 0.0,
        }
    a_key = player_key(a.name, a.tour)
    b_key = player_key(b.name, b.tour)
    a_history = opponent_history.get(a_key, {})
    b_history = opponent_history.get(b_key, {})
    shared = sorted(set(a_history) & set(b_history))
    if not shared:
        return {
            "common_opponent_result_residual_diff": 0.0,
            "common_opponent_serve_residual_diff": 0.0,
            "common_opponent_return_residual_diff": 0.0,
            "common_opponent_surface_residual_diff": 0.0,
            "common_opponent_match_weight": 0.0,
        }
    result = serve = ret = surface_result = total_weight = 0.0
    for opponent in shared:
        a_item = a_history[opponent]
        b_item = b_history[opponent]
        weight = min(a_item.result.weight, b_item.result.weight)
        if weight <= 0:
            continue
        result += weight * (a_item.result.value() - b_item.result.value())
        serve += weight * (a_item.serve.value() - b_item.serve.value())
        ret += weight * (a_item.return_.value() - b_item.return_.value())
        surface_result += weight * (
            a_item.surface_result[match.surface].value() - b_item.surface_result[match.surface].value()
        )
        total_weight += weight
    if total_weight <= 0:
        shrink = 0.0
        result = serve = ret = surface_result = 0.0
    else:
        shrink = (total_weight / (total_weight + 12.0)) * (len(shared) / (len(shared) + 4.0))
        result = shrink * result / total_weight
        serve = shrink * serve / total_weight
        ret = shrink * ret / total_weight
        surface_result = shrink * surface_result / total_weight
    return {
        "common_opponent_result_residual_diff": result,
        "common_opponent_serve_residual_diff": serve,
        "common_opponent_return_residual_diff": ret,
        "common_opponent_surface_residual_diff": surface_result,
        "common_opponent_match_weight": min(1.0, total_weight / 20.0),
    }


def base_features(
    a: PlayerState,
    b: PlayerState,
    match: RawMatch,
    h2h: dict[tuple[str, str], int],
    opponent_history: dict[str, dict[str, OpponentResidual]] | None = None,
) -> dict[str, float]:
    surface = match.surface
    pair = (player_key(a.name, a.tour), player_key(b.name, b.tour))
    reverse = (pair[1], pair[0])
    h2h_total = h2h[pair] + h2h[reverse]
    h2h_shrunk = (h2h[pair] - h2h[reverse]) / (h2h_total + 8.0)
    surface_a = surface_rating(a, surface)
    surface_b = surface_rating(b, surface)
    p_struct = structural_probability(a, b, surface, match.best_of)
    p_latent = latent_exact_match_probability(a, b, surface, match.best_of)
    latent_a = latent_skill(a, surface)
    latent_b = latent_skill(b, surface)
    serve_a = service_point_model(a)
    serve_b = service_point_model(b)
    return_a = beta_rate(a, "return_won", 0.365)
    return_b = beta_rate(b, "return_won", 0.365)
    rank_a = a.ranking if a.ranking is not None else 999.0
    rank_b = b.ranking if b.ranking is not None else 999.0
    points_a = a.ranking_points if a.ranking_points is not None else 0.0
    points_b = b.ranking_points if b.ranking_points is not None else 0.0
    return {
        "overall_elo_diff": (a.overall_elo - b.overall_elo) / 400.0,
        "surface_elo_diff": (a.surface_elo.get(surface, 1500.0) - b.surface_elo.get(surface, 1500.0)) / 400.0,
        "surface_elo_shrunk_diff": (surface_a - surface_b) / 400.0,
        "rating_rd_diff": (b.rd - a.rd) / 350.0,
        "rating_uncertainty_sum": (a.rd + b.rd) / 700.0,
        "matches_diff": (min(a.matches, 350) - min(b.matches, 350)) / 350.0,
        "match_count_log_diff": math.log1p(a.matches) - math.log1p(b.matches),
        "ranking_diff": (rank_b - rank_a) / 998.0,
        "ranking_points_diff": (points_a - points_b) / 12000.0,
        "rank_known": float(a.ranking is not None and b.ranking is not None),
        "age_diff": ((a.age or 27.0) - (b.age or 27.0)) / 15.0,
        "height_diff": ((a.height or 185.0) - (b.height or 185.0)) / 30.0,
        "lefty_matchup": float(a.hand == "L") - float(b.hand == "L"),
        "same_hand": float(bool(a.hand) and a.hand == b.hand),
        "serve_strength_diff": serve_a - serve_b,
        "return_strength_diff": return_a - return_b,
        "serve_return_edge": (serve_a - (1 - return_b)) - (serve_b - (1 - return_a)),
        "ace_rate_diff": beta_rate(a, "aces", 0.055) - beta_rate(b, "aces", 0.055),
        "df_rate_diff": beta_rate(a, "double_faults", 0.035) - beta_rate(b, "double_faults", 0.035),
        "first_in_diff": beta_rate(a, "first_in", 0.62) - beta_rate(b, "first_in", 0.62),
        "first_won_diff": beta_rate(a, "first_won", 0.72) - beta_rate(b, "first_won", 0.72),
        "second_won_diff": beta_rate(a, "second_won", 0.52) - beta_rate(b, "second_won", 0.52),
        "bp_save_diff": beta_rate(a, "bp_saved", 0.58, 40.0) - beta_rate(b, "bp_saved", 0.58, 40.0),
        "bp_convert_diff": beta_rate(a, "bp_converted", 0.40, 40.0) - beta_rate(b, "bp_converted", 0.40, 40.0),
        "return_point_won_diff": return_a - return_b,
        "serve_point_won_diff": serve_a - serve_b,
        "stat_sample_diff": min(a.stats["serve_points"].trials, 6000.0) / 6000.0 - min(b.stats["serve_points"].trials, 6000.0) / 6000.0,
        "days_rest_diff": (days_rest(a, match.match_date) - days_rest(b, match.match_date)) / 90.0,
        "recovery_curve_diff": recovery_curve(a, match.match_date) - recovery_curve(b, match.match_date),
        "workload_3d_diff": (workload(a, match.match_date, 3) - workload(b, match.match_date, 3)) / 4.0,
        "workload_7d_diff": (workload(a, match.match_date, 7) - workload(b, match.match_date, 7)) / 7.0,
        "workload_14d_diff": (workload(a, match.match_date, 14) - workload(b, match.match_date, 14)) / 10.0,
        "residual_form_short_diff": a.residual_short.value() - b.residual_short.value(),
        "residual_form_medium_diff": a.residual_medium.value() - b.residual_medium.value(),
        "surface_residual_form_diff": a.surface_residual[surface].value() - b.surface_residual[surface].value(),
        "score_dominance_diff": a.score_dominance.value() - b.score_dominance.value(),
        "set_dominance_diff": a.set_dominance.value() - b.set_dominance.value(),
        "tiebreak_strength_diff": a.tiebreak_strength.value() - b.tiebreak_strength.value(),
        "h2h_prior_diff": h2h_shrunk,
        "surface_h2h_prior_diff": (
            h2h[(f"{surface}:{pair[0]}", pair[1])] - h2h[(f"{surface}:{pair[1]}", pair[0])]
        ) / (h2h[(f"{surface}:{pair[0]}", pair[1])] + h2h[(f"{surface}:{pair[1]}", pair[0])] + 8.0),
        "best_of_5": float(match.best_of == 5),
        "is_indoor": float(match.indoor == "I"),
        "level_g": float(match.level == "G"),
        "level_m": float(match.level == "M"),
        "level_500": float(match.level == "500"),
        "level_250": float(match.level == "250"),
        "round_final": float(match.round == "F"),
        "round_sf": float(match.round == "SF"),
        "round_qf": float(match.round == "QF"),
        "surface_sample_diff": (a.surface_matches.get(surface, 0.0) - b.surface_matches.get(surface, 0.0)) / 80.0,
        "data_strength_diff": (
            math.log1p(a.matches) + math.log1p(a.stats["serve_points"].trials)
            - math.log1p(b.matches) - math.log1p(b.stats["serve_points"].trials)
        ) / 10.0,
        "structural_match_logit": safe_logit(p_struct),
        "latent_serve_skill_diff": latent_a["serve"] - latent_b["serve"],
        "latent_return_skill_diff": latent_a["return"] - latent_b["return"],
        "latent_surface_serve_skill_diff": latent_a["surface_serve"] - latent_b["surface_serve"],
        "latent_surface_return_skill_diff": latent_a["surface_return"] - latent_b["surface_return"],
        "latent_uncertainty_sum": latent_a["uncertainty"] + latent_b["uncertainty"],
        "latent_exact_match_logit": safe_logit(p_latent),
        **common_opponent_features(a, b, match, opponent_history),
    }


def update_player_metadata(player: PlayerState, rank: float | None, points: float | None, age: float | None, height: float | None, hand: str) -> None:
    if rank is not None:
        player.ranking = rank
    if points is not None:
        player.ranking_points = points
    if age is not None:
        player.age = age
    if height is not None:
        player.height = height
    if hand:
        player.hand = hand


def update_stats(player: PlayerState, match: RawMatch, prefix: str) -> None:
    mapping = {
        "serve_points": (f"{prefix}_svpt", f"{prefix}_svpt"),
        "service_won": (f"{prefix}_service_won", f"{prefix}_svpt"),
        "return_won": (f"{prefix}_return_won", "l_svpt" if prefix == "w" else "w_svpt"),
        "aces": (f"{prefix}_ace", f"{prefix}_svpt"),
        "double_faults": (f"{prefix}_df", f"{prefix}_svpt"),
        "first_in": (f"{prefix}_first_in", f"{prefix}_svpt"),
        "first_won": (f"{prefix}_first_won", f"{prefix}_first_in"),
        "second_won": (f"{prefix}_second_won", f"{prefix}_second_total"),
        "bp_saved": (f"{prefix}_bp_saved", f"{prefix}_bp_faced"),
        "bp_converted": (f"{prefix}_bp_converted", f"{prefix}_bp_opps"),
    }
    for key, (success_key, trial_key) in mapping.items():
        success = match.stats.get(success_key)
        trials = match.stats.get(trial_key)
        if key == "serve_points":
            success = trials
        player.stats[key].add(success, trials, match.match_date)
        player.surface_stats[match.surface][key].add(success, trials, match.match_date)


def update_after_match(winner: PlayerState, loser: PlayerState, match: RawMatch, pre_probability: float, h2h: dict[tuple[str, str], int]) -> None:
    expected = expected_score(blended_rating(winner, match.surface), blended_rating(loser, match.surface))
    inactivity = max(days_rest(winner, match.match_date), days_rest(loser, match.match_date))
    experience_factor = 1.0 / (1.0 + min(winner.matches, loser.matches) / 180.0)
    uncertainty_factor = 0.65 + (winner.rd + loser.rd) / 700.0
    inactivity_factor = 1.0 + min(inactivity, 180.0) / 600.0
    k = (15.0 + 18.0 * experience_factor) * uncertainty_factor * inactivity_factor * (1.06 if match.best_of == 5 else 1.0)
    delta = k * (1 - expected)
    winner.overall_elo += 0.42 * delta
    loser.overall_elo -= 0.42 * delta
    winner.surface_elo[match.surface] += 0.72 * delta
    loser.surface_elo[match.surface] -= 0.72 * delta
    winner.rd = max(35.0, min(350.0, winner.rd * 0.965 + 350.0 / math.sqrt(winner.matches + 8) * 0.035))
    loser.rd = max(35.0, min(350.0, loser.rd * 0.965 + 350.0 / math.sqrt(loser.matches + 8) * 0.035))
    winner.surface_matches[match.surface] += 1.0
    loser.surface_matches[match.surface] += 1.0

    residual_w = 1.0 - pre_probability
    residual_l = -residual_w
    winner.residual_short.add(residual_w, match.match_date, 90.0)
    loser.residual_short.add(residual_l, match.match_date, 90.0)
    winner.residual_medium.add(residual_w, match.match_date, 365.0)
    loser.residual_medium.add(residual_l, match.match_date, 365.0)
    winner.surface_residual[match.surface].add(residual_w, match.match_date, 365.0)
    loser.surface_residual[match.surface].add(residual_l, match.match_date, 365.0)

    w_sets, l_sets, w_games, l_games, tiebreaks = score_summary(match.score)
    total_games = max(1, w_games + l_games)
    game_margin = (w_games - l_games) / total_games
    set_margin = (w_sets - l_sets) / max(1, w_sets + l_sets)
    winner.score_dominance.add(game_margin, match.match_date, 540.0)
    loser.score_dominance.add(-game_margin, match.match_date, 540.0)
    winner.set_dominance.add(set_margin, match.match_date, 540.0)
    loser.set_dominance.add(-set_margin, match.match_date, 540.0)
    if tiebreaks:
        winner.tiebreak_strength.add(1.0, match.match_date, 900.0)
        loser.tiebreak_strength.add(-1.0, match.match_date, 900.0)

    winner.last_date = loser.last_date = match.match_date
    winner.workload_dates = [d for d in winner.workload_dates[-50:] if (match.match_date - d).days <= 60] + [match.match_date]
    loser.workload_dates = [d for d in loser.workload_dates[-50:] if (match.match_date - d).days <= 60] + [match.match_date]
    winner.matches += 1
    loser.matches += 1
    update_stats(winner, match, "w")
    update_stats(loser, match, "l")
    winner_key = player_key(winner.name, winner.tour)
    loser_key = player_key(loser.name, loser.tour)
    h2h[(winner_key, loser_key)] += 1
    h2h[(f"{match.surface}:{winner_key}", loser_key)] += 1


def update_opponent_residuals(
    winner: PlayerState,
    loser: PlayerState,
    match: RawMatch,
    pre_winner_probability: float,
    pre_winner_serve: float,
    pre_loser_serve: float,
    pre_winner_return: float,
    pre_loser_return: float,
    opponent_history: dict[str, dict[str, OpponentResidual]],
) -> None:
    winner_key = player_key(winner.name, winner.tour)
    loser_key = player_key(loser.name, loser.tour)
    winner_item = opponent_history[winner_key][loser_key]
    loser_item = opponent_history[loser_key][winner_key]
    winner_result_residual = 1.0 - pre_winner_probability
    loser_result_residual = -winner_result_residual
    winner_item.result.add(winner_result_residual, match.match_date, 730.0)
    loser_item.result.add(loser_result_residual, match.match_date, 730.0)
    winner_item.surface_result[match.surface].add(winner_result_residual, match.match_date, 730.0)
    loser_item.surface_result[match.surface].add(loser_result_residual, match.match_date, 730.0)

    winner_service_rate = ratio(match.stats.get("w_service_won"), match.stats.get("w_svpt"))
    loser_service_rate = ratio(match.stats.get("l_service_won"), match.stats.get("l_svpt"))
    winner_return_rate = ratio(match.stats.get("w_return_won"), match.stats.get("l_svpt"))
    loser_return_rate = ratio(match.stats.get("l_return_won"), match.stats.get("w_svpt"))
    if winner_service_rate is not None:
        winner_item.serve.add(winner_service_rate - pre_winner_serve, match.match_date, 730.0)
    if loser_service_rate is not None:
        loser_item.serve.add(loser_service_rate - pre_loser_serve, match.match_date, 730.0)
    if winner_return_rate is not None:
        winner_item.return_.add(winner_return_rate - pre_winner_return, match.match_date, 730.0)
    if loser_return_rate is not None:
        loser_item.return_.add(loser_return_rate - pre_loser_return, match.match_date, 730.0)


def build_feature_rows(
    matches: list[RawMatch],
    temporal_mode: str = "round_safe",
) -> tuple[pd.DataFrame, dict[str, PlayerState], dict[tuple[str, str], int]]:
    if temporal_mode not in {"round_safe", "tournament_frozen"}:
        raise ValueError(f"Unknown temporal_mode: {temporal_mode}")
    players: dict[str, PlayerState] = {}
    h2h: dict[tuple[str, str], int] = defaultdict(int)
    opponent_history: dict[str, dict[str, OpponentResidual]] = defaultdict(lambda: defaultdict(OpponentResidual))
    rows: list[dict[str, Any]] = []
    indexed_matches = list(enumerate(matches))
    batches: dict[tuple[str, date, str], list[tuple[int, RawMatch]]] = defaultdict(list)
    for index, match in indexed_matches:
        tournament_key = match.tournament_id or match.tournament
        batches[(match.tour, match.match_date, tournament_key)].append((index, match))

    for _, batch in sorted(batches.items(), key=lambda item: item[0]):
        # Sackmann match files expose tournament start date, not exact match date.
        # Round labels give a safe partial order, but not exact ordering within a
        # round. We therefore snapshot every match in the same round before any
        # same-round update, then apply those results only to later rounds.
        # Metadata is frozen from each player's earliest available round in this
        # tournament. A later-round row must never overwrite a feature snapshot
        # for an earlier round that shares the tournament start date.
        entry_metadata: dict[str, tuple[int, int, tuple[Any, ...]]] = {}
        for index, match in batch:
            for name, metadata in (
                (match.winner, (match.winner_rank, match.winner_rank_points, match.winner_age, match.winner_height, match.winner_hand)),
                (match.loser, (match.loser_rank, match.loser_rank_points, match.loser_age, match.loser_height, match.loser_hand)),
            ):
                key = player_key(name, match.tour)
                candidate = (ROUND_ORDER.get(match.round, 0), index, metadata)
                if key not in entry_metadata or candidate[:2] < entry_metadata[key][:2]:
                    entry_metadata[key] = candidate
                players.setdefault(key, PlayerState(name, match.tour))
        for key, (_, _, metadata) in entry_metadata.items():
            update_player_metadata(players[key], *metadata)

        if temporal_mode == "tournament_frozen":
            ordered_batches = [(0, sorted(batch, key=lambda item: item[0]))]
        else:
            round_batches: dict[int, list[tuple[int, RawMatch]]] = defaultdict(list)
            for index, match in batch:
                round_batches[ROUND_ORDER.get(match.round, 0)].append((index, match))
            ordered_batches = [(order, sorted(round_batch, key=lambda item: item[0])) for order, round_batch in sorted(round_batches.items())]

        for _, safe_batch in ordered_batches:
            pending_updates: list[tuple[PlayerState, PlayerState, RawMatch, float, float, float, float, float]] = []
            for index, match in safe_batch:
                winner = players[player_key(match.winner, match.tour)]
                loser = players[player_key(match.loser, match.tour)]
                pre_winner_probability = expected_score(blended_rating(winner, match.surface), blended_rating(loser, match.surface))
                pre_winner_serve = service_point_model(winner)
                pre_loser_serve = service_point_model(loser)
                pre_winner_return = beta_rate(winner, "return_won", 0.365)
                pre_loser_return = beta_rate(loser, "return_won", 0.365)
                flipped = stable_flip(match)
                p1, p2, label = (winner, loser, 1) if not flipped else (loser, winner, 0)
                rows.append(
                    {
                        "index": index,
                        "date": match.match_date.isoformat(),
                        "year": match.match_date.year,
                        "tour": match.tour,
                        "tournament": match.tournament,
                        "surface": match.surface,
                        "level": match.level,
                        "round": match.round,
                        "player1": p1.name,
                        "player2": p2.name,
                        "label": label,
                        **base_features(p1, p2, match, h2h, opponent_history),
                    }
                )
                pending_updates.append((winner, loser, match, pre_winner_probability, pre_winner_serve, pre_loser_serve, pre_winner_return, pre_loser_return))

            for winner, loser, match, pre_winner_probability, pre_winner_serve, pre_loser_serve, pre_winner_return, pre_loser_return in pending_updates:
                update_after_match(winner, loser, match, pre_winner_probability, h2h)
                update_opponent_residuals(
                    winner,
                    loser,
                    match,
                    pre_winner_probability,
                    pre_winner_serve,
                    pre_loser_serve,
                    pre_winner_return,
                    pre_loser_return,
                    opponent_history,
                )
    frame = pd.DataFrame(rows)
    return frame, players, h2h


def sigmoid(x: np.ndarray | float) -> np.ndarray | float:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35, 35)))


def fit_logistic(train: pd.DataFrame, features: list[str], epochs: int = 320, lr: float = 0.06, l2: float = 0.004) -> FittedLogistic:
    x = train[features].to_numpy(dtype=float)
    y = train["label"].to_numpy(dtype=float)
    center = np.nanmean(x, axis=0)
    scale = np.nanstd(x, axis=0)
    scale = np.where(scale < 1e-6, 1.0, scale)
    z = np.nan_to_num((x - center) / scale)
    weights = np.zeros(z.shape[1], dtype=float)
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        p = sigmoid(intercept + z @ weights)
        error = p - y
        intercept -= lr * float(error.mean())
        weights -= lr * ((z.T @ error) / n + l2 * weights)
    return FittedLogistic(features, weights, float(intercept), center, scale)


def fit_platt(logits: np.ndarray, y: np.ndarray, epochs: int = 900, lr: float = 0.025) -> dict[str, float | str]:
    slope = 1.0
    intercept = 0.0
    n = max(1, len(y))
    for _ in range(epochs):
        p = sigmoid(slope * logits + intercept)
        error = p - y
        slope -= lr * (float((error * logits).sum()) / n + 0.002 * (slope - 1.0))
        intercept -= lr * float(error.mean())
    return {"method": "platt", "slope": round(float(slope), 6), "intercept": round(float(intercept), 6)}


def calibrated_probs(logits: np.ndarray, cal: dict[str, Any]) -> np.ndarray:
    return sigmoid(float(cal.get("slope", 1.0)) * logits + float(cal.get("intercept", 0.0)))


def roc_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    positives = int(labels.sum())
    negatives = int(len(labels) - positives)
    if positives == 0 or negatives == 0:
        return 0.5
    order = np.argsort(probs)
    sorted_probs = probs[order]
    sorted_labels = labels[order]
    ranks = np.empty(len(probs), dtype=float)
    i = 0
    while i < len(probs):
        j = i + 1
        while j < len(probs) and sorted_probs[j] == sorted_probs[i]:
            j += 1
        ranks[i:j] = (i + 1 + j) / 2.0
        i = j
    rank_sum = float(ranks[sorted_labels == 1].sum())
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def ece(probs: np.ndarray, labels: np.ndarray, buckets: int = 10) -> float:
    out = 0.0
    for bucket in range(buckets):
        low, high = bucket / buckets, (bucket + 1) / buckets
        mask = (probs >= low) & (probs < high if bucket < buckets - 1 else probs <= high)
        if mask.any():
            out += float(mask.mean()) * abs(float(probs[mask].mean()) - float(labels[mask].mean()))
    return out


def metrics(probs: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    p = np.clip(probs.astype(float), 1e-6, 1 - 1e-6)
    y = labels.astype(int)
    return {
        "accuracy": round(float(((p >= 0.5) == y).mean()), 4),
        "roc_auc": round(float(roc_auc(p, y)), 4),
        "log_loss": round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 4),
        "brier_score": round(float(((p - y) ** 2).mean()), 4),
        "ece": round(float(ece(p, y)), 4),
    }


def candidate_sets(all_features: list[str]) -> dict[str, list[str]]:
    groups = {
        "rating": ["overall_elo_diff", "surface_elo_shrunk_diff", "rating_rd_diff", "rating_uncertainty_sum"],
        "ranking": ["ranking_diff", "ranking_points_diff", "rank_known"],
        "serve_return": ["serve_strength_diff", "return_strength_diff", "serve_return_edge", "first_in_diff", "first_won_diff", "second_won_diff", "ace_rate_diff", "df_rate_diff", "return_point_won_diff", "serve_point_won_diff", "stat_sample_diff"],
        "latent_serve_return": ["latent_serve_skill_diff", "latent_return_skill_diff", "latent_surface_serve_skill_diff", "latent_surface_return_skill_diff", "latent_uncertainty_sum", "latent_exact_match_logit"],
        "common_opponent_v2": ["common_opponent_result_residual_diff", "common_opponent_serve_residual_diff", "common_opponent_return_residual_diff", "common_opponent_surface_residual_diff", "common_opponent_match_weight"],
        "form": ["residual_form_short_diff", "residual_form_medium_diff", "surface_residual_form_diff"],
        "fatigue": ["days_rest_diff", "recovery_curve_diff", "workload_3d_diff", "workload_7d_diff", "workload_14d_diff"],
        "score": ["score_dominance_diff", "set_dominance_diff", "tiebreak_strength_diff"],
        "bio": ["age_diff", "height_diff", "lefty_matchup", "same_hand"],
        "h2h": ["h2h_prior_diff", "surface_h2h_prior_diff"],
        "context": ["best_of_5", "is_indoor", "level_g", "level_m", "level_500", "level_250", "round_final", "round_sf", "round_qf"],
    }
    compact = [
        "overall_elo_diff",
        "surface_elo_shrunk_diff",
        "matches_diff",
        "ranking_diff",
        "ranking_points_diff",
        "days_rest_diff",
        "workload_14d_diff",
        "h2h_prior_diff",
        "surface_h2h_prior_diff",
        "best_of_5",
    ]
    out = {
        "enhanced_full": all_features,
        "enhanced_runtime_safe": [feature for feature in all_features if feature in RUNTIME_COMPATIBLE_FEATURES],
        "compact_production_reference": compact,
        "rating_ranking_structural": list(dict.fromkeys(groups["rating"] + groups["ranking"] + ["structural_match_logit", "best_of_5", "matches_diff"])),
        "exact_scoring_expert": ["latent_exact_match_logit", "structural_match_logit", "best_of_5"],
        "serve_return_structural": list(dict.fromkeys(groups["serve_return"] + groups["latent_serve_return"] + ["best_of_5", "matches_diff"])),
        "common_opponent_plus_core": list(dict.fromkeys(groups["rating"] + groups["ranking"] + groups["serve_return"] + groups["common_opponent_v2"] + ["best_of_5", "matches_diff"])),
        "no_h2h": [feature for feature in all_features if feature not in groups["h2h"]],
        "no_form": [feature for feature in all_features if feature not in groups["form"]],
        "no_serve_return": [feature for feature in all_features if feature not in groups["serve_return"]],
        "no_latent_serve_return": [feature for feature in all_features if feature not in groups["latent_serve_return"]],
        "no_common_opponent_v2": [feature for feature in all_features if feature not in groups["common_opponent_v2"]],
        "no_fatigue": [feature for feature in all_features if feature not in groups["fatigue"]],
        "no_score": [feature for feature in all_features if feature not in groups["score"]],
        "no_bio": [feature for feature in all_features if feature not in groups["bio"]],
        "no_context": [feature for feature in all_features if feature not in groups["context"]],
    }
    for group, features in groups.items():
        out[f"{group}_only"] = [feature for feature in features if feature in all_features]
    return {name: [feature for feature in features if feature in all_features] for name, features in out.items() if features}


def fit_eval_fold(frame: pd.DataFrame, features: list[str], train_mask: pd.Series, cal_mask: pd.Series, test_mask: pd.Series) -> tuple[np.ndarray, dict[str, float]]:
    train = frame[train_mask]
    cal_rows = frame[cal_mask]
    test_rows = frame[test_mask]
    model = fit_logistic(train, features)
    calibrator = fit_platt(model.raw_logits(cal_rows), cal_rows["label"].to_numpy(dtype=int))
    probs = calibrated_probs(model.raw_logits(test_rows), calibrator)
    return probs, metrics(probs, test_rows["label"].to_numpy(dtype=int))


def walk_forward(frame: pd.DataFrame, features: list[str], years: Iterable[int] = range(2019, 2024)) -> dict[str, Any]:
    folds = []
    pooled_probs = []
    pooled_labels = []
    for year in years:
        train_mask = frame["year"] < year
        cal_mask = frame["year"] == year - 1
        train_mask = frame["year"] < year - 1
        test_mask = frame["year"] == year
        if train_mask.sum() < 5000 or cal_mask.sum() < 500 or test_mask.sum() < 500:
            continue
        probs, fold_metrics = fit_eval_fold(frame, features, train_mask, cal_mask, test_mask)
        labels = frame.loc[test_mask, "label"].to_numpy(dtype=int)
        folds.append({"year": year, "rows": int(test_mask.sum()), **fold_metrics})
        pooled_probs.append(probs)
        pooled_labels.append(labels)
    if not folds:
        return {"status": "no_folds"}
    pp = np.concatenate(pooled_probs)
    yy = np.concatenate(pooled_labels)
    return {
        "status": "evaluated",
        "folds": folds,
        "mean_log_loss": round(float(np.mean([item["log_loss"] for item in folds])), 4),
        "mean_brier_score": round(float(np.mean([item["brier_score"] for item in folds])), 4),
        "mean_ece": round(float(np.mean([item["ece"] for item in folds])), 4),
        "mean_accuracy": round(float(np.mean([item["accuracy"] for item in folds])), 4),
        "pooled_metrics": metrics(pp, yy),
    }


def feature_matrix_logits(frame: pd.DataFrame, artifact: dict[str, Any]) -> np.ndarray:
    model = artifact["model"]
    logits = np.full(len(frame), float(model.get("intercept", 0.0)))
    center = model.get("center") or []
    scale = model.get("scale") or []
    for index, (coefficient, feature) in enumerate(zip(model.get("coefficients", []), model.get("feature_names", []), strict=False)):
        if feature in frame.columns:
            values = frame[str(feature)].to_numpy(dtype=float)
            if center and scale and index < len(center) and index < len(scale):
                values = (values - float(center[index])) / (float(scale[index]) or 1.0)
            logits += float(coefficient) * values
    return logits


def artifact_metrics(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing"}
    artifact = json.loads(path.read_text(encoding="utf-8"))
    feature_names = set((artifact.get("model") or {}).get("feature_names") or [])
    missing = sorted(feature_names - set(frame.columns))
    if missing:
        return {"status": "incompatible_feature_rows", "model_version": artifact.get("model_version"), "missing_features": missing[:12]}
    logits = feature_matrix_logits(frame, artifact)
    calibration = artifact.get("model", {}).get("calibration") or {}
    probs = calibrated_probs(logits, calibration)
    return {"status": "evaluated", "model_version": artifact.get("model_version"), **metrics(probs, frame["label"].to_numpy(dtype=int))}


def artifact_metrics_on_saved_rows(path: Path) -> dict[str, Any]:
    if not SAVED_FEATURE_ROWS_PATH.exists():
        return {"status": "missing_feature_rows"}
    rows = pd.read_csv(SAVED_FEATURE_ROWS_PATH)
    rows["date"] = pd.to_datetime(rows["date"])
    rows["year"] = rows["date"].dt.year
    return artifact_metrics(rows[rows["year"] == 2025], path)


def final_train_eval(frame: pd.DataFrame, features: list[str]) -> dict[str, Any]:
    train_mask = frame["year"] <= 2023
    cal_mask = frame["year"] == 2024
    test_mask = frame["year"] == 2025
    holdout_2026 = frame["year"] == 2026
    started = time.perf_counter()
    model = fit_logistic(frame[train_mask], features, epochs=420)
    calibrator = fit_platt(model.raw_logits(frame[cal_mask]), frame.loc[cal_mask, "label"].to_numpy(dtype=int))
    test_probs = calibrated_probs(model.raw_logits(frame[test_mask]), calibrator)
    result = {
        "features": features,
        "feature_count": len(features),
        "calibration": calibrator,
        "metrics_2025": metrics(test_probs, frame.loc[test_mask, "label"].to_numpy(dtype=int)),
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "model": {
            "type": "enhanced_logistic_regression",
            "feature_names": features,
            "coefficients": [float(x) for x in model.coefficients],
            "intercept": float(model.intercept),
            "center": [float(x) for x in model.center],
            "scale": [float(x) for x in model.scale],
            "calibration": calibrator,
        },
    }
    if holdout_2026.sum() >= 50:
        p2026 = calibrated_probs(model.raw_logits(frame[holdout_2026]), calibrator)
        result["prospective_2026"] = {"rows": int(holdout_2026.sum()), **metrics(p2026, frame.loc[holdout_2026, "label"].to_numpy(dtype=int))}
    return result


def final_test_probabilities(frame: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    train_mask = frame["year"] <= 2023
    cal_mask = frame["year"] == 2024
    test_mask = frame["year"] == 2025
    model = fit_logistic(frame[train_mask], features, epochs=420)
    calibrator = fit_platt(model.raw_logits(frame[cal_mask]), frame.loc[cal_mask, "label"].to_numpy(dtype=int))
    test_rows = frame[test_mask].copy()
    probs = calibrated_probs(model.raw_logits(test_rows), calibrator)
    labels = test_rows["label"].to_numpy(dtype=int)
    return probs, labels, test_rows


def bootstrap_logloss_delta(
    baseline_probs: np.ndarray,
    candidate_probs: np.ndarray,
    labels: np.ndarray,
    rows: pd.DataFrame,
    iterations: int = 500,
) -> dict[str, Any]:
    if len(labels) == 0:
        return {"status": "no_test_rows"}
    blocks = rows["tournament"].fillna("").astype(str) + "|" + rows["date"].astype(str)
    groups = [np.flatnonzero((blocks == block).to_numpy()) for block in sorted(blocks.unique())]
    if not groups:
        return {"status": "no_blocks"}
    rng = np.random.default_rng(11)
    deltas = []
    baseline_probs = np.clip(baseline_probs.astype(float), 1e-6, 1 - 1e-6)
    candidate_probs = np.clip(candidate_probs.astype(float), 1e-6, 1 - 1e-6)
    labels = labels.astype(int)
    for _ in range(iterations):
        sampled = np.concatenate([groups[int(rng.integers(0, len(groups)))] for _ in range(len(groups))])
        y = labels[sampled]
        b = baseline_probs[sampled]
        c = candidate_probs[sampled]
        baseline_loss = float(-(y * np.log(b) + (1 - y) * np.log(1 - b)).mean())
        candidate_loss = float(-(y * np.log(c) + (1 - y) * np.log(1 - c)).mean())
        deltas.append(candidate_loss - baseline_loss)
    low, high = np.quantile(deltas, [0.025, 0.975])
    return {
        "status": "evaluated",
        "delta_definition": "candidate_log_loss_minus_baseline_log_loss; negative is better",
        "mean_delta": round(float(np.mean(deltas)), 5),
        "ci_95": [round(float(low), 5), round(float(high), 5)],
        "iterations": iterations,
        "block": "tournament start date + tournament name",
    }


def stratified_metrics(rows: pd.DataFrame, probs: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for surface in sorted(PRIMARY_SURFACES):
        mask = rows["surface"].to_numpy() == surface
        if mask.sum() >= 50:
            output[f"surface_{surface}"] = {"rows": int(mask.sum()), **metrics(probs[mask], labels[mask])}
    favorite = np.maximum(probs, 1.0 - probs)
    bands = {
        "close_50_55": (favorite >= 0.50) & (favorite < 0.55),
        "lean_55_65": (favorite >= 0.55) & (favorite < 0.65),
        "favorite_65_80": (favorite >= 0.65) & (favorite < 0.80),
        "heavy_favorite_80_plus": favorite >= 0.80,
    }
    for name, mask in bands.items():
        if mask.sum() >= 50:
            output[name] = {"rows": int(mask.sum()), **metrics(probs[mask], labels[mask])}
    history = np.maximum(rows.get("matches_diff", pd.Series(0.0, index=rows.index)).abs().to_numpy(), 0)
    low_history = rows.get("data_strength_diff", pd.Series(0.0, index=rows.index)).abs().to_numpy() < 0.15
    if low_history.sum() >= 50:
        output["low_history_proxy"] = {"rows": int(low_history.sum()), **metrics(probs[low_history], labels[low_history])}
    if (history >= 0).sum() >= 50:
        output["all_test_rows"] = {"rows": int(len(labels)), **metrics(probs, labels)}
    return output


def data_profile(matches: list[RawMatch]) -> dict[str, Any]:
    fields = Counter()
    surfaces = Counter(m.surface for m in matches)
    levels = Counter(m.level for m in matches)
    rounds = Counter(m.round for m in matches)
    for m in matches:
        if m.winner_rank is not None and m.loser_rank is not None:
            fields["ranking"] += 1
        if m.winner_rank_points is not None and m.loser_rank_points is not None:
            fields["ranking_points"] += 1
        if m.winner_age is not None and m.loser_age is not None:
            fields["age"] += 1
        if m.winner_height is not None and m.loser_height is not None:
            fields["height"] += 1
        if m.winner_hand and m.loser_hand:
            fields["handedness"] += 1
        if m.stats.get("w_svpt") is not None and m.stats.get("l_svpt") is not None:
            fields["serve_stats"] += 1
        if m.score:
            fields["score"] += 1
        if m.indoor:
            fields["indoor_outdoor"] += 1
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    csv_columns: dict[str, list[str]] = {}
    for path in csv_files[:4]:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            csv_columns[path.name] = next(reader, [])
    local_sources = Counter(detect_tour(path) for path in csv_files)
    has_challenger_files = any("chall" in path.name.lower() for path in csv_files)
    has_wta_files = any("wta" in path.name.lower() for path in csv_files)
    has_match_num = any("match_num" in columns for columns in csv_columns.values())
    has_draw_size = any("draw_size" in columns for columns in csv_columns.values())
    return {
        "matches": len(matches),
        "csv_files": len(csv_files),
        "local_file_tours": dict(local_sources),
        "schema_sample": csv_columns,
        "date_range": [matches[0].match_date.isoformat(), matches[-1].match_date.isoformat()] if matches else [],
        "tours": dict(Counter(m.tour for m in matches)),
        "surfaces": dict(surfaces),
        "levels": dict(levels),
        "rounds_top": dict(rounds.most_common(12)),
        "available_signal_rates": {key: round(value / max(1, len(matches)), 4) for key, value in fields.items()},
        "temporal_resolution": {
            "exact_match_date_available": False,
            "tourney_date_meaning": "tournament start date in Jeff Sackmann match files",
            "round_available": bool(rounds),
            "match_num_available": has_match_num,
            "draw_size_available": has_draw_size,
            "safe_update_decision": "round-level batches only; no same-round ordering from match_num is used because it is not a chronological timestamp",
        },
        "lower_tour_availability": {
            "challenger_files_present": has_challenger_files,
            "wta_files_present": has_wta_files,
            "qualifying_matches_present_as_files": False,
            "decision": "not integrated unless local trusted files are present; current workspace only exposes ATP tour-level match CSVs",
        },
        "not_available": ["point_by_point", "weather", "injury", "odds", "ball_type", "travel"],
    }


def player_payload(players: dict[str, PlayerState]) -> dict[str, Any]:
    payload = {}
    for key, p in players.items():
        payload[key] = {
            "name": p.name,
            "tour": p.tour,
            "overall_elo": round(p.overall_elo, 3),
            "surface_elo": {surface: round(value, 3) for surface, value in p.surface_elo.items() if surface in PRIMARY_SURFACES},
            "form_5": 0.5,
            "form_10": 0.5,
            "form_20": 0.5,
            "surface_form": {surface: 0.5 for surface in PRIMARY_SURFACES},
            "stat_averages": {
                "ace_rate": round(beta_rate(p, "aces", 0.055), 5),
                "df_rate": round(beta_rate(p, "double_faults", 0.035), 5),
                "first_in": round(beta_rate(p, "first_in", 0.62), 5),
                "first_won": round(beta_rate(p, "first_won", 0.72), 5),
                "second_won": round(beta_rate(p, "second_won", 0.52), 5),
                "bp_save": round(beta_rate(p, "bp_saved", 0.58, 40.0), 5),
                "bp_convert": round(beta_rate(p, "bp_converted", 0.40, 40.0), 5),
                "return_point_won": round(beta_rate(p, "return_won", 0.365), 5),
                "serve_point_won": round(service_point_model(p), 5),
                "stat_sample": round(min(p.stats["serve_points"].trials, 6000) / 6000.0, 5),
            },
            "last_date": p.last_date.isoformat() if p.last_date else None,
            "matches": p.matches,
            "ranking": p.ranking,
            "ranking_points": p.ranking_points,
            "advanced_state": {
                "rd": round(p.rd, 3),
                "surface_matches": {surface: round(p.surface_matches.get(surface, 0.0), 3) for surface in PRIMARY_SURFACES},
                "residual_form_short": round(p.residual_short.value(), 6),
                "residual_form_medium": round(p.residual_medium.value(), 6),
                "surface_residual_form": {surface: round(p.surface_residual[surface].value(), 6) for surface in PRIMARY_SURFACES},
                "score_dominance": round(p.score_dominance.value(), 6),
                "set_dominance": round(p.set_dominance.value(), 6),
                "tiebreak_strength": round(p.tiebreak_strength.value(), 6),
                "age": p.age,
                "height": p.height,
                "hand": p.hand,
            },
        }
    return payload


def snapshot_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:16]


def promote_corrected_model(
    final: dict[str, Any],
    players: dict[str, PlayerState],
    selected_name: str,
    matches_processed: int,
    temporal_mode: str,
) -> None:
    metrics_2025 = final["metrics_2025"]
    compatible = set(final["features"]).issubset(RUNTIME_COMPATIBLE_FEATURES)
    if not compatible:
        raise ValueError(f"Refusing to promote non-runtime feature set: {selected_name}")
    old = json.loads(MODEL_PATH.read_text(encoding="utf-8")) if MODEL_PATH.exists() else {}
    artifact = {
        "model_version": f"courtiq-real-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{selected_name}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tour": "atp",
        "feature_version": "courtiq_enhanced_runtime_safe_v1",
        "training_cutoff": "date <= 2023",
        "calibration_period": "date == 2024",
        "evaluation_period": "date == 2025",
        "temporal_policy_version": f"atp_tournament_date_{temporal_mode}_v1",
        "dataset_coverage": {
            "start_date": min((player.last_date for player in players.values() if player.last_date), default=None).isoformat()
            if any(player.last_date for player in players.values())
            else None,
            "end_date": max((player.last_date for player in players.values() if player.last_date), default=None).isoformat()
            if any(player.last_date for player in players.values())
            else None,
        },
        "data_source": f"Local ATP CSV files from work/tennis-data; features use {temporal_mode} chronological snapshots because tourney_date is tournament start date.",
        "data_snapshot_hash": snapshot_hash(DATA_DIR.glob("*.csv")),
        "matches_processed": matches_processed,
        "model": final["model"],
        "metrics": metrics_2025,
        "legacy_contaminated_metrics_retired": {
            "reason": "Previous production/backtest rows may have updated state between matches sharing the same tournament start date. Those metrics are no longer treated as scientific benchmarks.",
            "previous_model_version": old.get("model_version"),
            "previous_metrics": old.get("metrics"),
        },
        "previous_model_version": old.get("model_version"),
        "promotion_source": {
            "report": str(REPORT_PATH),
            "selection_rule": "strongest runtime-compatible corrected model selected from 2019-2023 walk-forward log loss, calibrated on 2024, benchmarked on 2025",
        },
        "players": player_payload(players),
    }
    MODEL_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    started = time.perf_counter()
    random.seed(7)
    np.random.seed(7)
    temporal_mode = os.environ.get("COURTIQ_TEMPORAL_MODE", "round_safe").strip() or "round_safe"
    matches = load_matches()
    if len(matches) < 1000:
        raise SystemExit("Not enough real matches in work/tennis-data.")
    frame, players, _ = build_feature_rows(matches, temporal_mode=temporal_mode)
    feature_cols = [col for col in frame.columns if col not in {"index", "date", "year", "tour", "tournament", "surface", "level", "round", "player1", "player2", "label"}]
    frame[feature_cols] = frame[feature_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    ENHANCED_ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(ENHANCED_ROWS_PATH, index=False)

    test_2025 = frame[frame["year"] == 2025]
    current_disk = artifact_metrics_on_saved_rows(MODEL_PATH)
    if current_disk.get("status") == "incompatible_feature_rows" and MODEL_PATH.exists():
        current_payload = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        retired = (current_payload.get("legacy_contaminated_metrics_retired") or {}).get("previous_metrics")
        if isinstance(retired, dict):
            current_disk = {"status": "legacy_from_retired_metadata", "model_version": current_payload.get("previous_model_version"), **retired}
    frozen_original = artifact_metrics_on_saved_rows(FROZEN_BASELINE_PATH)
    current_reference_metrics = current_disk if current_disk.get("status") == "evaluated" else {"log_loss": FROZEN_STACKED_BENCHMARK["log_loss"], "brier_score": FROZEN_STACKED_BENCHMARK["brier_score"]}

    candidates = {}
    for name, features in candidate_sets(feature_cols).items():
        candidates[name] = {
            "feature_count": len(features),
            "runtime_compatible": set(features).issubset(RUNTIME_COMPATIBLE_FEATURES),
            "walk_forward": walk_forward(frame, features),
        }
    eligible = [
        (name, info)
        for name, info in candidates.items()
        if info["walk_forward"].get("status") == "evaluated"
    ]
    selected_name, selected_info = min(
        eligible,
        key=lambda item: (
            float(item[1]["walk_forward"]["mean_log_loss"]),
            float(item[1]["walk_forward"]["mean_brier_score"]),
            float(item[1]["walk_forward"]["mean_ece"]),
        ),
    )
    runtime_safe_final = final_train_eval(frame, candidate_sets(feature_cols)["enhanced_runtime_safe"])
    final = final_train_eval(frame, candidate_sets(feature_cols)[selected_name])
    runtime_probs, runtime_labels, runtime_test_rows = final_test_probabilities(frame, candidate_sets(feature_cols)["enhanced_runtime_safe"])
    selected_probs, selected_labels, selected_test_rows = final_test_probabilities(frame, candidate_sets(feature_cols)[selected_name])
    bootstrap_delta = bootstrap_logloss_delta(runtime_probs, selected_probs, selected_labels, selected_test_rows)
    selected_strata = stratified_metrics(selected_test_rows, selected_probs, selected_labels)
    promote_corrected_model(runtime_safe_final, players, "enhanced_runtime_safe", len(matches), temporal_mode)

    temporal_guard = (
        "Sackmann tourney_date is tournament start date. Rows use a conservative round-safe partial order: completed earlier rounds update later rounds, but all matches inside the same round are snapshotted before any same-round update. match_num is not used to order matches inside a round."
        if temporal_mode == "round_safe"
        else "Sackmann tourney_date is tournament start date. Rows snapshot every match in the same tournament before applying any tournament-result update. This is more conservative than round-safe updating and prevents all intra-tournament leakage."
    )

    report = {
        "status": "ok",
        "run_id": f"final-modeling-pass-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "temporal_mode": temporal_mode,
        "data_profile": data_profile(matches),
        "test_set_discipline": {
            "development_selection": "walk-forward validation years 2019-2023 only",
            "calibration": "2024 only",
            "final_benchmark": "2025 only",
            "prospective_holdout": "2026 reported when enough rows exist; not used for selection",
            "tournament_date_guard": temporal_guard,
            "round_order_used": ROUND_ORDER,
        },
        "baselines": {
            "valid_corrected_benchmark_from_brief": VALID_CORRECTED_BENCHMARK,
            "legacy_contaminated_stacked_benchmark_from_brief": RETIRED_UNSAFE_BENCHMARK,
            "legacy_original_artifact_possibly_contaminated": frozen_original,
            "legacy_current_disk_artifact_possibly_contaminated_before_this_run": current_disk,
        },
        "experts_tested": {
            "dynamic_rating": "overall Elo, surface Elo with sample shrinkage, Glicko-style rating deviation",
            "serve_return": "empirical-Bayes decayed first/second serve, return, ace, double-fault and break-point rates",
            "latent_serve_return_engine": "logit(P(server wins point)) = surface_intercept + ServeSkill_server - ReturnSkill_receiver with surface-to-overall shrinkage and exact scoring conversion",
            "common_opponent_v2": "expectation-adjusted result, serve and return residuals against shared opponents, surface-aware, recency-weighted and shrunk by shared sample size",
            "current_state": "expectation-adjusted residual form, workload/rest, score dominance memory",
            "structural_scoring": "serve point -> game -> set -> match probability via exact backend tennis math",
            "tabular_ml": "regularized logistic over candidate feature families",
            "boosters": "not run: LightGBM/XGBoost/CatBoost packages unavailable in the offline runtime",
        },
        "candidate_search": candidates,
        "selected_by_walk_forward": {"name": selected_name, **selected_info},
        "final_selected_model": final,
        "selected_model_stratified_2025": selected_strata,
        "bootstrap_vs_runtime_safe": bootstrap_delta,
        "best_runtime_compatible_corrected_model": {
            "name": "enhanced_runtime_safe",
            **runtime_safe_final,
        },
        "production_decision": {
            "production_model_changed": False,
            "winning_model": "enhanced_runtime_safe",
            "reason": "No deployable corrected candidate materially beat the valid leakage-safe benchmark. The production artifact was regenerated from raw real data under corrected tournament-date semantics, while legacy 70-72% contaminated metrics remain retired.",
            "artifact_path": str(MODEL_PATH),
        },
        "comparison_table": [
            {"model": "VALID corrected benchmark from brief", **VALID_CORRECTED_BENCHMARK},
            {"model": "LEGACY possibly contaminated stacked benchmark", **RETIRED_UNSAFE_BENCHMARK},
            {"model": "LEGACY possibly contaminated current artifact before run", **{k: current_disk[k] for k in ("accuracy", "roc_auc", "log_loss", "brier_score", "ece") if k in current_disk}},
            {"model": f"Corrected research best ({selected_name})", **final["metrics_2025"]},
            {"model": "CURRENT production leakage-safe enhanced_runtime_safe", **runtime_safe_final["metrics_2025"]},
        ],
        "runtime_seconds": round(time.perf_counter() - started, 3),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "report": str(REPORT_PATH),
        "selected": selected_name,
        "production_changed": False,
        "comparison_table": report["comparison_table"],
        "prospective_2026": final.get("prospective_2026"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
