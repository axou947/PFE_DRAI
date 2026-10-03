# Inflation score, one vote per source: pre-registration and result

**Status: NOT ADOPTED on 2026-10-03.** It failed on simulated data, before any real run. The published
model stays **v2.2** ([SLOWDOWN.md](SLOWDOWN.md)) and its settings fingerprint does not change. The real
out-of-sample period was not looked at, so the inflation dimension stays unseen for a later change.

## The question (Henry, 2026-10-03)

"Does every input have the same weight? A higher CPI should have more impact on the regime."

How the model weighs its inputs today:

- **Dimension scores: equal weights.** Each score is the plain average of its inputs' expanding z-scores
  (`features/build.py`, `dimension_scores`). The inflation score is CPI over a year, the 10-year
  breakeven level, the breakeven change over a quarter and the 2-year rate change over 6 months, a quarter
  each.
- **Between dimensions: an order, not weights.** The rule checks stress first, then inflation, then growth
  ([REGIMES.md](REGIMES.md)). The jump and k-means models measure plain distances on the three scores.
- **The stress alarm is weighted by data.** gbm reads the 12 inputs, the 3 scores and their 5-day
  changes, and learns its own weights; the onset detector does the same on fast market inputs.
- **Size already counts.** A z-score of +4 (the clip) on CPI alone adds 1.0 to the inflation score,
  above the Overheating threshold of 0.8.

The one weighting that looked wrong: the breakeven's level and its change are read off the same series,
so market expectations carry **half** of the inflation score and CPI a quarter.

## What was tested (v2.3 candidate)

One vote per **source** instead of one per input (`features.inflation.weighting: sources`): the inputs
of one source are averaged first, then the sources.

| input | until v2.2 | v2.3 candidate |
|---|---:|---:|
| CPI (1 year) | 1/4 | 1/3 |
| breakeven level | 1/4 | 1/6 |
| breakeven change (3 months) | 1/4 | 1/6 |
| 2-year rate change (6 months) | 1/4 | 1/3 |

Regions without a breakeven (euro area, Japan, emerging markets) get the same score either way. Stress
and growth do not change.

## The check (fixed before any run)

`python -m pfe_drai --provider fred overheating` runs both weightings on the same data and days
(`validation/overheating.py`). The reference is outside the model: on simulated data, the simulator's
hidden Overheating regime; on real data, **core PCE inflation over 12 months** (FRED `PCEPILFE`, the
Fed's preferred measure, not a model input) **above 2.5%**, outside stress episodes for the displayed
regime.

Adoption needs all eight (`overheating` in `config/settings.yaml`):

1. the inflation score above its threshold matches the reference better (balanced accuracy);
2. the displayed Overheating matches it better **by at least 0.02**. Slowdown's +0.012 was not
   evidence (SLOWDOWN.md), and condition 1 is close to mechanical on real data, because CPI and PCE
   move together;
3. no stress episode lost; 4. median latency ≤ 5 days; 5. ≤ 1.5 false positives a year; 6. ≤ 10% of
   calm days in false alarm;
7. Brier not higher; 8. ECE not higher by more than 0.005.

The order was: simulated data first, and a real run only if the simulated data showed a gain.

## Result on simulated data (2026-10-03)

`docs/experiments/inflation.py`, combined model as published, seeds 1–12 and 42 (229 stress episodes),
every number out of sample.

| | seeds 1–8, before | seeds 1–8, after | seeds 9–12 + 42, before | seeds 9–12 + 42, after |
|---|---:|---:|---:|---:|
| inflation score vs truth (bal. acc.) | 0.847 | 0.830 | 0.815 | 0.795 |
| displayed Overheating vs truth (bal. acc.) | 0.818 | 0.798 | 0.781 | 0.768 |
| truth Overheating days found / shown days right | 68.7% / 77.9% | 66.2% / 72.5% | 62.7% / 69.7% | 60.9% / 66.7% |
| stress episodes detected | 130/136 | 129/136 | 91/93 | 91/93 |
| false positives / yr, calm days in false alarm | 0.58, 9.7% | 0.55, 9.4% | 0.75, 11.3% | 0.72, 11.1% |
| Brier, ECE | 0.178, 0.071 | 0.178, 0.067 | 0.184, 0.060 | 0.182, 0.060 |
| regime switches / yr | 3.3 | 3.5 | 3.1 | 3.3 |

The inflation match is better with one vote per source in **2 of 13** seeds, and the displayed Overheating
match is better in **1 of 13**: on average −0.018 and −0.018. Detection and calibration stay within noise
(one episode fewer of 229). Both Overheating conditions fail, so the real run was not made.

**Why it is worse.** Doubling the breakeven was not just double counting: it is the timely input. CPI
over a year is a 12-month average, published a month late; the breakeven moves the day expectations move,
and its quarterly change catches turns early. Giving CPI more weight makes the score later, not better.
In the simulator the breakeven tracks current inflation by construction, so this result describes the
simulator first. The same structure holds for real data (a lagging yearly CPI and a daily market price),
which is why a real run was not worth spending the out-of-sample look on.

## What stays

- The model, the settings that make its fingerprint, and the daily publication: unchanged.
- The switch (`features.inflation`, default one vote per input), the explanation that follows the
  weights (`explain.py`), the `overheating` command and its reference. A later Overheating change can
  use them, with its own pre-registration.
- Better ideas, if Overheating is revisited: core rather than headline CPI, or CPI over 3 or 6 months
  (more timely), each tested first on simulated data with this check.
