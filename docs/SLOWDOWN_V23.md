# Displayed Slowdown (v2.3): diagnosis and pre-registration

**Status, 2026-10-03: NOT ADOPTED.** The one real run selected no candidate on the first part (results at the
bottom), so the published model stays **v2.2** and its settings fingerprint does not change. This page was committed and
pushed before Henry ran anything. The run's output is under "Results", and nothing above that heading changed afterwards
except this status line.

## The problem

v2.2 made Slowdown a real regime of the rule, but what the app **displays** as Slowdown is no better than a
coin flip against the outside reference (Chicago Fed activity index `CFNAIMA3` below 0, outside stress
episodes; real data, out-of-sample 2009-04 to 2026-09, SLOWDOWN.md):

| v2.2, real data | |
|---|---:|
| growth score below 0 vs below-trend growth (balanced accuracy) | 0.620 |
| displayed Slowdown vs the reference's slowdown days (balanced accuracy) | **0.492** |
| reference slowdown days found / shown Slowdown days that are right | 11.9% / 51.0% |
| days shown as Slowdown / days the rule calls Slowdown / reference below trend | 12.5% / 43.3% / 61.2% |

## Diagnosis (simulated data and published numbers only)

Where is the match lost: in the growth score, in the rule, or in the jump model that names what is displayed?

**1. Not in the growth score.** On real data the growth score alone matches below-trend growth at 0.620; what is
displayed matches at 0.492. The loss happens after the growth score, between the score and the screen.

**2. On simulated data the jump model is not the problem.** `docs/experiments/slowdown_v23.py` runs v2.2 once
per seed and scores, against the hidden slowdown regime, the growth score alone, the rule's own label, and the
displayed regime (out-of-sample days, means):

| simulated, displayed Slowdown (bal. acc.) | growth below 0 | rule label | **v2.2 displayed** |
|---|---:|---:|---:|
| standard world, seeds 1–8 | 0.702 | 0.783 | **0.780** |
| standard world, seeds 9–12, 42 | 0.715 | 0.800 | **0.827** |
| quiet world, seeds 1–8 | 0.661 | 0.754 | **0.739** |
| quiet world, seeds 9–12, 42 | 0.661 | 0.762 | **0.728** |

On simulated data what is displayed is about **0.1 better** than the growth score alone; on real data it is
**0.13 worse**. The simulator does not reproduce the real failure. The "quiet" world was built for this
diagnosis: the same regime paths, but a slowdown's markets look like an expansion's (equity volatility 14%
instead of 21%, high-yield spread 4% instead of 5.5%), so only production and claims show it. That is the
shape of most below-trend months since 2009. Even there, the jump model still finds the slowdowns (0.73).

**3. So the loss is in how the jump model's states line up with real slowdowns.** In the simulator, a slowdown
moves production from +3% to −1% a year and claims from 230,000 to 300,000 a week: a large, clean shift that
forms a cluster of its own on the three dimensions, which the jump model finds. Real below-trend months are
mostly mild (CFNAI a little under 0), so they do not form a cluster; the jump model's four states follow the
stress and inflation dimensions, where real data varies most, and the state that gets the name Slowdown
(nearest to the rule's Slowdown centre, REGIMES.md) is only partly made of slow-growth days (43–49% agreement
in the refits listed in SLOWDOWN.md). This is hypothesis (b) of SLOWDOWN.md. It is a reading of the numbers
above, not a test: the simulator cannot test it, which is why the decision below is taken on real data.

**4. What the simulator can say about the fix.** If the calm regime displayed came from the transparent rule
instead of the jump model's states, simulated data says it would be about as good, not better: −0.03 in the
standard world (better in 3 of 13 seeds), +0.01 in the quiet one (better in 9 of 13). On simulated data that
change is not worth making. On real data it could be, because there the jump model's naming is what fails.
Only real data can decide, so the protocol below is built to make that test hard to pass by luck.

## What changes (display only)

