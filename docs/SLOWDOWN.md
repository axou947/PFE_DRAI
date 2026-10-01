# A real Slowdown regime: pre-registration

**Status: pre-registered on 2026-10-01. Step 1 done; step 2 not yet run on the variant step 1 selected (see Results).** This page fixes what changes,
how it was chosen (simulated data only), the holdout that picks the growth inputs and the rule
that decides on real data. It is committed and pushed before Henry runs anything; the real results
are added under "Results" as they come out, and nothing above that heading changes afterwards.

If adopted, the model becomes **v2.2** (`models.version`). Until then the published model is
**v2.1** (detection v2, [DETECTION_V2.md](DETECTION_V2.md), with the calibrated probability,
[CALIBRATION.md](CALIBRATION.md)).

## The problem

The rule ([REGIMES.md](REGIMES.md)) calls a day **Slowdown** when the growth score is below −0.25
and neither stress nor overheating applies. On real data (REGIMES.md, results of 2026-10-01):

- the rule puts 9.5% of days in Slowdown, and the jump model never finds them as a group: until
  2023-04 the state named Slowdown has only 13–26% Slowdown days, and from 2023-10 no state is
  named Slowdown at all. So the app has not shown Slowdown since 2023;
- nothing checks that the rule's Slowdown matches a slowdown of the economy.

## Diagnosis (simulated data and the code, no real data)

The growth score is the average of four expanding z-scores: 6-month equity momentum, the 10y−2y
curve slope, industrial production over a year and jobless claims over 3 months (sign flipped).

1. **The rule's Slowdown flickers.** On simulated data (seed 42), the rule makes 46 Slowdown spells
   of median length 6 days, where the simulator has 9 slowdowns of median length 155 days. The
   rule finds 48% of the true slowdown days and calls 36% of them Expansion. Across seeds 1–8, the
   growth score crosses −0.25 about 3 times a year, with a median spell of 4 days. A state that
   lasts a week cannot be a regime of the economy, and a jump model, which pays to switch, will
   not make a state of it.
2. **The curve slope reads the cycle the wrong way round.** A steep curve comes after the central
   bank cuts, during and just after a slump; an inverted curve comes late in a boom. It is a leading
   indicator of recessions a year or more ahead, not a measure of current growth. On simulated data
   its z-score averages +0.48 in stress and −1.18 in overheating, against −0.38 in slowdown.
3. **One extreme stretch squeezes every later reading.** An expanding standard deviation that
   contains 2008–09 (industrial production −15% over a year) and 2020 (claims up about 30 times in
   a few weeks) is inflated for every later day: after 2020 a normal move in claims reads close to
   0. On simulated data with a Covid-sized shock added in 2020, the claims z-score's spread after
   2021 falls from 0.98 to 0.37, and the growth score's match with the true slowdowns falls from
   0.663 to 0.598 (balanced accuracy, 12 seeds). This would explain why no Slowdown state appears
   after 2023 on real data. It is a property of the arithmetic, known before any real growth data
   was looked at.
4. **The threshold −0.25 was set by hand.** Nothing ties it to the economy.

