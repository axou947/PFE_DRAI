# PFE DRAI — détection de régime de marché + IA / market regime detection + AI

Explainable market regime detection for small asset managers and family offices.
The product is bilingual (FR/EN): all user-facing text lives in `locales/`.

## Regimes

Regimes are defined on three dimensions: **stress**, **growth** and **inflation**.
The mapping from model states to named regimes, and the rule that dates the start of each
stress episode, are written down before any backtest.

## Structure

```
pfe_drai/
  data/        # ingestion (FRED/ALFRED, ETF prices), point-in-time aware
  features/    # stress, growth and inflation dimensions; credit proxies (HYG/LQD/IEF)
  models/      # k-means baseline, Statistical Jump Model, gradient boosting
  validation/  # walk-forward, purged CV, detection latency, calibration
  scenarios/   # historical stress scenarios, regime-conditioned selection, fund impact
  reporting/   # risk committee note (FR/EN), PDF export
  publish/     # daily snapshot -> track_record/, externally timestamped (OpenTimestamps)
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
