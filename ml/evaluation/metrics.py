from __future__ import annotations

from math import log


def accuracy(y_true: list[int], y_prob: list[float], threshold: float = 0.5) -> float:
    if not y_true:
        return 0.0
    correct = sum(int((p >= threshold) == bool(y)) for y, p in zip(y_true, y_prob))
    return correct / len(y_true)


def brier_score(y_true: list[int], y_prob: list[float]) -> float:
    if not y_true:
        return 0.0
    return sum((p - y) ** 2 for y, p in zip(y_true, y_prob)) / len(y_true)


def log_loss(y_true: list[int], y_prob: list[float], eps: float = 1e-9) -> float:
    if not y_true:
        return 0.0
    total = 0.0
    for y, p in zip(y_true, y_prob):
        p = min(1.0 - eps, max(eps, p))
        total += y * log(p) + (1 - y) * log(1 - p)
    return -total / len(y_true)