Point-in-time inputs are not the problem: production and claims are first releases from ALFRED,
dated on their publication day (PR #4), and stay so.

## What changes (v2.2)

`features.growth` and `regimes.rule.growth_threshold` in `config/settings.yaml`:

| | until v2.1 | v2.2 |
|---|---|---|
| growth inputs | equity momentum, curve slope, production, claims | equity momentum, production, claims |
| scaling of the growth inputs | expanding mean and standard deviation | expanding median and interquartile range |
| growth score | that day's average | average of the last 21 business days |
| Slowdown threshold | −0.25 (by hand) | 0: growth below its own historical median |

- **Robust scaling** (`features/build.py:robust_zscore`): (x − median) / (IQR / 1.349), on the
  past only, as before. On normal data it reads like a z-score; one extreme stretch barely moves
  it (tested). Only the growth inputs change scale; stress and inflation are untouched.
- **A month's average** turns a growth score made of monthly and weekly releases plus one daily
  market input into a monthly reading. No day is lost (the first days average what exists).
- **Threshold 0** is "growth below its usual level", the same definition the reference below uses
  (0 = trend). It is not tuned.
- **The curve slope stays a model input.** gbm and the app's indicator chart still see it; it is no
  longer averaged into the growth score (the chart files it under "models only").

What does not change: the stress and inflation scores, the rule's order (stress first, then
overheating, then slowdown), the onset detector, the alarm (it reads the same detector score), the
calibration method and the frozen episode rule. The stress label is the same day for day, so the
part of gbm's target that matters for detection does not change; gbm and the jump model are
refitted on the new growth score and so can move P(stress) a little. That is what the detection
and calibration conditions below watch.

## An outside reference for Slowdown

On simulated data the truth is known. On real data there was none, so the rule could never be
wrong. The reference added here is the **Chicago Fed National Activity Index, 3-month average**
(FRED `CFNAIMA3`) **below 0**: a weighted average of 85 monthly activity indicators (production,
employment, consumption, sales), built so that 0 means growth at its historical trend. It is used
as published today (revised): it is the answer to check against, never a model input. Each month's
reading applies to the days of that month; months not yet published are left out.

`validation/slowdown.py` scores, on the out-of-sample days:

- **growth match**: balanced accuracy of "growth score below the threshold" against below-trend
  growth (average of the share found on below-trend days and the share right on the others, so
  the base rate does not decide);
- **persistence**: the rule's Slowdown spells a year and their median length;
- **a Slowdown state**: the share of walk-forward refits where one of the jump model's states is
  named Slowdown and at least half of its training days are Slowdown by the rule;
- **displayed Slowdown**: balanced accuracy of "the app shows Slowdown" against the reference's
  slowdown days: below-trend growth outside any stress episode (simulated: the hidden slowdown
  regime), with the share of those days found and the share of shown days that are right.

## How it was chosen (simulated data only)

Development on seeds 1–8 (137 stress episodes), every number out of sample, combined model as
published (`docs/experiments/slowdown.py`). Each row adds one change to the row above it, except
the macro rows, which replace the three inputs with production and claims only.

| candidate (seeds 1–8) | rule Slowdown | spells / yr | median spell | growth match | Slowdown state | displayed match | detected | lat. all | FP / yr | false alarm | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| until v2.1 | 11.1% | 2.1 | 4 | 0.689 | 27% | 0.769 | 130/137 | −5.0 | 0.52 | 9.5% | 0.179 | 0.065 |
| threshold 0 | 20.4% | 2.7 | 4 | 0.719 | 94% | 0.789 | 131/137 | −5.0 | 0.52 | 9.5% | 0.178 | 0.065 |
| + 21-day average | 21.6% | 1.2 | 25 | 0.702 | 96% | 0.788 | 131/137 | −4.3 | 0.55 | 9.5% | 0.179 | 0.065 |
| + no curve slope | 23.9% | 1.2 | 28 | 0.750 | 95% | 0.780 | 129/137 | −4.4 | 0.52 | 9.6% | 0.179 | 0.061 |
| **+ robust scaling (v2.2)** | 30.0% | 1.5 | 32 | 0.734 | 96% | 0.768 | 129/137 | −3.5 | 0.52 | 9.6% | 0.179 | 0.069 |
| macro only, standard | 25.7% | 1.4 | 29 | 0.741 | 97% | 0.799 | 130/137 | −3.9 | 0.52 | 9.3% | 0.179 | 0.064 |
| macro only, robust | 31.8% | 1.8 | 32 | 0.730 | 95% | 0.783 | 130/137 | −4.7 | 0.55 | 9.8% | 0.180 | 0.064 |

