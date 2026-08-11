# CourtIQ algorithms

## 1. Elo expected score

Purpose: estimate pre-match win probability from player strength.

Formula:

```text
E_A = 1 / (1 + 10^((R_B - R_A)/400))
```

Programmatic location: `backend/app/services/elo_service.py`.

Assumptions:

- Rating difference captures expected strength gap.
- Ratings are updated sequentially after matches.

Complexity: O(1) per match prediction.

Limitations:

- Elo alone does not model injuries, tactics or missing data.

## 2. Surface Elo

Purpose: account for player strength differences on hard, clay and grass.

Implementation:

```text
blended_rating = 0.62 * surface_elo + 0.30 * overall_elo - 0.08 * uncertainty
```

Assumptions:

- Surface-specific history adds signal beyond global strength.
- Uncertain players should be penalized until more data exists.

Complexity: O(1) per rating lookup/update.

Limitations:

- Requires enough surface-specific matches; cold-start players remain uncertain.

## 3. Recency weighting

Purpose: reduce the influence of stale results.

Formula:

```text
weight = exp(-(ln 2 / half_life_days) * days_old)
```

Programmatic location: `recency_weight` in `backend/app/services/elo_service.py`.

Assumptions:

- Player level changes over time.
- A smooth decay is more stable than hard cutoffs.

Complexity: O(1) per weighted event.

Limitations:

- Half-life must be validated empirically.

## 4. Rolling statistics

Purpose: capture recent form, serve/return strength and fatigue proxies using only previous matches.

Example features:

- Previous 5/10-match win rate
- Serve hold-rate difference
- Return break-rate difference
- Days-rest difference
- Prior head-to-head before match date

Complexity: naive O(M × W), where M is matches and W is rolling window size; can be optimized to O(M) per player with queues.

Limitations:

- Missing stats reduce signal.
- Rolling windows can be noisy for low-volume players.

## 5. Point-to-game probability

Purpose: convert probability of winning a serve point into probability of holding serve.

Formula:

```text
P(game) = P(win before deuce) + P(reach deuce) * P(win from deuce)

P(win before deuce) = p^4 * (1 + 4q + 10q^2)
P(reach deuce) = 20p^3q^3
P(win from deuce) = p^2 / (p^2 + q^2)
```

Programmatic location: `backend/app/services/tennis_math.py`.

Complexity: O(1).

Limitations:

- Assumes point probability is stationary within the game.

## 6. Set-to-match probability

Purpose: convert set win probability to match win probability.

Best-of-3:

```text
P(match) = p^2 * (3 - 2p)
```

Best-of-5:

```text
P(match) = p^3 * (1 + 3(1-p) + 6(1-p)^2)
```

Complexity: O(1).

Limitations:

- Assumes independent set outcomes.

## 7. Monte Carlo simulation

Purpose: estimate match or bracket outcomes by repeated random sampling with a reproducible seed.

Implementation:

- Seed a pseudorandom generator.
- Simulate many matches/brackets.
- Count player/tournament wins.
- Return empirical probability.

Programmatic locations:

- `backend/app/services/simulation_service.py`
- `scripts/benchmark_simulation.py`
- `scripts/benchmark_core.py`

Complexity:

```text
O(S × P)
```

where S is simulation count and P is simulated points/games/matches per simulation.

Limitations:

- Accuracy depends on input probabilities.
- Long simulations should be cached or moved off the hot request path.

## 8. Prediction calibration

Purpose: test whether predicted probabilities match observed outcomes.

Method:

- Bucket predictions, for example 50–60%, 60–70%, 70–80%.
- For each bucket, compare average predicted confidence with actual observed win rate.
- Report Brier score and log loss.

Complexity: O(N) for N predictions.

Limitations:

- Needs enough held-out historical matches.
- This local checkout has no imported CSV dataset, so calibration metrics are pending.

## 9. Pose joint-angle calculation

Purpose: convert three 2D landmarks into a joint angle for biomechanics notes.

Formula:

```text
angle = arccos((BA · BC) / (|BA| |BC|))
```

Programmatic location: `backend/app/services/video_analysis.py`.

Complexity: O(1) per joint per frame.

Limitations:

- 2D angles depend on camera angle.
- Landmark confidence and smoothing are required for production-grade video analysis.
- Ball speed, spin RPM and unforced errors are not measured by this helper.
