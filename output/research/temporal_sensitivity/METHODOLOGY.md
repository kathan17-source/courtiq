# ATP temporal sensitivity

Round-safe updates player state only after every match in an earlier round has been snapshotted. Tournament-frozen snapshots every match in a tournament from player state at tournament entry and applies results only after all tournament predictions. Both modes use the identical fixed enhanced-runtime-safe feature specification, training years through 2023, 2024-only calibration, and the 2025 held-out benchmark. No production artifact is written or promoted.

Reproduce: `.venv/bin/python scripts/run_temporal_sensitivity.py`
