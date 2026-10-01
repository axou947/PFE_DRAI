# Calibrated stress probability: pre-registration

**Status: pre-registered on 2026-10-01, before any run on real data.** This page fixes what was
changed, how it was chosen (simulated data only), and the rule that decides on real data. It is
committed and pushed before Henry runs anything; the real results are added under "Results" as
they come out, and nothing above that heading changes afterwards.

## The problem

"Calibrated" means that on the days the app says about 30% stress, stress follows about 3 times in
10. v2 (docs/DETECTION_V2.md) shows P(stress) = max(jump, gbm, onset). That number is a good
**detector score** (11/11 real episodes, median latency −3 days) but not a probability:

- the jump model's probabilities swing between 0% and 100% (a softmax of a distance);
- the highest of three numbers is biased upwards when the models disagree;
- and the other way: most days the score is near 0%, including many days inside long episodes
  that no model flags any more.

### The event a probability is checked against

**Inside an episode of the frozen rule, or one starts within 5 business days**
(`validation.calibration.target_horizon_days: 5`, `validation/calibration.py:stress_event`). It is
the event the detector is scored on (an alarm up to a week before the dated start counts), and the
episodes come from the frozen rule (sha256 `6741b674…`, unchanged). The outcome of a day is known
5 business days later; scores on a past date leave those days out.

### Scores (lower is better for the first three)

- **Brier**: mean squared gap between the probability and the outcome (0 or 1).
- **Log loss**: punishes confident mistakes most (a 99% call that does not come true).
- **ECE** (expected calibration error): days grouped in 10 bins of predicted probability, the gap
  between the average prediction and the observed frequency in each bin, weighted by its days.
  This is what the reliability chart shows.
- **Brier skill**: 1 − Brier / Brier of always saying the observed frequency (above 0 = useful).

### Baseline: v2 is badly calibrated (simulated data)

Measured before any change, out-of-sample, seeds 1–8 (development) and 9–12, 42 (confirmation):

| P(stress) = v2 detector score | Brier | log loss | ECE   | mean P | observed |
|-------------------------------|------:|---------:|------:|-------:|---------:|
| seeds 1–8                     | 0.217 | 1.067    | 0.202 | 18.8%  | 24.6%    |
| seeds 9–12, 42                | 0.224 | 1.043    | 0.206 | 20.3%  | 24.9%    |

Seed 42 in detail (`python -m pfe_drai calibration`): the 3,798 days the score put under 10% saw
stress 14.7% of the time, and the 658 days above 90% saw it 57% of the time.

## What changes

`models.combined.stress_combination: calibrated` (`models/calibrator.py`, `models/combined.py`):

    P(stress) = sigmoid(b + w × logit(detector score))

**Platt scaling** of the v2 detector score: two numbers, refitted every 126 business days on past
days only, weight kept ≥ 0 (a higher score can never lower the probability), small ridge penalty.

- **Out-of-sample inputs.** A calibrator fitted on in-sample predictions learns their
  overconfidence. So the three models start predicting 2 years into the data
  (`stack.warmup_days: 504`) instead of 5, on the same refit dates: from the backtest start on,
  their predictions are exactly the usual ones (tested). At each refit, the calibrator learns from
  the earlier out-of-sample scores, the last 5 days dropped (outcome not known yet). Removing the
  last two years of data changes no earlier probability (tested).
- **Fallback.** With fewer than 20 stress-event days in the past, P(stress) is the detector score,
  as in v2, and the day is marked not calibrated. On real data the 2008 crisis is in the first
  window, so this should not happen.
- **The calm regimes** keep the jump model's proportions and share 1 − P(stress), as before.

**The stress alarm does not change.** It still reads the detector score: on once it stays above
0.5 for 3 days. Detection (episodes caught, latency, false alarms, alarm time) is therefore
identical to v2 by construction (tested). The app, the committee note, the API and the daily
track record now show both: the calibrated probability, and the alarm with its score and date.

Why not put the alarm on the calibrated probability (the first idea): on simulated data, no
threshold on the calibrated probability keeps v2's detections within the false-alarm targets.

| alarm reads (seeds 1–8, 137 episodes) | detected | median lat. (all) | FP / yr | false alarm |
|---------------------------------------|---------:|------------------:|--------:|------------:|
| **detector score > 0.50 (v2, kept)**  | 130      | −6.0              | 0.52    | 9.5%        |
| calibrated P > 0.30                   | 113      | −6.25             | 0.67    | 13.6%       |
| calibrated P > 0.35                   | 103      | −0.5              | 0.45    | 9.5%        |
| calibrated P > 0.40                   | 86       | +4.25             | 0.37    | 7.8%        |

