# Sahm rule and high-yield credit: simulated tests and pre-registration

**Status, 2026-10-03:** high-yield credit is **NOT ADOPTED**. It failed on simulated data, so it gets no real run.
The Sahm rule is **pre-registered, step 1 not run yet.** The published model stays **v2.2** and its
settings fingerprint does not change. This page is committed and pushed before Henry runs anything. Results go
under "Results", and nothing above that heading changes afterwards.

## Why these two

They follow [MODEL_UPGRADES.md](MODEL_UPGRADES.md). Seven upgrades built from the series the model already reads
did not beat v2.2. These two bring in data the model does not read yet, and both have long, free, publishable
histories that reach a real period never used to score crises (Henry checked them on 2026-10-03):

| series | source | first value |
|---|---|---|
| Vanguard High-Yield Corporate fund (`VWEHX`) | Tiingo | 1980-01-02 |
| Vanguard Intermediate-Term Treasury fund (`VFITX`) | Tiingo | 1991-10-28 |
| Real-time Sahm rule indicator (`SAHMREALTIME`) | FRED | 1959-12 |

The ICE BofA spreads on FRED keep only 3 years, and Moody's BAA cannot be redistributed (re-audit). That is why
the high-yield proxy is a fund pair, read like LQD/IEF today. The CBOE VIX term structure (VIX3M from Dec 2007)
has almost no history before the out-of-sample period, so it is left for a live shadow run.

## High-yield credit in the crisis detector: not adopted (simulated data)

Candidate: the onset detector also reads high-yield bonds against Treasuries over 5 and 21 days (`onset_hy`),
next to the investment-grade pair that was a holdout candidate in [DETECTION_V2.md](DETECTION_V2.md) (`onset_ig`, the `market_credit` set). In the
simulator these are the HYG / LQD / IEF series. Run: `docs/experiments/model_upgrades.py`, 13 seeds.

| candidate (13 seeds, 229 episodes) | detected | lat. all | FP / yr | false alarm | Brier | ECE | switches / yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| **v2.2 (onset on market inputs)** | **221** | −3.4 | **0.643** | 10.3% | 0.180 | 0.067 | 3.2 |
| + investment-grade credit | 219 | −3.1 | 0.650 | 10.4% | 0.181 | 0.065 | 3.2 |
| + high-yield credit | 221 | −3.2 | 0.674 | 10.4% | 0.181 | 0.065 | 3.2 |

High-yield credit catches the same crises, a little later, with more false positives (worse in 6 seeds, better in 5).
**Not adopted, and no real run.** In the simulator the high-yield spread is a slow process that follows the
regime, so it says little the equity and VIX inputs do not already say. Real spreads can lead equities, which this
simulator cannot show. A later test would need a reason the simulator can check.

## Sahm rule in the growth score

### The idea

The **Sahm rule** (Claudia Sahm, 2019) compares the 3-month average unemployment rate with its lowest 3-month
average over the past 12 months. A rise of 0.5 points has started every US recession since 1970. The growth
score reads unemployment only through jobless claims over a quarter. The Sahm gap is a slower, cleaner reading of
the labour market and fits a regime that should last months.

`unemployment_gap` (`features/build.py:sahm_gap`) = −(3-month average − its 12-month low), on business days (63
and 252), past data only. 0 means unemployment is at its low; −0.5 is the Sahm signal. On real data the input is
FRED `UNRATE` as **first releases** (ALFRED), dated on the day of the employment report, as for claims and
production. `SAHMREALTIME` is FRED's own version, used only to confirm the series exists.

### Simulated data

The simulator now has an unemployment rate (`data/synthetic.py`) that follows its regime over months (4.2% in
expansion, 5.8% in slowdown). It is drawn after every other series, so those are unchanged, and 352 tests pass.
Candidates, 13 seeds, everything else as v2.2:

| candidate (13 seeds) | growth match | Slowdown shown | Slowdown found | accuracy | detected | FP / yr | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **v2.2** | 0.707 | 0.798 | 74.9% | 0.727 | 221 | 0.643 | 0.180 | 0.067 |
| v2.2 + Sahm gap | 0.716 | 0.802 | 76.5% | 0.725 | 221 | 0.654 | 0.180 | 0.066 |
| Sahm gap instead of claims | 0.668 | 0.792 | 77.3% | 0.709 | 221 | 0.585 | 0.180 | 0.062 |

- **Sahm gap instead of claims** loses growth match in 11 seeds of 13. Not a candidate.
- **v2.2 + Sahm gap** is a little better on growth match (+0.009, better in 7 seeds of 13) and Slowdown found (better
  in 9 seeds), with detection unchanged. That is too small to be evidence. The simulator's unemployment follows the
  same hidden regime as its claims, so on this data the Sahm gap can add little by construction. What it is known
  for (calling real recessions early) only real data can show, hence a real test, under a rule that asks for a gain
  larger than these.

### Protocol (fixed before any real run)

**Step 1: growth score holdout.** `python -m pfe_drai --provider fred sahm`, run once by Henry.

- Same window and reference as the v2.2 growth holdout ([SLOWDOWN.md](SLOWDOWN.md)): US data to 2009-04-02, scored
  from 1999-01-04 against `CFNAIMA3 < 0`. No model is fitted, so no crisis is involved.
- Two rows: **v2.2 as published** (four inputs, robust scaling, 21-day average, threshold 0) and **v2.2 + Sahm gap**
  (the same with the Sahm gap as a fifth input). Settings: the `sahm:` block of `config/settings.yaml`, outside the
  model's fingerprint.
- **Passes** only if the Sahm candidate's balanced accuracy is **at least 0.02 above v2.2's**, and its Slowdown
  changes at most 2 times a year. That is the margin the displayed Overheating needed ([INFLATION.md](INFLATION.md)).
  On simulated data this rule passes in 3 seeds of 13 (mean gain +0.006), so it asks for more than noise.
- If it fails, the test stops: v2.2 stays and the table is published here.

**Step 2 (only if step 1 passes): one run on the out-of-sample period.** The Sahm gap is wired into the model
(features, gbm, explanations) on a new branch. Then one run of `slowdown` compares v2.2 with v2.2 + Sahm on the same
days, under the nine conditions of [SLOWDOWN.md](SLOWDOWN.md), with one change fixed now: the displayed Slowdown
must beat v2.2's by at least **0.02**, not merely be higher (0.012 was not evidence there). If any condition fails,
v2.2 stays. Nothing is retuned after either run.

### What this does not claim

- **The holdout has been used once before for growth:** the v2.2 growth score scored 0.757 on it (SLOWDOWN.md). The
  v2.2 row is that same score, so step 1 compares against a known number. The Sahm gap itself was never computed on
  it, but this is weaker than a fresh holdout. The 0.02 margin is partly there for that reason.
- **The out-of-sample period is not blind for growth** either (v2.2 was run on it). A pass in step 2 is evidence, not proof.
- 1999–2009 holds two recessions (2001, 2008), so step 1 rests on few turning points.

## Results

### Step 1 (real data): not run yet
