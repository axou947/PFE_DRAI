# Stress detection v2: pre-registration

**Status: adopted on 2026-10-01** (decision rule met, results at the bottom). Pre-registered
the same day, **before any run of v2 on real data** (neither the holdout
nor the 11 published episodes). This page fixes what will be tested, on which data, and how the
result decides. It is committed and pushed before Henry runs anything; the results are added
below it afterwards, as they come out, and nothing above the "Results" heading changes.

## Why v1 is slow on real data

v1 (`combined` = jump regimes, P(stress) = max(jump, gbm), [DETECTION.md](DETECTION.md)) caught
5 of the 11 real out-of-sample episodes, median latency 11 days, 0.17 false positives a year.
Reading the code, not the episodes, gives two reasons:

1. **The models learn a different event from the one they are scored on.** gbm learns the rule
   label "stress score above 1", where the stress score averages four slow z-scores (VIX,
   21-day vol, a quarter of credit spread change, drawdown). The track record scores the
   episodes of the frozen rule: a 10% fall or a volatility spike. A 10% fall can happen while the
   stress score stays below 1, and then no model trained on that label can call it, however fast.
   The ceiling is the label, not the model.
2. **The inputs are slow and their scale drifts.** Expanding z-scores over a history that holds
   2008 shrink every later reading (a VIX of 35 in 2018 scores lower than it would have in 2006),
   and a quarter-long credit change reacts late by construction.

We know which real episodes v1 missed (DETECTION.md publishes them). Nothing below was chosen by
looking at them: no v2 variant was ever run on real data, and every choice was made on simulated
data, with the reasons above fixed first.

## What v2 is

A stress-onset detector (`models/onset.py`), added as a second stress source of `combined`:
P(stress) = max(jump, gbm, onset).

- **Target**: the frozen episodes themselves, not the rule label: "an episode starts within 5
  business days, or started less than 21 business days ago" (`validation.onset_target`). It
  teaches the start of a fall, not the state of a long one.
- **Inputs** (`features/market.py`), daily and in their own units, so a value means the same
  thing in 1998 and 2025: drawdown, 5/10/21-day returns, 5/10/21-day realised vol, 21-day vol
  over the frozen rule's volatility line, VIX, its 5-day log change, VIX over its 3-month mean.
  Optionally investment-grade credit (LQD against IEF, 5 and 21 days): LQD, not HYG, because HYG
  starts in 2007 and one series must keep one meaning across the whole history.
- **Hold**: a probability holds 5 days (minimum time on), so the signal does not flicker around
  0.5 during a fall.
- **Walk-forward** as the other models: refit every 252 days on the past only, the last 5 days of
  each training window dropped (their target is not known yet). Tests check that removing the
  last two years of data changes no earlier prediction (`tests/test_onset.py`).

By construction v2 can only raise P(stress), so on any data it detects every episode v1 detects,
no later. What it can cost is false alarms; that is what the decision rule below watches.

### A metric that could be fooled, and the fix

False positives count alarm **onsets** outside episodes. A signal that turns on once and stays
on would score almost none, and median latency over detected episodes improves by missing the
hard ones. So v2 is also judged on two numbers fixed now, before any real run:

- **median latency over all episodes**, a missed one counting as the end of the detection window
  (60 days): `median_latency_all`;
- **false alarm share**: share of calm days (outside every episode and its 20-day lookback) with
  the stress signal on. Target ≤ 10% (`validation.targets.max_false_alarm_share`): the audit's
  1.5 false alarms a year, of about three weeks each.

## How it was designed (simulated data only)

Development on seeds 1–8 (137 episodes), as in DETECTION.md. Tried, in this order:

| onset variant (combined with jump + gbm)              | detected | median lat. | all eps. | FP / yr | false alarm | switches / yr |
|-------------------------------------------------------|---------:|------------:|---------:|--------:|------------:|--------------:|
| v1 (no onset)                                         |  80/137  |   −5.0      |  33.0    |  0.17   |   8%        |  2.4          |
| target = in an episode within 5 days, no hold, gbm    | 129/137  |   −4.0      |  −4.0    |  1.45   |  16%        | 15.3          |
| same, hold 10 days                                    | 134/137  |   −9.0      |  −8.0    |  1.01   |  27%        |  4.9          |
| **target = episode start window, hold 5, gbm**        | 131/137  |   −4.0      |  −3.0    |  0.52   |  10%        |  4.6          |
| target = episode start window, hold 5, logistic       |  94/137  |   −5.0      |   4.0    |  0.21   |   8%        |  2.9          |

- The first target (episode membership) learned "deep drawdown = stress": many false alarm days in
  long bear markets after an episode ends, and a flickering regime. Holding the signal 10 days cut
  the onsets but raised alarm time from 16% to 27% of calm days, which is how the need for the
  false alarm share was found. **Not kept.**
