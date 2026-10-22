from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "work/tennis-data"
MODEL_PATH = ROOT / "output/models/courtiq_model_wta.json"
BACKTEST_PATH = ROOT / "output/backtests/courtiq_backtest_report_wta.json"
FEATURE_ROWS_PATH = ROOT / "output/backtests/courtiq_feature_rows_wta.csv"
PLOTS_DIR = ROOT / "output/backtests"
SURFACES = {"hard", "clay", "grass"}
FEATURE_NAMES = [
    "overall_elo_diff",
    "surface_elo_diff",
    "form_5_diff",
    "form_10_diff",
    "form_20_diff",
    "surface_form_diff",
    "matches_diff",
    "ranking_diff",
    "ranking_points_diff",
    "ace_rate_diff",
    "df_rate_diff",
    "first_in_diff",
    "first_won_diff",
    "second_won_diff",
    "bp_save_diff",
    "bp_convert_diff",
    "return_point_won_diff",
    "serve_point_won_diff",
    "stat_sample_diff",
    "days_rest_diff",
    "workload_14d_diff",
    "h2h_prior_diff",
    "surface_h2h_prior_diff",
    "best_of_5",
]


@dataclass
class RawMatch:
    tour: str
    match_date: date
    tournament: str
    surface: str
    best_of: int
    winner: str
    loser: str
    winner_rank: float | None = None
    loser_rank: float | None = None
    winner_rank_points: float | None = None
    loser_rank_points: float | None = None
    stats: dict[str, float | None] = field(default_factory=dict)


@dataclass
class PlayerState:
    name: str
    tour: str
    overall_elo: float = 1500.0
    surface_elo: dict[str, float] = field(default_factory=lambda: {surface: 1500.0 for surface in SURFACES})
    results: deque[int] = field(default_factory=lambda: deque(maxlen=20))
    surface_results: dict[str, deque[int]] = field(default_factory=lambda: {surface: deque(maxlen=20) for surface in SURFACES})
    last_date: date | None = None
    workload_dates: deque[date] = field(default_factory=lambda: deque(maxlen=40))
    matches: int = 0
    ranking: float | None = None
    ranking_points: float | None = None
    stat_history: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=20)))
    stat_totals: dict[str, float] = field(default_factory=lambda: defaultdict(float))


def normalize_name(value: str) -> str:
    return " ".join(value.strip().replace("_", " ").split())


def player_key(name: str, tour: str) -> str:
    return f"{tour}::{normalize_name(name).lower()}"


def parse_date(value: str) -> date:
    value = value.strip()
    if not value:
        raise ValueError("empty date")
    if len(value) == 8 and value.isdigit():
        return datetime.strptime(value, "%Y%m%d").date()
    return datetime.fromisoformat(value).date()