- **The threshold is what makes Slowdown a state of the model:** with −0.25, a state named Slowdown
  that agrees with the rule exists in 27% of refits (0–12% in five of the eight seeds, the real-data
  picture); with 0, in 94–97%.
- **The month's average makes it a regime:** spells fall from 2.7 to 1.2 a year and last a month
  instead of 4 days, for 1.7 points of growth match.
- **Without the curve slope** the growth match rises by 4.8 points.
- **Robust scaling costs 1.6 points here**, on simulated data that has no extreme stretch. With a
  Covid-sized shock added (diagnosis, point 3), it is the other way: 0.639 against 0.598 after
  2021. Real data has two such stretches, so robust scaling is chosen for that reason, fixed now.
- Detection and calibration stay within noise: one episode of 137 fewer (129 against 130), false
  alarms unchanged, Brier unchanged, ECE +0.004.

Confirmation on seeds 9–12 and 42 (92 episodes), never used while choosing:

| candidate (seeds 9–12, 42) | rule Slowdown | spells / yr | median spell | growth match | Slowdown state | displayed match | detected | lat. all | FP / yr | false alarm | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| until v2.1 | 12.6% | 2.0 | 3 | 0.672 | 61% | 0.844 | 89/92 | −2.4 | 0.86 | 11.1% | 0.184 | 0.065 |
| no curve slope, standard | 24.3% | 1.4 | 24 | 0.759 | 100% | 0.821 | 89/92 | −1.7 | 0.83 | 11.0% | 0.182 | 0.061 |
| **v2.2** | 31.1% | 1.7 | 27 | 0.727 | 100% | 0.815 | 89/92 | −2.2 | 0.81 | 11.2% | 0.182 | 0.060 |
| macro only, robust | 35.6% | 2.0 | 25 | 0.747 | 99% | 0.848 | 89/92 | −2.0 | 0.85 | 11.5% | 0.184 | 0.062 |

Across all 13 seeds, v2.2 against v2.1: a Slowdown state in more refits in 13 of 13, a better
growth match in 11 of 13, one stress episode fewer (218 against 219 of 229), Brier and ECE
within ±0.005.

**What does not improve on simulated data: the displayed Slowdown.** Its match with the hidden
slowdowns is better in 5 of 8 development seeds and in none of the 5 confirmation seeds (means
0.768 against 0.769, and 0.815 against 0.844). The simulator's old Slowdown states, though mixed
by the rule's standard, already sat on the true slowdowns, because the old rule missed half of
them. On real data the old model has shown no Slowdown since 2023, so this is where v2.2 has the
most to prove. It is kept as a condition below, and it is the one most likely to fail.

## Protocol (fixed before any real run)

### Step 1: pick the growth inputs on a real holdout

`python -m pfe_drai --provider fred slowdown --holdout`, run once by Henry.

- Data: US data before the real out-of-sample period, the same window as the onset holdout
  (`validation.holdout`): SPY (Tiingo, from 1993-01-29), the 10- and 2-year yields, production and
  claims (ALFRED first releases where ALFRED has them), to 2009-04-02. Scored from 1999-01-04
  (`validation.slowdown.holdout.evaluate_from`) against `CFNAIMA3 < 0`. No model is fitted: only
  the growth score is computed, so nothing about crises is involved and none of the 11 real
  episodes is seen.
- Candidates, in this order, all with robust scaling, the 21-day average and threshold 0:
  1. three inputs (no curve slope), the simulated-data choice;
  2. four inputs (with the curve slope);
  3. macro only (production and claims).
  The growth score until v2.1 is printed for comparison; it is not a candidate.
- Selection: a candidate qualifies if its "growth below 0" changes at most 2 times a year
  (`max_spells_per_year`). Among those, the highest balanced accuracy wins; a candidate within
  1 point (`tie: 0.01`) of the best counts as tied, and ties go to the earlier candidate.
- If no candidate qualifies, v2.2 stops there: the growth score stays as in v2.1 and the table is
  published here. If the winner is not candidate 1, its inputs go in `features.growth.inputs` in
  the commit after the table, before step 2.

