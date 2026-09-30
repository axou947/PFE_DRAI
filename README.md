# PFE DRAI — détection de régime de marché + IA / market regime detection + AI

Explainable market regime detection for small asset managers and family offices.
The product is bilingual (FR/EN): all user-facing text lives in `locales/`.

## Structure

```
pfe_drai/
  data/        # ingestion (FRED/ALFRED, ETF prices), point-in-time aware
  features/    # the two regime axes, free credit proxies (HYG/LQD/IEF)
  models/      # k-means baseline, Statistical Jump Model, gradient boosting
  validation/  # walk-forward, purged CV, detection latency, calibration
  publish/     # daily timestamped snapshot -> track_record/
  i18n/        # t(key, lang) loader for locales/{fr,en}.json
locales/       # fr.json, en.json
app/           # Streamlit dashboard (later)
api/           # FastAPI GET /regime (later)
track_record/  # one JSON per day, committed by CI
tests/
```

## Setup

```
pip install -e ".[dev]"
pytest
```
