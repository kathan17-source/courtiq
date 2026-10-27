# Actual application screenshots

The README uses unmodified Chromium screenshots of the running local CourtIQ frontend and FastAPI backend, captured by `tests/browser/recruiter-captures.mjs` in [CI run 40464911480](https://github.com/kathan17-source/courtiq/actions/runs/40464911480), revision `c608f46`. No response mocks, generated interface drawings, private uploads or fabricated results were used.

- **Predict:** actual Alcaraz–Sinner prediction and the current ATP evaluation warning. Working inference does not establish validated performance.
- **Analyze:** actual “Waiting for footage” upload-ready interface. No video was uploaded; this capture does not demonstrate successful pose extraction.
- **Simulation:** actual backend response for eight illustrative historical players, 2,000 brackets and seed 42. The roster includes retired players and is not a current tournament draw.

To reproduce, install the development and browser dependencies as in `.github/workflows/ci.yml`, start `python scripts/run_courtiq.py`, then run `node tests/browser/recruiter-captures.mjs`. The script waits for actual API responses, fonts and transient notifications before capture. Player aggregates come from the shipped artifact; no provider dataset or private recording is embedded in these images.

## File integrity

SHA-256 values of the original CI PNG files copied into `docs/assets/`:

```text
a9ce39f1bcaa14c8c17af548e27bdabb3b29265c67e1d5448fb02d4b461e2864  courtiq-predict.png
d7cc61947675ab6610cb7b0eb5398cf2fbc2bd2c561e6711675e463349a72ab4  courtiq-analyze.png
4af65d91150cd029e4bc745b36996ed272bbc6abcdba01c6888e92e6d1545489  courtiq-simulation.png
```

Existing project rights and research limitations apply. Screenshots are interface evidence, not independent model validation or permission to reuse third-party material.