`models.combined.calm` (new setting, absent = v2.2). The combined model's P(stress) is the calibrated detector
score; what is left, 1 − P(stress), is shared between Expansion, Overheating and Slowdown
(`pfe_drai/display.py`). Candidates, listed before any real run, in this order:

| candidate | the calm share goes to | stress shown when |
|---|---|---|
| `jump` (v2.2) | the calm regimes in the jump model's proportions | P(stress) is the largest bar |
| 1. `rule` | all of it to the rule's calm regime of the day: overheating if inflation is above 0.8, else slowdown if growth is below 0, else expansion; a new calm regime counts once it has held 3 days (`validation.confirm_days`, as for the regime alerts) | P(stress) above 50% |
| 2. `rule_named` | the jump model's calm shares, but the largest goes to the rule's calm regime (same 3-day hold) | same days as v2.2 |
| 3. `gbm` | the calm regimes in gbm's proportions (gbm learns the rule's regimes one week ahead) | P(stress) is the largest bar |

**P(stress) is never touched,** so the stress alarm, every episode's latency, false alarms, Brier and ECE are
identical day for day; the run checks it. Only the label and the calm bars change. With `rule`, the Slowdown
bar reads "not stress, and the rule calls the calm side Slowdown": a 90% bar is 10% stress, not 90% certainty
about growth.

Not candidates, and why: a lower jump penalty or another state count changes the jump model's P(stress), which
feeds the alarm; a threshold on a rolling window changes the rule, so gbm's training labels and P(stress)
change too. Both would put detection back at risk for a display problem.

Simulated data, every display computed from the same out-of-sample probabilities (means):

| simulated | v2.2 | rule | rule_named | gbm |
|---|---:|---:|---:|---:|
| standard 1–8: bal. acc. / switches a year / median Slowdown spell | 0.780 / 3.3 / 39 | 0.750 / 3.8 / 33 | 0.746 / 4.2 / 28 | 0.750 / 7.5 / 13 |
| standard 9–12, 42 | 0.827 / 3.1 / 34 | 0.800 / 3.7 / 34 | 0.790 / 4.2 / 28 | 0.792 / 7.3 / 11 |
| quiet 1–8 | 0.739 / 3.3 / 52 | 0.739 / 3.9 / 38 | 0.736 / 4.3 / 32 | 0.721 / 7.5 / 10 |
| quiet 9–12, 42 | 0.728 / 3.1 / 46 | 0.752 / 3.8 / 33 | 0.753 / 4.4 / 30 | 0.739 / 7.5 / 9 |

gbm flickers (7 to 8 switches a year) and will not pass the guards; `rule_named` switches a little over 4
times a year. Both are kept because they were written down as candidates before these numbers.

## How it is evaluated (and why this design)

The usual design (pick on the real 1999–2009 holdout, decide on 2009–2026) does not work here:

- the 1999–2009 holdout cannot run a display: the jump model needs the stress and inflation scores, whose
  inputs mostly start in 2002–2003 (credit ETFs, breakevens), and a model needs 5 years of training. Its growth
  part has also been used twice already (SLOWDOWN.md, SAHM_HY.md);
- simulated data cannot pick either (diagnosis, point 4).

So the selection and the decision are both on the real out-of-sample period, split in two, in **one command
run once**, plus a second reference that no version of the model has ever been scored against:

- **Selection: 2009-04-03 to 2017-12-29** (first part), against `CFNAIMA3 < 0` outside stress episodes.
- **Decision: 2018-01-02 to the last day** (second part), never used to choose, same reference.
- **Second reference, whole period: real GDP grew slower than potential GDP** that quarter (FRED `GDPC1`
  against the Congressional Budget Office's `GDPPOT`, latest vintages, outside stress episodes). It is built
  differently from CFNAI (output, not 85 activity indicators) and its trend is the CBO's estimate of potential
  growth, which follows the slower growth of the 2010s instead of CFNAI's 1967–today average (SLOWDOWN.md,
  "What it does not show"). It is evaluation only, never a model input, and was never looked at.