def parse_float(row: dict[str, str], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def parse_surface(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned in {"greenset", "carpet", "indoor hard", "outdoor hard"}:
        return "hard"
    return cleaned if cleaned in SURFACES else "hard"


def detect_tour(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("wta") or "wta" in name:
        return "wta"
    return "atp"


def load_matches(data_dir: Path = DATA_DIR) -> list[RawMatch]:
    files = sorted(data_dir.glob("*.csv"))
    for subdir in ("atp", "wta"):
        nested = data_dir / subdir
        if nested.exists():
            files.extend(sorted(nested.glob("*.csv")))
    if not files:
        raise FileNotFoundError("No ATP/WTA CSV files found in work/tennis-data/, work/tennis-data/atp/, or work/tennis-data/wta/.")
    matches: list[RawMatch] = []
    for path in files:
        tour = detect_tour(path)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                winner, loser = canonical_winner_loser(row)
                if not winner or not loser:
                    continue
                try:
                    match_date = parse_date(row.get("tourney_date") or row.get("date") or row.get("Date") or "")
                except ValueError:
                    continue
                surface = parse_surface(row.get("surface"))
                if not row.get("surface") and row.get("Surface"):
                    surface = parse_surface(row.get("Surface"))
                best_of = int(parse_float(row, "best_of", "Best of") or (5 if tour == "atp" and row.get("tourney_level") == "G" else 3))
                player1 = normalize_name(row.get("Player_1") or row.get("player_1") or "")
                player2 = normalize_name(row.get("Player_2") or row.get("player_2") or "")
                winner_side = "1" if player1 and winner == player1 else ("2" if player2 and winner == player2 else "")
                loser_side = "2" if winner_side == "1" else ("1" if winner_side == "2" else "")
                w_svpt = parse_float(row, "w_svpt")
                l_svpt = parse_float(row, "l_svpt")
                w_first_in_count = parse_float(row, "w_1stIn")
                l_first_in_count = parse_float(row, "l_1stIn")
                w_second_total = none_sub(w_svpt, w_first_in_count)
                l_second_total = none_sub(l_svpt, l_first_in_count)
                w_first_won = parse_float(row, "w_1stWon")
                l_first_won = parse_float(row, "l_1stWon")
                w_second_won = parse_float(row, "w_2ndWon")
                l_second_won = parse_float(row, "l_2ndWon")
                w_service_won = none_sum(w_first_won, w_second_won)
                l_service_won = none_sum(l_first_won, l_second_won)
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
                    "w_first_in_count": w_first_in_count,
                    "l_first_in_count": l_first_in_count,
                    "w_first_won_count": w_first_won,
                    "l_first_won_count": l_first_won,
                    "w_second_total": w_second_total,
                    "l_second_total": l_second_total,
                    "w_second_won_count": w_second_won,
                    "l_second_won_count": l_second_won,
                    "w_bp_saved_count": w_bp_saved,
                    "l_bp_saved_count": l_bp_saved,
                    "w_bp_faced": w_bp_faced,
                    "l_bp_faced": l_bp_faced,
                    "w_bp_converted": none_sub(l_bp_faced, l_bp_saved),
                    "l_bp_converted": none_sub(w_bp_faced, w_bp_saved),
                    "w_ace_rate": ratio(parse_float(row, "w_ace"), parse_float(row, "w_svpt")),
                    "l_ace_rate": ratio(parse_float(row, "l_ace"), parse_float(row, "l_svpt")),
                    "w_df_rate": ratio(parse_float(row, "w_df"), parse_float(row, "w_svpt")),
                    "l_df_rate": ratio(parse_float(row, "l_df"), parse_float(row, "l_svpt")),
                    "w_first_in": ratio(parse_float(row, "w_1stIn"), parse_float(row, "w_svpt")),
                    "l_first_in": ratio(parse_float(row, "l_1stIn"), parse_float(row, "l_svpt")),
                    "w_first_won": ratio(parse_float(row, "w_1stWon"), parse_float(row, "w_1stIn")),
                    "l_first_won": ratio(parse_float(row, "l_1stWon"), parse_float(row, "l_1stIn")),
                    "w_second_won": ratio(parse_float(row, "w_2ndWon"), none_sub(parse_float(row, "w_svpt"), parse_float(row, "w_1stIn"))),
                    "l_second_won": ratio(parse_float(row, "l_2ndWon"), none_sub(parse_float(row, "l_svpt"), parse_float(row, "l_1stIn"))),
                    "w_bp_save": ratio(parse_float(row, "w_bpSaved"), parse_float(row, "w_bpFaced")),
                    "l_bp_save": ratio(parse_float(row, "l_bpSaved"), parse_float(row, "l_bpFaced")),
                    "w_bp_convert": ratio(none_sub(parse_float(row, "l_bpFaced"), parse_float(row, "l_bpSaved")), parse_float(row, "l_bpFaced")),
                    "l_bp_convert": ratio(none_sub(parse_float(row, "w_bpFaced"), parse_float(row, "w_bpSaved")), parse_float(row, "w_bpFaced")),
                }
                matches.append(
                    RawMatch(
                        tour=tour,
                        match_date=match_date,
                        tournament=row.get("tourney_name") or row.get("tournament") or row.get("Tournament") or "",
                        surface=surface,
                        best_of=best_of if best_of in {3, 5} else 3,
                        winner=winner,
                        loser=loser,
                        winner_rank=parse_float(row, "winner_rank", "winner_rank_num", f"Rank_{winner_side}"),
                        loser_rank=parse_float(row, "loser_rank", "loser_rank_num", f"Rank_{loser_side}"),
                        winner_rank_points=parse_float(row, "winner_rank_points", "winner_points", f"Pts_{winner_side}"),
                        loser_rank_points=parse_float(row, "loser_rank_points", "loser_points", f"Pts_{loser_side}"),
                        stats=stats,
                    )
                )
    matches.sort(key=lambda item: (item.match_date, item.tour, item.tournament, item.winner, item.loser))
    return matches


def canonical_winner_loser(row: dict[str, str]) -> tuple[str, str]:
    winner = normalize_name(row.get("winner_name") or row.get("winner") or row.get("Winner") or "")
    loser = normalize_name(row.get("loser_name") or row.get("loser") or "")
    player1 = normalize_name(row.get("Player_1") or row.get("player_1") or "")
    player2 = normalize_name(row.get("Player_2") or row.get("player_2") or "")
    if winner and loser:
        return winner, loser
    if winner and player1 and player2:
        if winner == player1:
            return player1, player2
        if winner == player2:
            return player2, player1
    return winner, loser


def none_sub(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b


def none_sum(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a + b


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return max(0.0, min(1.0, numerator / denominator))


def average(values: Iterable[float], default: float = 0.5) -> float:
    rows = list(values)
    return sum(rows) / len(rows) if rows else default


def beta_rate(success: float, total: float, prior: float = 0.5, prior_n: float = 80.0) -> float:
    if total <= 0:
        return prior
    return (prior * prior_n + success) / (prior_n + total)


def stat_rate(player: PlayerState, success_key: str, total_key: str, prior: float, prior_n: float = 120.0) -> float:
    return beta_rate(player.stat_totals[success_key], player.stat_totals[total_key], prior, prior_n)


def stat_sample(player: PlayerState) -> float:
    return min(player.stat_totals["serve_points"], 6000.0) / 6000.0


def form(results: deque[int], n: int) -> float:
    rows = list(results)[-n:]
    return sum(rows) / len(rows) if rows else 0.5


def days_rest(player: PlayerState, match_date: date) -> float:
    if player.last_date is None:
        return 14.0
    return min(60.0, max(0.0, float((match_date - player.last_date).days)))


def workload_14d(player: PlayerState, match_date: date) -> float:
    return float(sum(1 for item in player.workload_dates if 0 <= (match_date - item).days <= 14))


def expected_score(a: float, b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((b - a) / 400.0))


def blended(player: PlayerState, surface: str) -> float:
    return 0.62 * player.surface_elo.get(surface, player.overall_elo) + 0.38 * player.overall_elo


def update_elo(winner: PlayerState, loser: PlayerState, surface: str, best_of: int) -> None:
    expected = expected_score(blended(winner, surface), blended(loser, surface))
    experience = 1.0 / (1.0 + min(winner.matches, loser.matches) / 160.0)
    k = (18.0 + 18.0 * experience) * (1.08 if best_of == 5 else 1.0)
    delta = k * (1.0 - expected)
    winner.overall_elo += delta * 0.42
    loser.overall_elo -= delta * 0.42
    winner.surface_elo[surface] = winner.surface_elo.get(surface, 1500.0) + delta * 0.72
    loser.surface_elo[surface] = loser.surface_elo.get(surface, 1500.0) - delta * 0.72


def feature_diff(a: PlayerState, b: PlayerState, surface: str, match_date: date, best_of: int, h2h: dict[tuple[str, str], int]) -> dict[str, float]:
    pair_a = (player_key(a.name, a.tour), player_key(b.name, b.tour))
    pair_b = (pair_a[1], pair_a[0])
    surface_pair_a = (f"{surface}:{pair_a[0]}", pair_a[1])
    surface_pair_b = (f"{surface}:{pair_a[1]}", pair_a[0])
    return {
        "overall_elo_diff": (a.overall_elo - b.overall_elo) / 400.0,
        "surface_elo_diff": (a.surface_elo.get(surface, 1500.0) - b.surface_elo.get(surface, 1500.0)) / 400.0,
        "form_5_diff": form(a.results, 5) - form(b.results, 5),
        "form_10_diff": form(a.results, 10) - form(b.results, 10),
        "form_20_diff": form(a.results, 20) - form(b.results, 20),
        "surface_form_diff": form(a.surface_results[surface], 10) - form(b.surface_results[surface], 10),
        "matches_diff": (min(a.matches, 300) - min(b.matches, 300)) / 300.0,
        "ranking_diff": ((b.ranking or 999.0) - (a.ranking or 999.0)) / 998.0,
        "ranking_points_diff": ((a.ranking_points or 0.0) - (b.ranking_points or 0.0)) / 12000.0,
        "ace_rate_diff": stat_rate(a, "aces", "serve_points", 0.055) - stat_rate(b, "aces", "serve_points", 0.055),
        "df_rate_diff": stat_rate(a, "double_faults", "serve_points", 0.035) - stat_rate(b, "double_faults", "serve_points", 0.035),
        "first_in_diff": stat_rate(a, "first_in", "serve_points", 0.62) - stat_rate(b, "first_in", "serve_points", 0.62),
        "first_won_diff": stat_rate(a, "first_won", "first_in", 0.72) - stat_rate(b, "first_won", "first_in", 0.72),
        "second_won_diff": stat_rate(a, "second_won", "second_total", 0.52) - stat_rate(b, "second_won", "second_total", 0.52),
        "bp_save_diff": stat_rate(a, "bp_saved", "bp_faced", 0.58, 40.0) - stat_rate(b, "bp_saved", "bp_faced", 0.58, 40.0),
        "bp_convert_diff": stat_rate(a, "bp_converted", "bp_opportunities", 0.40, 40.0) - stat_rate(b, "bp_converted", "bp_opportunities", 0.40, 40.0),
        "return_point_won_diff": stat_rate(a, "return_points_won", "return_points", 0.365) - stat_rate(b, "return_points_won", "return_points", 0.365),
        "serve_point_won_diff": stat_rate(a, "service_points_won", "serve_points", 0.635) - stat_rate(b, "service_points_won", "serve_points", 0.635),
        "stat_sample_diff": stat_sample(a) - stat_sample(b),
        "days_rest_diff": (days_rest(a, match_date) - days_rest(b, match_date)) / 60.0,
        "workload_14d_diff": (workload_14d(a, match_date) - workload_14d(b, match_date)) / 8.0,
        "h2h_prior_diff": (h2h[pair_a] - h2h[pair_b]) / 10.0,
        "surface_h2h_prior_diff": (h2h[surface_pair_a] - h2h[surface_pair_b]) / 10.0,
        "best_of_5": float(best_of == 5),
    }


def process_matches(matches: list[RawMatch]) -> tuple[list[dict[str, object]], dict[str, PlayerState]]:
    players: dict[str, PlayerState] = {}
    h2h: dict[tuple[str, str], int] = defaultdict(int)
    rows: list[dict[str, object]] = []

    batches: dict[tuple[str, date, str], list[tuple[int, RawMatch]]] = defaultdict(list)
    for index, match in enumerate(matches):
        batches[(match.tour, match.match_date, match.tournament)].append((index, match))

    for _, batch in sorted(batches.items(), key=lambda item: item[0]):
        for _, match in batch:
            winner_key = player_key(match.winner, match.tour)
            loser_key = player_key(match.loser, match.tour)
            winner = players.setdefault(winner_key, PlayerState(name=match.winner, tour=match.tour))
            loser = players.setdefault(loser_key, PlayerState(name=match.loser, tour=match.tour))
            winner.ranking = match.winner_rank or winner.ranking
            loser.ranking = match.loser_rank or loser.ranking
            winner.ranking_points = match.winner_rank_points or winner.ranking_points
            loser.ranking_points = match.loser_rank_points or loser.ranking_points

        for index, match in batch:
            winner = players[player_key(match.winner, match.tour)]
            loser = players[player_key(match.loser, match.tour)]
            flipped = stable_flip(match)
            p1, p2, label = (winner, loser, 1) if not flipped else (loser, winner, 0)
            features = feature_diff(p1, p2, match.surface, match.match_date, match.best_of, h2h)
            rows.append(
                {
                    "index": index,
                    "date": match.match_date.isoformat(),
                    "tour": match.tour,
                    "tournament": match.tournament,
                    "surface": match.surface,
                    "player1": p1.name,
                    "player2": p2.name,
                    "label": label,
                    **features,
                }
            )

        for _, match in batch:
            winner_key = player_key(match.winner, match.tour)
            loser_key = player_key(match.loser, match.tour)
            winner = players[winner_key]
            loser = players[loser_key]
            update_elo(winner, loser, match.surface, match.best_of)
            winner.results.append(1)
            loser.results.append(0)
            winner.surface_results[match.surface].append(1)
            loser.surface_results[match.surface].append(0)
            winner.last_date = loser.last_date = match.match_date
            winner.workload_dates.append(match.match_date)
            loser.workload_dates.append(match.match_date)
            winner.matches += 1
            loser.matches += 1
            update_stats(winner, match.stats, "w")
            update_stats(loser, match.stats, "l")
            h2h[(winner_key, loser_key)] += 1
            h2h[(f"{match.surface}:{winner_key}", loser_key)] += 1

    return rows, players


def stable_flip(match: RawMatch) -> bool:
    seed = f"{match.match_date.isoformat()}|{match.tour}|{match.tournament}|{match.winner}|{match.loser}"
    value = 0
    for char in seed:
        value = (value * 131 + ord(char)) % 1_000_003
    return value % 2 == 0


def update_stats(player: PlayerState, stats: dict[str, float | None], prefix: str) -> None:
    mapping = {
        "ace_rate": f"{prefix}_ace_rate",
        "df_rate": f"{prefix}_df_rate",
        "first_in": f"{prefix}_first_in",
        "first_won": f"{prefix}_first_won",
        "second_won": f"{prefix}_second_won",
        "bp_save": f"{prefix}_bp_save",
        "bp_convert": f"{prefix}_bp_convert",
    }
    for target, source in mapping.items():
        value = stats.get(source)
        if value is not None:
            player.stat_history[target].append(float(value))
    count_mapping = {
        "serve_points": f"{prefix}_svpt",
        "service_points_won": f"{prefix}_service_won",
        "return_points": "l_svpt" if prefix == "w" else "w_svpt",
        "return_points_won": f"{prefix}_return_won",
        "aces": f"{prefix}_ace",
        "double_faults": f"{prefix}_df",
        "first_in": f"{prefix}_first_in_count",
        "first_won": f"{prefix}_first_won_count",
        "second_total": f"{prefix}_second_total",
        "second_won": f"{prefix}_second_won_count",
        "bp_saved": f"{prefix}_bp_saved_count",
        "bp_faced": f"{prefix}_bp_faced",
        "bp_converted": f"{prefix}_bp_converted",
        "bp_opportunities": "l_bp_faced" if prefix == "w" else "w_bp_faced",
    }
    for target, source in count_mapping.items():
        value = stats.get(source)
        if value is not None and value >= 0:
            player.stat_totals[target] += float(value)


def sigmoid(value: float) -> float:
    if value < -35:
        return 0.0
    if value > 35:
        return 1.0
    return 1.0 / (1.0 + math.exp(-value))


def fit_logistic(rows: list[dict[str, object]], epochs: int = 180, learning_rate: float = 0.08, l2: float = 0.0015) -> tuple[list[float], float]:
    weights = [0.0 for _ in FEATURE_NAMES]
    intercept = 0.0
    n = max(1, len(rows))
    for _ in range(epochs):
        grad = [0.0 for _ in FEATURE_NAMES]
        grad_i = 0.0
        for row in rows:
            x = [float(row[name]) for name in FEATURE_NAMES]
            y = float(row["label"])
            pred = sigmoid(intercept + sum(w * value for w, value in zip(weights, x, strict=True)))
            error = pred - y
            grad_i += error
            for idx, value in enumerate(x):
                grad[idx] += error * value
        intercept -= learning_rate * grad_i / n
        for idx in range(len(weights)):
            weights[idx] -= learning_rate * ((grad[idx] / n) + l2 * weights[idx])
    return weights, intercept


def row_logit(row: dict[str, object], weights: list[float], intercept: float) -> float:
    return intercept + sum(weights[i] * float(row[name]) for i, name in enumerate(FEATURE_NAMES))


def predict_row(row: dict[str, object], weights: list[float], intercept: float, calibrator: dict[str, float] | None = None) -> float:
    logit = row_logit(row, weights, intercept)
    if calibrator:
        logit = calibrator.get("slope", 1.0) * logit + calibrator.get("intercept", 0.0)
    return sigmoid(logit)


def evaluate(rows: list[dict[str, object]], weights: list[float], intercept: float, calibrator: dict[str, float] | None = None) -> dict[str, object]:
    if not rows:
        return {"rows": 0}
    probs = [min(0.999999, max(0.000001, predict_row(row, weights, intercept, calibrator))) for row in rows]
    labels = [int(row["label"]) for row in rows]
    base = probability_metrics(probs, labels)
    return {
        "rows": len(rows),
        **base,
        "calibration": calibration(probs, labels),
        "ece": round(expected_calibration_error(probs, labels), 4),
    }


def probability_metrics(probs: list[float], labels: list[int]) -> dict[str, float]:
    accuracy = sum((p >= 0.5) == bool(y) for p, y in zip(probs, labels, strict=True)) / len(labels)
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in zip(probs, labels, strict=True)) / len(labels)
    brier = sum((p - y) ** 2 for p, y in zip(probs, labels, strict=True)) / len(labels)
    return {
        "accuracy": round(accuracy, 4),
        "roc_auc": round(roc_auc(probs, labels), 4),
        "log_loss": round(log_loss, 4),
        "brier_score": round(brier, 4),
    }


def roc_auc(probs: list[float], labels: list[int]) -> float:
    positives = sum(1 for label in labels if label == 1)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return 0.5
    ranked = sorted(zip(probs, labels, strict=True), key=lambda item: item[0])
    rank_sum_positive = 0.0
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][0] == ranked[index][0]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        rank_sum_positive += average_rank * sum(1 for _, label in ranked[index:end] if label == 1)
        index = end
    return (rank_sum_positive - positives * (positives + 1) / 2.0) / (positives * negatives)


def calibration(probs: list[float], labels: list[int], buckets: int = 10) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    for bucket in range(buckets):
        low, high = bucket / buckets, (bucket + 1) / buckets
        picked = [(p, y) for p, y in zip(probs, labels, strict=True) if low <= p < high or (bucket == buckets - 1 and p == 1.0)]
        if picked:
            rows.append(
                {
                    "bucket": bucket,
                    "count": len(picked),
                    "mean_predicted": round(sum(p for p, _ in picked) / len(picked), 4),
                    "actual_win_rate": round(sum(y for _, y in picked) / len(picked), 4),
                }
            )
    return rows


def expected_calibration_error(probs: list[float], labels: list[int], buckets: int = 10) -> float:
    total = len(labels)
    error = 0.0
    for row in calibration(probs, labels, buckets):
        error += (row["count"] / total) * abs(float(row["mean_predicted"]) - float(row["actual_win_rate"]))
    return error


def fit_platt_calibrator(validation: list[dict[str, object]], weights: list[float], intercept: float) -> dict[str, float]:
    if not validation:
        return {"method": "none", "slope": 1.0, "intercept": 0.0}
    pseudo_rows = [{"x": row_logit(row, weights, intercept), "label": row["label"]} for row in validation]
    slope = 1.0
    cal_intercept = 0.0
    learning_rate = 0.03
    n = len(pseudo_rows)
    for _ in range(900):
        grad_slope = 0.0
        grad_intercept = 0.0
        for row in pseudo_rows:
            x = float(row["x"])
            y = float(row["label"])
            pred = sigmoid(slope * x + cal_intercept)
            error = pred - y
            grad_slope += error * x
            grad_intercept += error
        slope -= learning_rate * ((grad_slope / n) + 0.002 * (slope - 1.0))
        cal_intercept -= learning_rate * grad_intercept / n
    return {"method": "platt_validation_2024", "slope": round(slope, 6), "intercept": round(cal_intercept, 6)}


def split_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    return split_rows_with_rules(rows)[0:3]


def split_rows_with_rules(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    train = [row for row in rows if int(str(row["date"])[:4]) <= 2023]
    validation = [row for row in rows if int(str(row["date"])[:4]) == 2024]
    test = [row for row in rows if int(str(row["date"])[:4]) == 2025]
    if train and validation and test:
        return train, validation, test, {
            "train_rule": "date <= 2023",
            "calibration_rule": "date == 2024",
            "final_holdout_rule": "date == 2025",
            "split_type": "fixed_modern_holdout",
        }
    years = sorted({int(str(row["date"])[:4]) for row in rows})
    if len(years) >= 3:
        validation_year = years[-2]
        test_year = years[-1]
        train = [row for row in rows if int(str(row["date"])[:4]) < validation_year]
        validation = [row for row in rows if int(str(row["date"])[:4]) == validation_year]
        test = [row for row in rows if int(str(row["date"])[:4]) == test_year]
        if train and validation and test:
            return train, validation, test, {
                "train_rule": f"date < {validation_year}",
                "calibration_rule": f"date == {validation_year}",
                "final_holdout_rule": f"date == {test_year}",
                "split_type": "latest_two_year_holdout",
            }
    n = len(rows)
    return (
        rows[: int(n * 0.7)],
        rows[int(n * 0.7) : int(n * 0.85)],
        rows[int(n * 0.85) :],
        {
            "train_rule": "first 70% of chronological rows",
            "calibration_rule": "next 15% of chronological rows",
            "final_holdout_rule": "final 15% of chronological rows",
            "split_type": "row_count_fallback",
        },
    )


def rows_between_years(rows: list[dict[str, object]], start: int, end: int) -> list[dict[str, object]]:
    return [row for row in rows if start <= int(str(row["date"])[:4]) <= end]


def rows_before_year(rows: list[dict[str, object]], year: int) -> list[dict[str, object]]:
    return [row for row in rows if int(str(row["date"])[:4]) < year]


def export_feature_rows(rows: list[dict[str, object]]) -> None:
    FEATURE_ROWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEATURE_ROWS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["empty"])
        writer.writeheader()
        writer.writerows(rows)


def player_payload(players: dict[str, PlayerState]) -> dict[str, dict[str, object]]:
    payload = {}
    for key, player in players.items():
        payload[key] = {
            "name": player.name,
            "tour": player.tour,
            "overall_elo": round(player.overall_elo, 3),
            "surface_elo": {surface: round(value, 3) for surface, value in player.surface_elo.items()},
            "form_5": round(form(player.results, 5), 4),
            "form_10": round(form(player.results, 10), 4),
            "form_20": round(form(player.results, 20), 4),
            "surface_form": {surface: round(form(player.surface_results[surface], 10), 4) for surface in SURFACES},
            "stat_averages": {
                "ace_rate": round(stat_rate(player, "aces", "serve_points", 0.055), 5),
                "df_rate": round(stat_rate(player, "double_faults", "serve_points", 0.035), 5),
                "first_in": round(stat_rate(player, "first_in", "serve_points", 0.62), 5),
                "first_won": round(stat_rate(player, "first_won", "first_in", 0.72), 5),
                "second_won": round(stat_rate(player, "second_won", "second_total", 0.52), 5),
                "bp_save": round(stat_rate(player, "bp_saved", "bp_faced", 0.58, 40.0), 5),
                "bp_convert": round(stat_rate(player, "bp_converted", "bp_opportunities", 0.40, 40.0), 5),
                "return_point_won": round(stat_rate(player, "return_points_won", "return_points", 0.365), 5),
                "serve_point_won": round(stat_rate(player, "service_points_won", "serve_points", 0.635), 5),
                "stat_sample": round(stat_sample(player), 5),
            },
            "last_date": player.last_date.isoformat() if player.last_date else None,
            "matches": player.matches,
            "ranking": player.ranking,
            "ranking_points": player.ranking_points,
        }
    return payload


def data_snapshot_hash(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:16]


def data_files(data_dir: Path = DATA_DIR) -> list[Path]:
    files = list(data_dir.glob("*.csv"))
    for subdir in ("atp", "wta"):
        nested = data_dir / subdir
        if nested.exists():
            files.extend(nested.glob("*.csv"))
    return sorted(files)


def benchmark_baseline(rows: list[dict[str, object]], feature_name: str, scale: float = 2.2) -> dict[str, object]:
    if not rows:
        return {"rows": 0}
    probs = [sigmoid(scale * float(row[feature_name])) for row in rows]
    labels = [int(row["label"]) for row in rows]
    return {"rows": len(rows), **probability_metrics(probs, labels), "ece": round(expected_calibration_error(probs, labels), 4)}


def walk_forward_report(rows: list[dict[str, object]], years: Iterable[int] = range(2020, 2026)) -> list[dict[str, object]]:
    folds = []
    for year in years:
        train = rows_before_year(rows, year)
        valid = rows_between_years(rows, year, year)
        if len(train) < 1000 or len(valid) < 100:
            continue
        weights, intercept = fit_logistic(train, epochs=90)
        folds.append(
            {
                "validation_year": year,
                "train_rows": len(train),
                "validation_rows": len(valid),
                "logistic": evaluate(valid, weights, intercept),
                "surface_elo_baseline": benchmark_baseline(valid, "surface_elo_diff"),
                "overall_elo_baseline": benchmark_baseline(valid, "overall_elo_diff"),
                "ranking_baseline": benchmark_baseline(valid, "ranking_diff"),
                "serve_return_baseline": benchmark_baseline(valid, "serve_point_won_diff", 9.0),
            }
        )
    return folds


def summarize_folds(folds: list[dict[str, object]], model_key: str) -> dict[str, float | int]:
    picked = [fold[model_key] for fold in folds if model_key in fold]
    if not picked:
        return {"folds": 0}
    return {
        "folds": len(picked),
        "mean_log_loss": round(sum(float(row["log_loss"]) for row in picked) / len(picked), 4),
        "mean_brier": round(sum(float(row["brier_score"]) for row in picked) / len(picked), 4),
        "mean_accuracy": round(sum(float(row["accuracy"]) for row in picked) / len(picked), 4),
        "mean_ece": round(sum(float(row.get("ece", 0.0)) for row in picked) / len(picked), 4),
    }


def write_outputs(matches: list[RawMatch], rows: list[dict[str, object]], players: dict[str, PlayerState], weights: list[float], intercept: float, calibrator: dict[str, float]) -> dict[str, object]:
    train, validation, test, split_rules = split_rows_with_rules(rows)
    uncalibrated_test = evaluate(test, weights, intercept)
    calibrated_test = evaluate(test, weights, intercept, calibrator)
    folds = walk_forward_report(rows)
    tours = sorted({match.tour for match in matches})
    tour_label = tours[0] if len(tours) == 1 else "mixed"
    coverage = {
        "start_date": matches[0].match_date.isoformat() if matches else None,
        "end_date": matches[-1].match_date.isoformat() if matches else None,
        "years": [matches[0].match_date.year, matches[-1].match_date.year] if matches else [],
    }
    report = {
        "status": "ok",
        "matches": len(matches),
        "feature_rows": len(rows),
        "players": len(players),
        "date_range": [matches[0].match_date.isoformat(), matches[-1].match_date.isoformat()] if matches else [],
        "splits": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
            **split_rules,
        },
        "models": {
            "logistic_regression": {
                "validation": evaluate(validation, weights, intercept),
                "test_uncalibrated": uncalibrated_test,
                "test": calibrated_test,
                "calibration": calibrator,
            },
            "overall_elo_baseline": benchmark_baseline(test, "overall_elo_diff"),
            "surface_elo_baseline": benchmark_baseline(test, "surface_elo_diff"),
            "ranking_baseline": benchmark_baseline(test, "ranking_diff"),
            "serve_return_baseline": benchmark_baseline(test, "serve_point_won_diff", 9.0),
        },
        "walk_forward": {
            "folds": folds,
            "summary": {
                "logistic": summarize_folds(folds, "logistic"),
                "surface_elo_baseline": summarize_folds(folds, "surface_elo_baseline"),
                "overall_elo_baseline": summarize_folds(folds, "overall_elo_baseline"),
                "ranking_baseline": summarize_folds(folds, "ranking_baseline"),
                "serve_return_baseline": summarize_folds(folds, "serve_return_baseline"),
            },
        },
        "leakage_control": "Features are snapshotted before Elo/form/H2H/stat updates for each same tournament/date batch.",
        "tensor_phase_status": {
            "phase_0_data_discovery": "implemented_for_supplied_csv_schema",
            "phase_1_temporal_store": "chronological_state_snapshots_before_update",
            "phase_2_baselines": "ranking_overall_elo_surface_elo_serve_return",
            "phase_3_scoring_engine": "closed_form_game_and_dp_tests_in_backend",
            "phase_4_serve_return": "beta_binomial_shrunk_match_aggregate_rates",
            "phase_5_plus": "not_promoted_without_extra_supported_inputs_or_validated_gain",
        },
    }
    source_files = data_files(DATA_DIR)
    if tour_label != "mixed":
        source_files = [path for path in source_files if detect_tour(path) == tour_label]
    artifact = {
        "model_version": f"courtiq-real-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "tour": tour_label,
        "feature_version": "courtiq_basic_temporal_v2",
        "training_cutoff": split_rules["train_rule"],
        "calibration_period": split_rules["calibration_rule"],
        "evaluation_period": split_rules["final_holdout_rule"],
        "temporal_policy_version": "same_tournament_date_batch_v1",
        "dataset_coverage": coverage,
        "data_source": "Local CSV files from work/tennis-data; supports Jeff Sackmann-style winner/loser CSVs and CourtIQ canonical Player_1/Player_2/Winner CSVs.",
        "data_snapshot_hash": data_snapshot_hash(source_files),
        "matches_processed": len(matches),
        "model": {
            "type": "calibrated_logistic_regression",
            "feature_names": FEATURE_NAMES,
            "coefficients": weights,
            "intercept": intercept,
            "calibration": calibrator,
        },
        "metrics": calibrated_test,
        "uncalibrated_metrics": uncalibrated_test,
        "players": player_payload(players),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    BACKTEST_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    export_feature_rows(rows)
    return report


def main() -> int:
    print(
        json.dumps(
            {
                "status": "legacy_entrypoint_disabled",
                "message": "Direct production training through scripts/train_match_model.py is disabled to prevent stale mixed or unsafe artifacts.",
                "use": [
                    "python scripts/train_models.py --tour atp",
                    "python scripts/train_models.py --tour wta",
                    "python scripts/train_models.py --tour all",
                ],
            },
            indent=2,
        )
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
