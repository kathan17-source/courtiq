# CourtIQ interview notes

## Concise talking points

### Why did you build CourtIQ?

I wanted a tennis product that was not just “AI advice.” The interesting engineering problem is combining historical match data, surface-specific player strength, probability math, video movement analysis and a usable product surface without pretending the system knows more than it measures.

### What was the hardest technical problem?

The hardest part is the trust boundary: making predictions explainable while preventing temporal leakage and not overstating accuracy. Versioned ATP/WTA artifacts expose their cutoffs and held-out metrics, while unavailable live features are explicitly neutral rather than presented as measured facts.

### How does your Elo model work?

Each match is processed in chronological order. Before the match, expected win probability is computed from the rating gap. After the result, the winner gains rating and the loser loses rating by a K-scaled update. CourtIQ keeps overall and surface-specific ratings.

### Why surface-specific Elo?

Tennis player strength changes by surface. Grass, clay and hard courts reward different serve, movement and rally patterns, so a single global rating hides important signal.

### How did you prevent data leakage?

The intended pipeline only uses features available before match start. Elo is updated after prediction/evaluation, rolling features are prior-window features, and validation is chronological rather than randomly shuffled.

### Why chronological validation?

Sports prediction is a time-series problem. Random splits can train on future player form and test on past matches, which inflates performance.

### Why Brier score/log loss rather than only accuracy?

Accuracy ignores probability quality. A 51% prediction and a 95% prediction are both just “correct” or “wrong.” Brier score and log loss punish overconfidence and help evaluate calibration.

### Why did you choose the final ML model?

The repository contains separate versioned ATP and WTA logistic artifacts selected with chronological splits. They are credible research baselines, not guarantees of future performance or a substitute for ongoing drift evaluation.

### How are predictions calibrated?

Calibration parameters and held-out calibration metrics are stored with each artifact. ATP reports 2025 log loss 0.6185 and Brier 0.2154; WTA reports 0.6232 and 0.2172.

### How does the Monte Carlo simulator work?

It uses a deterministic random seed and repeatedly simulates match outcomes from model probabilities. Public requests are capped at 10K; tournament simulation precomputes each pair once.

### What is the time complexity?

Elo updates are O(M) for M matches. Feature generation is O(M × F) where F is the number of features per match. Monte Carlo simulation is O(S × P) where S is simulations and P is simulated points/games per match or bracket.

### How does the video analysis work?

The implemented math computes joint angles from 2D landmarks using vector geometry. The frontend supports video upload UX, and the backend validates upload metadata safely. Full ball tracking, RPM and winner/error detection are not claimed.

### What currently doesn’t work perfectly?

It remains a local prototype: artifacts are file-backed, profiles/plans live in browser storage, media analysis is single-camera 2D pose, and current artifacts cannot reconstruct arbitrary historical player state.

### What would you change with 10x traffic?

Move rate limiting to a proxy/shared cache, run video processing in isolated background workers, add OpenTelemetry, use managed PostgreSQL with read replicas where needed, cache hot model responses and deploy a versioned model artifact at startup.

### What would you improve next?

Add artifact governance and drift monitoring, tournament-entry metadata snapshots, stronger WTA serve-stat coverage, isolated media workers, authentication and shared persistence.

## Resume bullets

### SWE-focused

- Built a FastAPI/PostgreSQL tennis analytics backend with strict schemas, standardized error envelopes, request IDs, CORS config, upload validation and Docker/CI scaffolding.
- Implemented production-readiness guardrails for video uploads, including MIME/extension/size checks, UUID filenames, rate limiting and lifecycle indexes for temporary jobs.
- Created a static JavaScript product prototype with match prediction, training, gear and player flows backed by tested probability and rating services.

### ML/data-focused

- Designed a leakage-safe tennis prediction pipeline using chronological evaluation, surface-aware Elo features, Brier/log-loss metrics and explicit pending-metric handling when data is absent.
- Implemented tennis probability utilities for point-to-game conversion, best-of-3/best-of-5 match probability and deterministic Monte Carlo simulation.
- Added reproducible chronological evaluation, artifact validation and deterministic simulation tests without presenting benchmark metrics as future guarantees.

### Quant/math-focused

- Implemented sequential Elo updates, surface-weighted rating blends and analytic tennis scoring probabilities to model match win probability under surface and format changes.
- Bounded public Monte Carlo requests at 10,000 simulations and precomputed tournament pair probabilities to control work.
- Documented calibration-oriented evaluation using Brier score, log loss and chronological backtesting instead of relying on headline accuracy.

## 20 skeptical interviewer questions

1. **Why should I trust this model?**  
   Trust is bounded: use the disclosed 2025 held-out metrics and artifact cutoffs as evidence for the research baseline, then monitor prospective calibration and drift before production use.

2. **How do you know you aren’t leaking future data?**  
   Elo updates happen after prediction/evaluation, and feature definitions are pre-match features. The planned split is chronological.

3. **Isn’t Elo enough?**  
   Elo is a strong baseline, but tennis has surface, fatigue, serve/return and form effects. The code treats Elo as the foundation, not the final word.

4. **Why would gradient boosting outperform logistic regression?**  
   It might not. The README lists it as future work, not a proven result. The final choice should be based on chronological validation.

5. **What happens for a player with only three matches?**  
   The rating keeps high uncertainty and should be treated as a cold-start case. The current code includes uncertainty drag in blended ratings.

6. **What is your cold-start strategy?**  
   Use conservative base ratings, uncertainty penalties and avoid confident claims until enough matches exist.

7. **How do you handle changing player strength?**  
   Sequential updates and recency weighting are included/planned so recent results affect ratings more than stale history.

8. **Why is surface weighting reasonable?**  
   Tennis outcomes are surface-dependent. A clay specialist and grass specialist can have similar global strength but different matchup probabilities.

9. **What happens when match data is missing?**  
   The backend returns pending/no-data states rather than inventing stats.

10. **How do you know video angle measurement is accurate?**  
    The current implementation only provides joint-angle math; real accuracy requires landmark confidence, camera-angle metadata and validation against labelled video.

11. **Why FastAPI?**  
    It gives typed request validation, generated API docs, async support and simple Python deployment for ML-adjacent services.

12. **Why PostgreSQL?**  
    The data is relational: players, aliases, tournaments, matches, point events, model versions and backtests need constraints and joins.

13. **What breaks at 100K users?**  
    In-process rate limiting, local static hosting, synchronous heavy video work and single-node assumptions.

14. **How do you evaluate calibration?**  
    Bucket predicted probabilities and compare average confidence with observed accuracy; also report Brier score and log loss.

15. **Why not random train/test split?**  
    It leaks future player form into past predictions.

16. **What if the model is overconfident?**  
    Log loss and calibration expose overconfidence; calibration can be fixed with validation-set methods once real data exists.

17. **Where are the real historical data sources?**  
   The reproducible pipeline reads the ATP/WTA files under `work/tennis-data`; distribution rights and coverage should be reviewed before external publication.

18. **Is the frontend production-ready?**  
    It is a strong static prototype, not a hardened deployed SPA. The backend hardening work is more production-oriented.

19. **How do you test malformed uploads?**  
    `tests/test_upload_security.py` covers unsafe filenames, oversized uploads and safe UUID filename generation. A stress helper rejected 5,000 malformed uploads.

20. **What is the most honest limitation?**  
    Without imported historical match data and a saved backtest, CourtIQ can demonstrate engineering depth but cannot claim real predictive accuracy.