A crisis start is a rare, fast event; "in an episode or one starting within a week" is mostly the
long middle of episodes. A probability honest about the second is a slower detector of the first.
So each number does one job: the alarm is tuned for speed, the probability says how often stress
followed.

## How it was chosen (simulated data only)

Development on seeds 1–8 (`docs/experiments/calibration.py`). Six low-parameter calibrators,
fixed before running them: the input is the detector score alone (Platt, 1 weight) or one weight
per model (stacked logistic, 3 weights) or both (4), read in log-odds or as a probability.
Isotonic regression and boosting were left out before any run: the real history has about a dozen
crises, which a flexible calibrator would learn by heart.

| calibrator (seeds 1–8)                | weights | Brier | log loss | ECE   |
|---------------------------------------|--------:|------:|---------:|------:|
| v2 detector score (no calibration)    | –       | 0.217 | 1.067    | 0.202 |
| **Platt, log-odds of the score**      | 1       | 0.179 | 0.546    | 0.065 |
| Platt, score as a probability         | 1       | 0.177 | 0.543    | 0.075 |
| stacked, log-odds of each model       | 3       | 0.178 | 0.551    | 0.061 |
| stacked, each model as a probability  | 3       | 0.179 | 0.554    | 0.062 |
| stacked + score, log-odds             | 4       | 0.178 | 0.552    | 0.062 |
| stacked + score, as probabilities     | 4       | 0.178 | 0.552    | 0.064 |

All six land within 0.002 of each other on Brier, so the simplest won: one weight on the detector
score. Between its two forms, the log-odds one (Platt's own form) has the lower ECE, which is the
score the reliability chart shows. Either way the probability is a rising function of the score
the alarm reads, so the two never point in opposite directions within a refit.

Confirmation on seeds 9–12 and 42 (92 episodes), never used while choosing:

| seeds 9–12, 42                     | Brier | log loss | ECE   | regime switches / yr |
|------------------------------------|------:|---------:|------:|---------------------:|
| v2 detector score                  | 0.224 | 1.043    | 0.206 | 6.2                  |
| **Platt (adopted on this branch)** | 0.184 | 0.550    | 0.065 | 3.4                  |

Every one of the five seeds improves on all three scores. The regime flickers less (3.4 switches a
year against 6.2), because a 20% → 35% move no longer flips the regime to stress; the alarm still
fires on the same days.

## Protocol (fixed before any real run)

One run on real data, by Henry, of each:

    python -m pfe_drai --provider fred calibration
    python -m pfe_drai --provider fred backtest

- Data: the usual real-data setup (FRED + Tiingo, ALFRED first releases), out-of-sample from
  2009-04 as in every earlier real run, every day whose outcome is known.
- **Decision**: `stress_combination: calibrated` stays (and becomes the daily publication) if, on
  real data, the calibrated P(stress) has a **lower Brier score and a lower ECE** than the v2
  detector score, on the same days. Otherwise it goes back to `max` (v2 as published).
- **Check, not a decision**: in `backtest`, the `combined` and `v2` rows must show the same
  detections, latencies, false positives and alarm time. A difference is a bug to fix, not a result.
- Whatever the outcome, every number is published here: Brier, log loss, ECE, Brier skill, mean
  probability against observed frequency, the reliability table of both, the calibrator's weights
  over time, and the backtest rows.
- Nothing is retuned after the run. The 1999–2009 holdout (docs/DETECTION_V2.md) cannot test this:
  the jump model and gbm need series that start in 2003.

### What this does not claim

- **11 crises are few, and days are not independent.** A month inside one crisis is ~20 correlated
  days; the top bins of the reliability chart rest on a handful of episodes and will stay noisy.
  The scores say whether the probability is better than v2's, not that it is exact.
- **The probability is about the frozen rule's episodes** (a 10% fall or a volatility spike), not
  about losses or any other definition of a crisis.
- **The first calibrator (2009) learned from one crisis (2008)**, out-of-sample scores from 2006
  on. Its numbers are rougher in the early years; the chart in the app is computed as known on the
  chosen date, so this shows.
- **It will rarely say 90%.** On simulated data the calibrated probability seldom goes past 70%:
  even a high score was followed by the event only about 6 times in 10. That is the point.

## Results

_To be filled with the real-data run, as it comes out._