- The start-window target keeps almost all the detections (131 of 137) with a third of the false
  positives (0.52 a year against 1.45) and 2 more points of alarm time instead of 8 to 19. **Kept.**
- Hold: without it, 127 detections and 6.8 switches a year; 5 days gives 131 and 4.6; 10 days the
  same detections with a little more alarm time. **5 days kept.**

Confirmation on seeds 9–12 and 42 (92 episodes), never used while choosing:

| model                              | detected | median lat. | all eps. | FP / yr | false alarm | switches / yr |
|------------------------------------|---------:|------------:|---------:|--------:|------------:|--------------:|
| v1                                 |  44/92   |   −3.0      |  60.0    |  0.24   |   9%        |  3.5          |
| v2, gbm / market                   |  89/92   |   −3.0      |  −3.0    |  0.86   |  11%        |  6.2          |
| v2, gbm / market + credit          |  87/92   |   −2.0      |  −2.0    |  0.77   |  11%        |  5.9          |
| v2, logistic / market              |  50/92   |   −3.5      |  35.0    |  0.31   |   9%        |  3.7          |
| v2, logistic / market + credit     |  53/92   |   −4.0      |  19.0    |  0.35   |   9%        |  3.8          |

On simulated data the false alarm share of v2 sits at the 10% target, mostly from v1's own part
(8–9%; the onset detector alone is at 2–3%). The simulator is known to overstate the models
(DETECTION.md), so these numbers only say the design works where the truth is known.

## Protocol (fixed before any real run)

**Step 1: pick the onset detector on a fresh real holdout.**
`python -m pfe_drai --provider fred holdout`, run once by Henry.

- Data: SPY (Tiingo, from 1993-01-29), VIX (FRED), LQD/IEF (Tiingo, from 2002) up to 2009-04-02,
  the day before the real out-of-sample period starts. Episodes dated by the same frozen rule
  (sha256 `6741b674…`, unchanged). None of these episodes was ever scored. Predictions start
  about 1999 (5 years of training, as in the main backtest).
- Candidates, in this order: logistic / market, logistic / market + credit, gbm / market,
  gbm / market + credit. Everything else is fixed as above.
- Selection: a candidate must meet the product's false-alarm targets on its own (≤ 1.5 false
  positives a year and ≤ 10% of calm days in false alarm). Among those, the lowest median latency
  over all episodes wins; ties go to fewer false positives, then to the earlier candidate.
- If no candidate qualifies, v2 stops there: v1 stays the default and the holdout table is
  published here.

**Step 2: one run on the 11 real episodes.** The selected candidate goes in `models.onset`,
`models.combined.stress_sources` becomes `[gbm, onset]` on this branch, and Henry runs
`python -m pfe_drai --provider fred backtest` once.

- **Decision**: v2 becomes the default (and the daily publication) if, on the real out-of-sample
  period, `combined` v2 meets both false-alarm targets: ≤ 1.5 false positives a year and ≤ 10% of
  calm days in false alarm. Otherwise `stress_sources` goes back to `[gbm]`.
- Whatever the decision, every number is published here: detected, median latency (detected and
  all episodes), false positives, false alarm share, switches, Brier, and the latency of each
  episode, next to v1 from the same run.
- No retuning after step 2. A v3 needs a new pre-registration with data that excludes these
  episodes, or a reason fixed before looking at them.

### What this does not claim

- The onset detector sees the drawdown and the volatility the episode rule is built on, so part
  of its speed comes from watching the same market the rule watches. That is the point of a
  stress signal (call the fall as it happens, every time, within days), but a latency near 0
  means "on the day the rule dates the start", not a forecast. Negative latencies (signal before
  the dated start) are the forecasting part and are shown episode by episode.
- 11 real episodes are few: a median moves a lot with one episode. The holdout adds about as many
  again from a different era (1999–2009), which is the reason to run it.

## Results

### Step 1: holdout (real data, run once by Henry, 2026-10-01)

`python -m pfe_drai --provider fred holdout`, predictions from 1999-02-25 to 2009-04-02.

| candidate                  | detected | median lat. | all eps. | FP / yr | false alarm | Brier |
|----------------------------|---------:|------------:|---------:|--------:|------------:|------:|
| logistic / market          |   3/6    |   6.0       |  41.5    |  0.40   |  3.1%       | 0.108 |
| logistic / market + credit |   3/6    |   6.0       |  41.5    |  0.40   |  2.8%       | 0.109 |
| **gbm / market** (selected)|   5/6    |  −2.0       |   1.0    |  0.50   |  2.4%       | 0.091 |
| gbm / market + credit      |   5/6    |  −2.0       |   1.0    |  0.50   |  1.5%       | 0.085 |

