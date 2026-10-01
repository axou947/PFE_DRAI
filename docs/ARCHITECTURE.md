# Architecture

```
            config/settings.yaml
                    │
 DataProvider ──► align + features ──► scores (stress, growth, inflation)
 (synthetic,        (point-in-time)          │
  csv, fred,                                 ├──► models (kmeans, jump, gbm) ──► walk-forward probabilities
  yahoo, …)                                  │                                        │
                                             └──► rule labels (gbm target)            ├──► validation (episodes, latency, FP, Brier)
                                                                                      ├──► alerts
                                                                                      ├──► scenarios + fund impact
                                                                                      ├──► committee note (FR/EN)
                                                                                      └──► daily publication
```

`pfe_drai.pipeline.Pipeline` runs this chain once and caches it. The Streamlit app, the API,
the CLI and the tests all use it, so a setting changed in `config/settings.yaml` reaches
every screen.

## Ajouter une source de données

1. Create `pfe_drai/data/my_source.py`:

   ```python
   from .base import DataProvider, register


   @register
   class MySource(DataProvider):
       name = "my_source"

       def fetch(self, start, end):
           # return {series name: pd.Series indexed by date}
           # names: see pfe_drai/data/catalog.py (equity, vix, hy_bond, …)
           ...
   ```

2. Import it in `pfe_drai/data/__init__.py`.
3. Set `data.provider: my_source` in `config/settings.yaml`. Put secrets in environment
   variables, never in the YAML.
4. Run `pytest` and `python -m pfe_drai backtest`.

Monthly series are returned at their reference date; the pipeline shifts them by
`data.publication_lag_days` so the model only sees what was published on each day.
For revised series (IP, CPI), `fetch_fred(..., vintage=...)` reads ALFRED vintages.

Each catalog entry records a `licence` (research / commercial / check), following the
re-audit: BAA10Y (Moody's) and Yahoo data are research-only; ICE BofA spreads are not used.

Real data = FRED (macro, VIX) + Tiingo (ETF prices). FRED allows commercial use with its
disclaimer; third-party series need the owner's permission (VIXCLS: cite Cboe). FRED SP500
is not used: it starts in 2016 and S&P forbids reproduction. Tiingo's free tier is enough for
research; internal commercial use is a paid plan. HYG starts in 2007, so real-data history
starts in 2008 once z-scores have a year of data.

## Ajouter un modèle

Subclass `RegimeModel` in `pfe_drai/models/`, implement `fit` and `predict_proba`
(one column per regime, rows sum to 1), decorate with `@register`, import it in
`pfe_drai/models/__init__.py`. It then appears in the app, the API, the backtest and the tests.
Unsupervised models name their states with `regimes.match_states` (closest prototype).

## Ajouter une langue

Copy `locales/en.json` to `locales/<code>.json`, translate the values and add the code to
`SUPPORTED` in `pfe_drai/i18n/__init__.py`. `tests/test_i18n.py` checks that every key and
placeholder exists in each language.

## Validation rules (fixed before testing)

- Episode start: first crossing of a −10 % drawdown from the 252-day high, or 21-day realised
  volatility above its expanding 95th percentile; at least 126 business days between starts.
- Episode end: drawdown back above −5 %, or 126 business days.
- Detection: P(stress) above the threshold for 3 consecutive days, between 20 days before and
  60 days after the start. Latency is reported for every episode, not only the median.
- False positive: a detection onset outside every episode (widened by 20 days before).

## Données simulées

`pfe_drai/data/synthetic.py` follows a regime path that mirrors the main crises since 2000
(`SCRIPT`), fills the gaps with a persistent random chain and generates every series from
regime-dependent dynamics (volatility, spreads, rates, inflation, activity). The true regime
is known, so the app also shows accuracy against it. Change `data.seed` for another history.