### Step 2: one run on the real out-of-sample period

`python -m pfe_drai --provider fred slowdown`, run once by Henry. The command runs v2.1's growth
score (`validation.slowdown.before`) and v2.2's side by side on the same data and days (out-of-
sample from 2009-04 as in every real run), prints every number, then the decision.

**Decision: v2.2 is adopted (and becomes the daily publication) only if all of these hold.**

Slowdown is real:

1. the growth score matches below-trend growth better than v2.1's (balanced accuracy against
   `CFNAIMA3 < 0`, higher);
2. a state of the jump model is named Slowdown, with at least half of its training days Slowdown by
   the rule, in at least half of the walk-forward refits;
3. the displayed Slowdown matches the reference's slowdown days better than v2.1's (balanced
   accuracy, higher).

Detection stays within its targets (`validation.targets`):

4. no stress episode lost (detected at least as many as v2.1 in the same run: 11 of 11 so far);
5. median latency at most 5 days;
6. at most 1.5 false positives a year;
7. at most 10% of calm days in false alarm.

Calibration does not get worse (`validation.slowdown.calibration_tolerance`):

8. Brier not higher than v2.1's in the same run (3 decimals);
9. ECE not higher than v2.1's by more than 0.005. ECE groups days in 10 bins and moves with a
   single day: one more day of data took the published v2.1 ECE from 0.042 to 0.043 (track-record
   preview, 2026-10-01). Brier does not move like that and gets no tolerance.

If any condition fails, `features.growth` and the threshold go back to v2.1's values,
`models.version` stays `v2.1`, and this page says which condition failed. Whatever the decision,
every number the command prints is published here. Nothing is retuned after the run: a v2.3 would
need a new pre-registration.

### What the track record shows

Each configuration has its own backtest record, written once and never rewritten
([TRACK_RECORD.md](TRACK_RECORD.md)). If v2.2 is adopted, the next daily run writes a new
backtest record for it, and the v2.1 record stays. From this change on, every published day also
carries `model_version` and `config_sha256`, so the page lists every model version with its
backtest and says on which day the published model changed. Days already published keep what was
published then.

## What this does not claim

- **The reference is not the truth either.** CFNAI is one measure of activity, revised after the
  fact, and its trend is the 1967–today average, higher than the growth of the 2010s; it will call
  many of those years below trend. It is used because it is outside the model, published and
  built so that 0 means trend.