What is not blind, said plainly: v2.2's displayed 0.492 and the growth score's 0.620 on the whole period are
already published, and that is why rule-based candidates are expected to do better than v2.2 against CFNAI.
The margins, the split and the second reference are there so that "expected" is not enough to pass.

Data windows: simulated data for the diagnosis and candidate list; no 1999–2009 data; one real run on
2009-04-03 onwards (the out-of-sample period of every real run since PR #4).

### Selection (first part, `slowdown_v23.select`)

A candidate qualifies if, on the first part, it switches regime **at most 4 times a year** and its median
displayed Slowdown spell is **at least 15 days** (`slowdown_v23.guards`). Among those, the highest displayed
balanced accuracy wins; one within 0.01 of the best counts as tied, and ties go to the earlier candidate.
The winner must beat v2.2's first-part balanced accuracy by **at least 0.02**; otherwise nothing is selected
and v2.3 stops there.

### Decision (`slowdown_v23.decide`)

**v2.3 is adopted only if every condition holds:**

1. a candidate is selected on the first part;
2. second part: its displayed Slowdown balanced accuracy is **at least 0.55**;
3. second part: **at least 0.02 above v2.2's** on the same days (Slowdown's earlier +0.012 was not evidence,
   INFLATION.md uses the same 0.02);
4. second part: it finds **at least as many** reference slowdown days as v2.2 (share found);
5. second part: its shown Slowdown days are reference slowdown days **more often than an average day** (precision
   above the base rate);
6. second reference (GDP below potential), whole period: balanced accuracy **above 0.5 and at least 0.02 above
   v2.2's**;
7. whole period: at most **4 regime switches a year**;
8. whole period: median displayed Slowdown spell of **at least 15 days**;
9. P(stress) identical on every day in every display (so detection 11/11 with every latency, false positives,
   false alarms, Brier and ECE are v2.2's by construction).

What the procedure does on simulated data (the hidden regime as the only reference, condition 6 left out):
13 seeds × 2 worlds = 26 runs. A candidate is selected in 11; **v2.3 would be adopted in 1** (quiet world,
seed 42). The others fail on condition 3 (9 runs), condition 4 (4) or condition 7 (2). Where simulated data
says the change is not better, the procedure almost always says no.

### If it passes / if it fails

- **Passes:** `models.combined.calm: <selected>` and `models.version: v2.3` in `config/settings.yaml`, in the
  commit after the Results. The next daily job writes a new backtest record (new fingerprint); days already
  published keep v2.2. README and REGIMES.md get a note.
- **Fails:** nothing changes, v2.2 stays, and this page says which condition failed. Any later attempt needs a
  new pre-registration, and the 2018–2026 CFNAI comparison and the GDP reference then count as seen.

## Commands

    python -m pfe_drai --provider fred slowdown --v23

Needs `FRED_API_KEY` (the two references) and `TIINGO_API_KEY` (as every real run). It prints every display
on the first part, the second part, the whole period and against GDP, then the selection and the decision.
Without `--provider fred` it runs on simulated data and is a check of the procedure only.

Simulated experiments: `python docs/experiments/slowdown_v23.py 1 2 3 4 5 6 7 8` (add `quiet` for the quiet
world).

## What this does not claim

- Slowdown does not predict anything. It labels below-trend growth, read from published data.
- Neither reference is the truth. If neither CFNAI nor GDP can be matched better than chance by any display,
  that is a valid result: the app would then say Slowdown is a label of its growth score, not of the economy.
- A pass would be about what is **displayed**. The rule, the growth score and the models are unchanged.

## Results

### The one real run (Henry, 2026-10-03)

`python -m pfe_drai --provider fred slowdown --v23`, out-of-sample 2009-04-03 to 2026-10-02, model combined.
P(stress) identical in every display: yes.

Displayed Slowdown against the reference's slowdown days (bal. acc. = balanced accuracy; found = share of reference
slowdown days shown as Slowdown; right = share of shown Slowdown days that are reference slowdown days; ref. days =
their share of all days; switches = regime switches a year; spell = median displayed Slowdown spell, days):

