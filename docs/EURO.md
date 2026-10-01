# Euro-area macro regimes: data decisions and pre-registration

**Status: RUN on 2026-10-01 and NOT PASSED (condition 6, see Results): the euro view stays experimental and is not published daily.** Pre-registered the same day, before any real euro run. The euro-area model (`--region euro`, `models.version: euro-v1`)
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
| `cpi` | HICP overall index, euro area (`HICP`, `M.U2.N.000000.4D0.INX`) | ECB Data Portal (the ECB replaced its `ICP` dataset by `HICP` on 4 February 2026 for Eurostat's new methodology, and Eurostat's `prc_hicp_midx` also ended in December 2025; both ends were seen in the 2026-10-01 run) | monthly | 18 days after month end | no public vintages; rarely revised | ECB open data, HICP produced by Eurostat |
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

### Phase A: coverage, run by Henry on 2026-10-01 (no model, before any real run)

| Series | First | Last | Filters that matched |
|---|---|---|---|
| equity (EZU) | 2001-01-02 | 2026-10-01 | n/a |
| vix (realised) | 2001-02-01 | 2026-10-01 | computed |
| us10y, us2y, credit_spread | 2004-09-07 | 2026-10-01 | ECB `YC` keys of the overlay |
| cpi | 2000-08-18 | 2026-09-18 | ECB `HICP` `M.U2.N.000000.4D0.INX` |
| indpro | 2000-09-19 | 2026-09-19 | `sts_inpr_m`, `EA20`, I21 |
| claims (unemployment) | 2000-09-04 | 2026-10-05 | `une_rt_m`, `EA21` |

Features start on 2006-03-07; the euro out-of-sample period starts on 2011-03-08 (`validation.min_train_days: 1260`).

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

### Step 1: holdout (real data, run once by Henry, 2026-10-01)

Window 2001-01-02 to 2011-03-07, predictions from 2007-02-09, 4 episodes dated by the frozen rule (2007-08-14, 2008-01-16, 2010-01-22, 2010-11-23).

| candidate | episodes | detected | median latency | all episodes | FP/yr | calm days in alarm | Brier |
|---|---|---|---|---|---|---|---|
| logistic / market | 4 | 3 | 11.0 | 11.5 | 0.49 | 5.2% | 0.240 |
| gbm / market | 4 | 4 | -14.5 | -14.5 | 1.47 | 3.0% | 0.216 |

Latency per episode (business days, negative = signal already on): logistic +9, +11, +12, missed; gbm -10, -19, -20, -3.

Selected by the pre-registered rule: **gbm / market**, which the US model already uses; it is set in the overlay (`models.onset`). Read with care: only 4 episodes, and the gbm's false alarms (1.47 a year) sit just under the 1.5 limit.

### Step 2: the real backtest (run once by Henry)

Run once by Henry on 2026-10-01 (`--region euro --provider euro backtest`, then `calibration` and `states` on the same fits), out-of-sample 2011-03-08 to 2026-10-01, 3,911 days, 12 episodes dated by the frozen rule.

| model | episodes | detected | median latency | all episodes | FP/yr | calm days in alarm | Brier | ECE |
|---|---|---|---|---|---|---|---|---|
| combined (the model) | 12 | 11 | 2.0 | 2.0 | 0.77 | 8.4% | 0.173 | 0.051 |
| v2 (same alarm, uncalibrated P) | 12 | 11 | 2.0 | 2.0 | 0.77 | 8.4% | 0.202 | 0.174 |
| onset alone | 12 | 10 | 0.0 | 2.0 | 0.64 | 2.2% | 0.188 | 0.173 |
| v1 (jump + gbm) | 12 | 3 | 13.0 | 60.0 | 0.19 | 6.4% | 0.220 | 0.206 |
| gbm, jump, kmeans alone | 12 | 3, 2, 2 | 13, 29, 25.5 | 60 | 0.13 to 0.51 | 4.5 to 5.8% | 0.20 to 0.23 | 0.19 to 0.23 |

Latency per episode, `combined` (business days, negative = signal already on): 2011-06-15 -15; 2014-08-06 +55; 2015-08-21 +9; 2018-05-29 +12; 2019-08-14 +2; 2020-02-27 +9; 2020-10-27 -20; 2022-02-22 -4; 2023-09-25 **missed**; 2024-11-12 -2; 2025-04-04 +2; 2026-03-13 -3. All 12 episodes were opened by the drawdown line.

Calibration: Brier 0.173 against 0.202 uncalibrated, ECE 0.051 against 0.174, but **Brier skill -0.02**: the calibrated probability is no better than always saying the observed frequency (21.7%). The calibrator's weight on the alarm score stayed between 0.00 and 0.13 at every refit, so the calibrated P(stress) only moves between about 17% and 34%. The uncalibrated detector score is badly over-confident: days above 90% were in the stress event 40.8% of the time.

States: the Slowdown state is named in 22 of 32 refits (not in 2012-2017 refits 10 times); agreement with the rule is a median 69% (lowest 32%).

### Decision rule applied (the conditions are those fixed above, not edited)

| # | Condition | Result | Met |
|---|---|---|---|
| 1 | at least 6 episodes | 12 | yes |
| 2 | at least 80% detected | 11 of 12 (92%) | yes |
| 3 | median latency at most 5 days | 2.0 | yes |
| 4 | at most 1.5 false alarms a year | 0.77 | yes |
| 5 | at most 10% of calm days in alarm | 8.4% | yes |
| 6 | ECE at most 0.08 and Brier skill above 0 | ECE 0.051, **skill -0.02** | **no** |
| 7 | Slowdown named in at least half of the refits | 22 of 32 (69%) | yes |

**Verdict: euro v1 does not pass** (6 of 7 conditions; condition 6 fails on skill). Consequences, as pre-registered: the results stay published here, the euro view stays labelled experimental, `publish.enabled` stays false and no euro daily record or workflow step is added. The euro alarm detects crises quickly (the detection conditions all hold), but the euro probability should not be read as a probability.

### What this does and does not show

- It does not show the euro area is harder than the US in general: the euro data are shorter, partly revised, and the ETF is priced in dollars, so some episodes may be currency moves (the 2020-10 and 2024-11 starts are candidates; not checked).
- The alarm stays on after an episode ends by the rule's recovery line, which explains the over-confidence of the raw score: this is a hypothesis, not tested.
- The real euro episodes are now seen. Any retuning (a euro-denominated series, a different calibration) needs its own pre-registration with a stated reason written beforehand.