| start      | max drawdown | logistic / market | logistic / m + credit | gbm / market | gbm / m + credit |
|------------|-------------:|------------------:|----------------------:|-------------:|-----------------:|
| 1999-09-29 | −11.7%       | missed            | missed                | −2           | −2               |
| 2000-01-07 | −2.6%        | missed            | missed                | +5           | +5               |
| 2000-03-16 | −0.5%        | +23               | +23                   | −13          | −13              |
| 2000-05-10 | −10.2%       | −15               | −15                   | −15          | −15              |
| 2000-10-11 | −27.0%       | +6                | +6                    | +4           | +4               |
| 2008-01-08 | −19.0%       | missed            | missed                | missed       | missed           |

- Every candidate meets both false-alarm targets. The two gbm candidates tie on latency and on
  false positives, so the rule takes the earlier one: **gbm / market** (no credit input).
  gbm / market + credit has less alarm time, but alarm time is a limit in the rule, not a tie-break.
- Only 6 episodes, fewer than hoped: the frozen rule's re-arming means the market that never got
  back above −5% from late 2000 to 2003 counts as one long episode, not several.
- 2008-01 is missed by every candidate: a slow slide, not a sharp break.
- Both targets hold for the selected detector on its own: median latency 1 day over all
  episodes (−2 over detected ones), 0.50 false positives a year, 2.4% of calm days in false alarm.

Step 2 (one run on the 11 real episodes) uses `models.onset: {learner: gbm, inputs: market}`
and `models.combined.stress_sources: [gbm, onset]`, set in the commit after this table.

Fix before the first holdout run (2026-10-01): the first real holdout run crashed before
printing any result, because gradient boosting cannot use an input that is empty for a whole
training window (credit before LQD/IEF start in 2002). Such an input is now left out until it
has values. That is what "credit is missing before 2002" already meant above; nothing else changed.

### Step 2: the 11 real episodes (run once by Henry, 2026-10-01)

`python -m pfe_drai --provider fred backtest`, out-of-sample from 2009-04, same run for v1 and v2.

| model                          | detected | median lat. | all eps. | FP / yr | false alarm | switches / yr | Brier |
|--------------------------------|---------:|------------:|---------:|--------:|------------:|--------------:|------:|
| **v2** (jump + gbm + onset)    |  11/11   |  −3.0       |  −3.0    |  1.26   |  4.9%       |  5.6          | 0.101 |
| v1 (jump + gbm)                |   5/11   |  11.0       |  60.0    |  0.17   |  0.4%       |  3.4          | 0.097 |
| onset alone                    |  11/11   |  −3.0       |  −3.0    |  1.09   |  4.4%       |  5.7          | 0.108 |

| start      | max drawdown | v2   | v1     |
|------------|-------------:|-----:|-------:|
| 2010-05-20 | −15.7%       |  −8  | missed |
| 2011-08-04 | −18.6%       |  +1  | +11    |
| 2011-12-19 | −10.4%       | −17  | missed |
| 2015-08-24 | −11.9%       |  +4  | missed |
| 2016-01-13 | −13.0%       |  −2  | +18    |
| 2018-02-08 | −10.1%       |  +2  | missed |
| 2018-12-14 | −19.3%       | −18  | +6     |
| 2020-02-27 | −33.7%       |   0  | +5     |
| 2022-02-22 | −12.9%       | −20  | missed |
| 2022-05-05 | −24.5%       |  −5  | missed |
| 2025-03-13 | −18.8%       |  −3  | +18    |

**Decision: v2 is adopted.** It meets both pre-registered false-alarm targets (1.26 ≤ 1.5 false
positives a year, 4.9% ≤ 10% of calm days), so `combined` keeps `stress_sources: [gbm, onset]` and
becomes the daily publication. With it, the audit's latency target is met on real data for the
first time: median −3 business days (≤ 5), every episode caught within 4 days of its dated start.

What it costs, said as plainly as the gains:

- **False positives go from 0.17 to 1.26 a year**, close to the 1.5 limit: about 20 false alarms
  over 16 years. They are short (4.9% of calm days in all), but a committee will see roughly one a year.
- **Regime switches go from 3.4 to 5.6 a year.**
- **Large negative latencies mean the signal was already on, not a forecast.** −17 to −20 days
  (2011-12, 2018-12, 2022-02) usually mean an alarm from an earlier dip was still running when the
  episode started. The detection window counts that as caught, as it did for v1. The latency at
  the start of each new fall is what the per-episode numbers above show; they are not all foresight.
- 11 episodes are few, and the holdout had 6. Both runs point the same way, but this is evidence,
  not proof. The daily track record is the real test from here on.

Nothing was retuned after this run.
