# Euro-area macro regimes: data decisions and pre-registration

**Status: PRE-REGISTERED, nothing run on real data yet.** The euro-area model (`--region euro`, `models.version: euro-v1`)
is an addition: the US model (v2.2), its frozen episode rule, its daily publication and its track record are not
touched. This page fixes the data, the episode rule, the regime thresholds, the selection procedure and the numeric
decision rule **before any real euro-area run**. The results are added under "Results" as they come out and nothing
above that heading changes afterwards. A failure is published and the euro view stays labelled experimental.

Everything is in `config/regions/euro.yaml` (deep-merged over `config/settings.yaml` by `--region euro`). The US run is
`settings.yaml` alone: no `region` key, same settings fingerprint, same published files (tested in `tests/test_euro.py`).

## What the euro model reads

The pipeline, features, models and calibration are the US ones, unchanged. Only the inputs differ. The euro provider
(`pfe_drai/data/euro.py`) returns the pipeline's column names with their euro-area meaning:

| Pipeline column | Euro-area series | Source | Frequency | Release lag used | Vintages | Licence |
|---|---|---|---|---|---|---|
| `equity` | EZU (iShares MSCI Eurozone), USD price | Tiingo | daily | 0 | n/a (price) | as the US ETFs: a paid plan for internal commercial use, no redisplay of prices |
| `vix` | 21-day realised volatility of EZU, annualised, in % | computed | daily | 0 | n/a | derived |
| `us10y`, `us2y` | AAA euro-area government yield curve, spot 10y and 2y (`YC`, `B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y` / `SR_2Y`) | ECB Data Portal | daily | 1 day | no, end-of-day curve | ECB open data, source acknowledged |
| `credit_spread` | 10y all-issuer euro-area yield minus the AAA 10y (`...G_N_C...` minus `...G_N_A...`) | ECB Data Portal | daily | 1 day | no | ECB open data |
| `cpi` | HICP overall index, euro area (`ICP`, `M.U2.N.000000.4.INX`) | ECB Data Portal (Eurostat's `prc_hicp_midx` ended in December 2025 in the 2026-10-01 run, probably replaced when HICP changed classification) | monthly | 18 days after month end | no public vintages; rarely revised | Eurostat open data |
| `indpro` | Industrial production, B-D, calendar adjusted (`sts_inpr_m`, I21, EA20 code) | Eurostat | monthly | 50 days | no public vintages; **revised** | Eurostat open data |
| `claims` | Unemployment rate, seasonally adjusted (`une_rt_m`, EA21 code) | Eurostat | monthly | 35 days | no public vintages; revised slightly | Eurostat open data |

Not used, on purpose: **PMIs** (S&P Global, licensed), **VSTOXX** (STOXX, licensed), **iBoxx** and index levels
(licensed), the daily Italy-Germany spread (no free daily source found: the ECB's long-term rate statistics are monthly),
the European Commission sentiment indicator (not needed: the growth score keeps the US v2.2 inputs, no new choice).

### Weaknesses, stated up front

1. **Not fully point-in-time.** Neither ECB nor Eurostat exposes first releases through its public API. Every monthly
   series is dated by a conservative release lag, so no value is visible before it could have been public, but
   **industrial production and unemployment are revised after release and the backtest sees the revised values** (the
   US model reads ALFRED first releases). Daily curves are not revised. The ECB's Real-Time Database could give vintages
   for some series; it is not used here, and `data.point_in_time: false` style shortcuts are not offered.
2. **The ETF is in dollars.** EZU is a US-listed fund: its price mixes euro-zone equities and EUR/USD. This inflates
   volatility and drawdowns when the euro moves and can date an episode the euro-area market did not have.
3. **"VIX" is realised, not implied.** The euro `vix` is the same information as the `realised_vol` feature, so the
   stress score weighs realised volatility twice and has no forward-looking volatility input.
4. **No daily breakeven.** The inflation dimension drops `breakeven_level` and `breakeven_change` (`features.drop`) and
   reads HICP year-on-year and the change of the 2-year yield only. Overheating is the weakest regime in the euro
   model. The ECB survey of professional forecasters is quarterly and the 5y5y inflation swap is licensed: neither is used.
5. **Credit is a sovereign proxy.** `credit_spread` measures how much the all-issuer curve sits above the AAA curve
   (peripheral and non-AAA sovereign stress), not corporate credit. No free euro corporate-bond price series was found.
6. **Short history.** The ECB yield-curve data starts in September 2004 and Tiingo's EZU in January 2001: features start on
   2006-03-07 and the first out-of-sample prediction is on 2011-03-08 (`data` run of 2026-10-01). The euro backtest has fewer episodes
   than the US one and the 2010-2012 sovereign crisis is only partly inside it. Do not read the euro model as validated like the US one.
7. Eurostat re-bases its indices and changes euro-area codes (EA, EA20, EA21). Each Eurostat series lists `alternatives` in the
   overlay, tried in order if the filters match nothing; they identify the same series under another code, they are not a data
   choice, and `data` prints the filters that worked.
8. The `YC` series keys and the Eurostat dataset codes and filters above were written from the documentation without
   network access (the build environment cannot reach either server). Phase A (`data`, below) is the check: a wrong key stops the run
   with the server's message, it never produces silent numbers.

## The episode rule for the euro area (frozen)

The US rule's **parameters, unchanged**, applied to the EZU price: a start is a fresh crossing of a −10% drawdown from the
252-day high or of 21-day realised volatility above its expanding 95th percentile; gap, recovery and maximum duration as in
`validation.episodes`. No new degree of freedom is introduced. Because the parameters are identical, the sha256 is the same as
the US one: `6741b6747b53b7cf5c1f9de0c5fedd9caccd111d49c9dbf63fde3a2010b8397a`. It is frozen in the euro overlay on its own
(`validation.episodes.frozen`, date 2026-10-01): the code refuses a euro run whose parameters no longer match it, and the US check is untouched.

The dated euro episodes have **not** been looked at before this freeze. What the rule may miss or add: part of 2010-2012 was a
spread event more than an equity drawdown (the equity line may open an episode in 2011 and not in 2010 or early 2012); dollar
moves of the ETF can open an episode of their own (limit 2 above).

## Regimes, models, selection

- **Regimes.** The same three dimensions and `regimes.rule` with the US values (stress 1.0, growth 0.0, inflation 0.8), the
  v2.2 growth score (four inputs, robust scaling, 21-day average). Nothing is tuned on the euro period.
- **Models.** Exactly the US v2.2 chain (jump + gbm + onset, calibrated P(stress)); no new model in this item.
- **Real holdout (the only selection on real data).** `validation.holdout` in the overlay: EZU's start to the day before the
  euro out-of-sample period (about 2010), two candidates for the onset detector (`logistic` or `gbm` on `market` inputs;
  `market_credit` does not exist for the euro). Rule: `select()` of `validation/holdout.py`, as in
  [DETECTION_V2.md](DETECTION_V2.md). The window is shorter than the US 1993-2009 and trains on 5 years, so it can
  select between two learners and nothing more. The holdout runs from 2001-01-02 to 2011-03-07, the day before the first out-of-sample day shown by `data`.
- **Simulated data.** The simulator is shared with the US model (euro-shaped payloads are built from it in
  `tests/test_euro.py`); it checks that the whole chain runs on euro inputs, not that the model is right for the euro area.

## Decision rule (numeric, fixed before any real run)

One real run: `python -m pfe_drai --region euro --provider euro backtest`, then `calibration` and `states` on the same data.
Euro v1 **passes** only if every condition holds for the default (`combined`) model on the out-of-sample days:

1. at least 6 episodes are dated by the frozen rule (fewer = inconclusive, not a pass);
2. at least 80% of the episodes are detected;
3. median detection latency over detected episodes at most 5 business days (`validation.targets`);
4. at most 1.5 false alarms a year;
5. at most 10% of calm days with the alarm on;
6. calibrated P(stress): ECE at most 0.08 and Brier below that of always predicting the observed frequency (skill > 0);
7. a Slowdown state is named in at least half of the walk-forward refits (`states`).

If all hold, the euro view may be published daily in `track_record/euro/` (a separate PR switches `publish.enabled` and adds a
`continue-on-error` step to `.github/workflows/publish.yml`, so a euro failure cannot cost the US day). If one fails, the
results are published here, the UI keeps the "experimental" label and nothing is published daily. The real episodes are then
"seen": any retuning needs its own pre-registration.

## Procedure (Henry, Windows PowerShell, in this order)

1. `python -m pfe_drai --region euro --provider euro data`: coverage per series (first and last observation, release lag,
   vintage, licence) and where the backtest starts. **Phase A.** It needs `TIINGO_API_KEY` and no ECB or Eurostat key.
2. `python -m pfe_drai --region euro --provider euro holdout`: the only selection on real data; the chosen candidate goes into the overlay.
3. `python -m pfe_drai --region euro --provider euro backtest`, `calibration`, `states`: **once.** Results below.

## Results

*(empty: nothing has been run on real data yet)*