- **"Below its own median" depends on the history behind it.** The growth score is scaled on the
  past only, so its median comes from the years the data starts with: a boom at the start puts
  more of the later days below the median. On simulated data scored over 1999–2009 with history
  from 1993, the v2.1 score matched the truth better than every candidate (0.764 against 0.714 for
  v2.2's inputs, 12 seeds); over 2005–2026 it was the other way (0.689 against 0.734). The real
  holdout can show the same: its table is published either way, and the decision is taken on the
  out-of-sample period, as for every earlier change.
- **Slowdown will be shown more often.** The rule puts about 30% of simulated days in Slowdown
  against about 11%. On real data the share will be known after step 2.
- **The curve slope is not proved useless.** It is a good recession signal a year ahead; it is
  only no longer counted as current growth.

## Results

### Step 1: growth holdout (real data, run once by Henry, 2026-10-01)

`python -m pfe_drai --provider fred slowdown --holdout`, 1999-01-04 to 2009-04-02 (2,578 days),
reference `CFNAIMA3 < 0` (below-trend growth on 50% of days).

| # | candidate | balanced accuracy | days below | spells / yr | median spell |
|---|---|---:|---:|---:|---:|
| – | until v2.1 (comparison only) | 0.776 | 52% | 6.83 | 5 |
| 1 | three inputs (no curve slope) | 0.745 | 72% | 1.37 | 37 |
| 2 | four inputs (with curve slope) | **0.757** | 71% | 1.76 | 36 |
| 3 | macro only (production, claims) | 0.743 | 69% | 1.46 | 33 |

All three candidates qualify (at most 2 spells a year). Candidate 2 has the highest balanced
accuracy and candidates 1 and 3 are within 0.014 of it, so **the rule selects candidate 2, four
inputs, with the curve slope**. The simulated data had picked the opposite, which is the reason for
holding the real holdout. v2.1's score is the most accurate here but flips 6.8 times a year with a
5-day median spell, which fails the persistence limit by construction.

### An unplanned run of step 2, on the wrong variant (2026-10-01)

**Say it plainly:** the protocol said that if the winner is not candidate 1, its inputs go in the
settings *before* step 2. Step 2 was run straight after step 1, on the **three-input** variant,
which step 1 did not select. This is a departure from the pre-registered protocol, made while the
instructions asked to paste step 1 first. It is published as it came out, as an **informative run
that does not decide anything**:

| | v2.1 | three inputs (not selected) |
|---|---:|---:|
| rule: days in Slowdown | 9.0% | 25.9% |
| rule: Slowdown spells / yr (median spell, days) | 3.32 (3) | 2.06 (30) |
| growth match with the reference (balanced accuracy) | 0.551 | 0.606 |
| refits with a state named Slowdown, agreement ≥ 50% | 0% | 83% |
| days shown as Slowdown | 6.7% | 15.1% |
| displayed Slowdown vs reference (balanced accuracy) | 0.480 | 0.502 |
| reference slowdown days found / shown days that are right | 4.9% / 39.2% | 15.4% / 54.8% |
| reference: days of below-trend growth | 61.2% | 61.2% |
| episodes detected, median latency | 11/11, −3 | 11/11, −3 |
| false positives / yr, calm days in false alarm | 1.26, 4.9% | 1.20, 5.6% |
| regime switches / yr | 2.2 | 3.7 |
| Brier, ECE | 0.091, 0.042 | **0.092**, 0.042 |

Every latency, episode by episode, is the same as v2.1's. Eight of the nine conditions hold. The
ninth, **Brier not higher, fails by 0.001** (0.091 → 0.092). Under the rule this variant would not be
adopted, but it is not the variant the rule selected.

What the run shows, whichever variant is decided on:

- **A Slowdown state now exists** (83% of refits against 0%), and it is a regime (30-day median
  spell against 3). The states with fewer than half Slowdown days are the 2022-10 to 2025-04 refits,
  with 43 to 46%, which is the period the problem was seen in.
- **What the app displays is still close to chance.** Balanced accuracy against the reference goes
  from 0.480 to 0.502 (0.5 is chance), and it finds 15% of the reference's slowdown days. Slowdown is
  shown on 15% of days while CFNAI is below trend on 61% of them (as announced in "What this does not
  claim", the index's long-run trend sits above the growth of the 2010s). The honest reading is that
  the growth score is now a better measure of growth, but what is shown as Slowdown is not yet a
  good match for the reference.
- Detection is untouched; regime switches rise from 2.2 to 3.7 a year.

### Step 2 on the selected variant: next

The protocol is followed from here: the selected four-input variant is set in
`validation.slowdown.tested` (`growth.inputs` = equity momentum, curve slope, production, claims;
robust scaling; 21-day average; threshold 0) in the commit that adds this section, and
`python -m pfe_drai --provider fred slowdown --tested` is run **once** by Henry. Its decision
applies with the nine conditions above, unchanged. **That run is no longer blind:** the three-input
run above has already shown the real out-of-sample period for a variant that differs only by the
curve slope, so a pass on the four-input variant is weaker evidence than a pass on a first look.
Both runs are published either way, and a failure ends v2.2: `features.growth` and the threshold
stay as in v2.1 (this is the state of the branch now, `models.version` is `v2.1`), and any further
change needs a v2.3 with its own pre-registration.
