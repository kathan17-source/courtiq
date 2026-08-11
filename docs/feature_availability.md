# Prediction feature availability

CourtIQ distinguishes measured artifact state from values unavailable in a name-only live request.

| Feature family | Live source | Contract |
|---|---|---|
| Overall/surface Elo, uncertainty, prior match counts | Versioned player snapshot | Available at the artifact state cutoff. |
| Ranking, ranking points, age, height, hand | Versioned player snapshot | Latest serialized value; missing values retain the artifact's documented neutral encoding. |
| Rolling serve/return statistics and residual forms | Versioned player snapshot | Prior-match aggregates only, subject to tour/source coverage. |
| Days rest, recovery curve, 3/7/14-day workload | No match date or schedule supplied | Explicit neutral defaults at live inference; these are not measured zeros. |
| Head-to-head and surface head-to-head | No opponent-pair history supplied to the runtime artifact | Explicit neutral defaults; not a claim that the players have never met. |
| Surface | Known event map or explicit request field | Unknown events are rejected unless the caller supplies hard, clay or grass. |

`training_cutoff`, `evaluation_cutoff`, serialized player-state cutoff, artifact creation time and temporal-policy version are exposed in prediction diagnostics. Supplying `as_of` records the requested date but does not reconstruct historical state; the response warns about that boundary.
