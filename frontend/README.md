# Frontend migration target

The live product currently remains in:

```text
outputs/tennis-ai-app/
```

This `frontend/` folder is reserved for the next refactor where the large static JavaScript file is split into maintainable modules without breaking the current product.

Target structure:

```text
frontend/src/
  components/
  pages/
    Predictor/
    Analyze/
    Training/
    Players/
    Tournaments/
  services/
  hooks/
  utils/
  types/
```

Migration rule: move one feature at a time and keep `outputs/tennis-ai-app/index.html` working after every step.