| | display | bal. acc. | found | right | ref. days | shown | switches | spell |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **first part (selection)**, CFNAIMA3 | jump (v2.2) | 0.473 | 7.1% | 43.2% | 57.2% | 9.4% | 2.29 | 34 |
| | rule | 0.476 | 31.5% | 53.6% | 57.2% | 33.6% | 3.89 | 21 |
| | rule_named | 0.480 | 31.1% | 54.2% | 57.2% | 32.8% | 4.35 | 21 |
| | gbm | 0.480 | 26.8% | 53.7% | 57.2% | 28.5% | 8.01 | 7 |
| **second part (decision)**, CFNAIMA3 | jump (v2.2) | 0.515 | 17.4% | 55.7% | 50.8% | 15.7% | 3.66 | 31 |
| | rule | 0.735 | 77.2% | 72.5% | 50.8% | 53.8% | 4.92 | 70 |
| | rule_named | 0.737 | 76.8% | 72.9% | 50.8% | 53.2% | 5.60 | 60 |
| | gbm | 0.727 | 75.2% | 72.2% | 50.8% | 52.5% | 9.83 | 26 |
| **whole period**, CFNAIMA3 | jump (v2.2) | 0.492 | 11.9% | 51.0% | 54.0% | 12.5% | 2.97 | 34 |
| | rule | 0.599 | 52.9% | 65.2% | 54.0% | 43.7% | 4.40 | 39 |
| | rule_named | 0.602 | 52.5% | 65.8% | 54.0% | 43.0% | 4.97 | 34 |
| | gbm | 0.596 | 49.4% | 65.7% | 54.0% | 40.5% | 8.92 | 11 |
| **whole period, GDP below potential** | jump (v2.2) | 0.505 | 13.5% | 26.5% | 25.0% | 12.5% | 2.97 | 34 |
| | rule | 0.523 | 46.8% | 27.0% | 25.0% | 43.7% | 4.40 | 39 |
| | rule_named | 0.525 | 46.2% | 27.1% | 25.0% | 43.0% | 4.97 | 34 |
| | gbm | 0.521 | 43.2% | 26.9% | 25.0% | 40.5% | 8.92 | 11 |

Selection: `rule` qualifies on the first part (3.89 switches a year, 21-day spell); `rule_named` (4.35) and `gbm` (8.01)
switch too often. `rule` beats v2.2 by 0.003, short of the 0.02 margin, so **no candidate is selected** and the
decision stops at condition 1. **Decision: v2.3 is not adopted; v2.2 stays.** Nothing was retuned.

What it shows, said plainly:

- **2009–2017: no display matches CFNAI.** Every display, v2.2's included, is below or at chance (0.47–0.48). In those
  years CFNAI is below its 1967–today trend on 57% of days while the growth score's median comes from a history that
  starts in 2004; whatever the display, the app and the reference disagree about what "below trend" means then.
- **2018–2026: the rule-based displays match CFNAI well** (0.735 against v2.2's 0.515). This part was never used to
  choose, so it is the most interesting number of the run, but the protocol chose on the first part and the first part
  said no. It is not a pass.
- **Even without the selection step, `rule` would have failed** two other conditions: GDP below potential, +0.018
  against the 0.02 required (0.523 against 0.505, both close to chance), and 4.40 regime switches a year on the whole
  period against at most 4.
- **The second reference says the same as the first part:** against GDP growth below the CBO's potential, no display
  is clearly better than chance (0.505–0.525). Below-potential quarters are 25% of days, against 54% for CFNAI: the two
  references disagree with each other about most of the 2010s.
- Detection and calibration were untouched by construction and the run confirmed it (P(stress) identical).

What it means for the app: the honest label is that **Slowdown is the growth score below its own median**, a
persistent reading of growth inputs, and not a match for an outside measure of the economy over the whole period.
Any later attempt needs a new pre-registration, and the whole 2009–2026 period now counts as seen for displayed
Slowdown against both CFNAI and GDP below potential. A real blind test would have to be a forward one (a live shadow
run, as for the challengers, CHALLENGERS.md), scored on months that have not happened yet.
