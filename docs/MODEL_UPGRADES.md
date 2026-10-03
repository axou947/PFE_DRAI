# Seven candidate upgrades of the regime model: tested on simulated data, none adopted

**Status: NONE ADOPTED, 2026-10-03.** No candidate beat v2.2 on simulated data without losing something
the model is judged on, so the published model stays **v2.2** and its settings fingerprint does not change.
Nothing was run on real data, so the real out-of-sample period stays unseen for each of these ideas.
The inflation score is not covered here ([INFLATION.md](INFLATION.md)).

## The question (Henry, 2026-10-03)

"Is there any other improvement we can make to our regime detection model? Look at every alternative,
test it, and explain why an added feature could be better."

## Where v2.2 is weak (from the earlier pages, real data)

- **False alarms:** 1.26 a year against a limit of 1.5 ([DETECTION_V2.md](DETECTION_V2.md)).
- **Displayed Slowdown:** about chance against the CFNAI reference, 0.492 ([SLOWDOWN.md](SLOWDOWN.md)).
- **Calibrated P(stress):** too cautious above 30% ([CALIBRATION.md](CALIBRATION.md)). Its weight has been
  rising as history accumulates. Simulated data cannot show this problem, so it is not tested here.
- **Already rejected, not redone:** faster stress inputs in the stress score, averaging the stress sources,
  the alarm on the calibrated P, majority-vote naming, a 5 to 8 state jump model, and one vote per inflation source.

## Candidates (from the literature and the weak spots above)

| candidate | what changes | why it could help |
|---|---|---|
| `onset_downside` | onset detector + EWMA downside deviation (half-lives 5 and 21 days), EWMA return, Sortino ratio, worst day of 10 | the features Shu & Mulvey use for jump models (2024); a fall shows in downside risk before total volatility |
| `onset_flight` | onset detector + 10-year yield change (5 and 21 days), 63-day correlation of stocks and yields | flight to quality: Treasuries rally when stocks fall in a crisis |
| `hysteresis` | alarm still on after 3 days above 0.5, but off only once the score falls below 0.3 | fewer short re-starts of the alarm, which are counted as new false alarms |
| `jump_downside` | jump model clusters the 3 scores + 2 downside inputs (z-scored); states named on the 3 scores | as in Shu & Mulvey and Aydinhan et al. (2024), where the jump model reads return-based features |
| `hmm` | Gaussian hidden Markov model (4 states) instead of the jump model, filtered (causal) probabilities | the classic regime model (Hamilton, Ang & Bekaert): a baseline the jump model should beat |
| `growth_fast` | production over 6 months (annualised) instead of 12; claims as the rise of their 4-week average over the 52-week low, instead of a 3-month change | slower inputs make Slowdown late; the claims signal is the one used in the Learn checklist |
| `calm_blend` | the calm regimes shown = average of the jump model's and gbm's | gbm learns the rule labels, whose growth score now matches slowdowns better |

Every input uses past data only. The run is `docs/experiments/model_upgrades.py` (needs `hmmlearn` for `hmm`).
It patches the package inside its own process, so no candidate touches the model.

## Results: 13 simulated histories (seeds 1–12 and 42, 229 stress episodes)

Means over the seeds. Lower is better for latency, false positives, alarm time, Brier, ECE and switches.
"Accuracy" is the share of days the displayed regime equals the simulator's hidden regime.
"Slowdown shown" is the balanced accuracy of the displayed Slowdown against the hidden one.

| candidate | detected | lat. all | FP / yr | false alarm | Brier | ECE | switches / yr | accuracy | Slowdown shown | stress recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **v2.2 (published)** | **221/229** | −3.4 | 0.643 | 10.3% | 0.180 | 0.067 | 3.2 | 0.727 | 0.798 | 0.662 |
| onset_downside | 215 | −3.4 | **0.577** | 10.0% | 0.181 | 0.071 | 3.2 | 0.728 | 0.798 | 0.671 |
| onset_flight | 216 | −3.7 | 0.631 | 10.3% | 0.182 | 0.063 | 3.1 | 0.728 | 0.803 | 0.622 |
| hysteresis | 221 | −3.5 | 0.616 | 10.9% | 0.180 | 0.067 | 3.2 | 0.727 | 0.798 | 0.662 |
| jump_downside | 221 | −3.6 | 0.732 | 10.4% | **0.176** | 0.077 | 3.9 | 0.711 | 0.774 | 0.629 |
| hmm | 221 | −4.2 | 0.705 | 11.4% | 0.181 | 0.071 | 3.5 | 0.689 | 0.762 | 0.508 |
| growth_fast | 220 | −3.5 | 0.615 | 10.5% | 0.178 | **0.063** | 3.4 | 0.723 | **0.804** | **0.689** |
| calm_blend | 221 | −3.4 | 0.643 | 10.3% | 0.180 | 0.067 | 6.7 | 0.728 | 0.768 | 0.664 |

How many of the 13 seeds each candidate made better / worse than v2.2:

| candidate | detected | FP / yr | false alarm | Brier | ECE | accuracy | Slowdown shown | switches |
|---|---|---|---|---|---|---|---|---|
| onset_downside | 2 / 6 | 9 / 2 | 9 / 4 | 4 / 7 | 4 / 8 | 7 / 5 | 6 / 6 | 7 / 5 |
| onset_flight | 0 / 4 | 5 / 5 | 7 / 6 | 4 / 9 | 7 / 5 | 7 / 5 | 9 / 4 | 10 / 3 |
| hysteresis | 0 / 0 | 6 / 0 | 0 / 13 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| jump_downside | 0 / 0 | 0 / 10 | 6 / 6 | 11 / 0 | 3 / 10 | 2 / 10 | 2 / 10 | 1 / 12 |
| hmm | 0 / 0 | 1 / 6 | 1 / 12 | 6 / 4 | 4 / 9 | 2 / 11 | 4 / 9 | 5 / 7 |
| growth_fast | 1 / 2 | 6 / 5 | 6 / 7 | 9 / 3 | 9 / 4 | 6 / 7 | 6 / 7 | 5 / 8 |
| calm_blend | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 7 / 5 | 2 / 10 | 0 / 13 |

## What each result says

- **onset_downside cuts false alarms by 10%** (0.643 → 0.577 a year, better in 9 seeds) **but misses 6 more
  crises** (215 against 221). The detector has to learn more inputs from a few dozen crises per history, and
  it becomes more cautious. Losing crises is the one thing the alarm must not do. **Not adopted.**
- **onset_flight** misses 5 more crises and gets worse on Brier in 9 seeds. **Not adopted.** In the simulator
  the 2-year yield falls in stress by construction, so this test is, if anything, too easy on the idea.
- **hysteresis** lowers the count of false alarms (never higher in any seed) only by keeping the alarm on longer:
  alarm time is higher in all 13 seeds. That is the "metric that could be fooled" from DETECTION_V2.md: fewer
  re-starts, the same alarms. **Not adopted.**
- **jump_downside** has a better Brier in all 11 seeds that moved, but a worse displayed regime (accuracy worse
  in 10), more false alarms (worse in 10) and more switches (worse in 12). Downside features pull the jump
  model's states towards market moves and away from the economy. **Not adopted.**
- **hmm** is clearly worse: it shows stress on half the hidden stress days against two thirds for the jump model,
  and its accuracy is worse in 11 seeds. This confirms the jump model was the right choice. **Not adopted.**
- **growth_fast** is the closest call: better Brier and ECE in 9 seeds, Slowdown found on more of the hidden
  slowdown days (77.5% against 74.9%), and fewer false alarms on average. But the growth score matches the
  hidden slowdowns worse (0.693 against 0.707, worse in 8 seeds), and accuracy and the displayed Slowdown are
  better in only 6 seeds of 13. That is noise, not an improvement. **Not adopted.**
- **calm_blend** doubles the regime switches (3.2 → 6.7 a year, worse in every seed) and the displayed Slowdown
  is worse in 10 seeds. **Not adopted.**

## What simulated data cannot test

Some promising inputs do not exist in the simulator, so they can only be judged on a real holdout:

- the **VIX term structure** (VIX over 3-month VIX, FRED `VXVCLS` from 2007), which inverts in stress;
- **high-yield spreads over 5 days** (HYG from 2007 only);
- the **Sahm rule / unemployment** for Slowdown (in the Learn checklist, not in the model).

Each would need its own pre-registration and a real holdout that excludes the 11 published episodes (for
example 1993–2009, as for the onset detector). Two of them start in 2007, which leaves almost no holdout,
and that is the reason not to rush them.

## Sources

- Shu, Yu & Mulvey (2024), *Downside risk reduction using regime-switching signals: a statistical jump model
  approach*, Journal of Asset Management. [link](https://link.springer.com/article/10.1057/s41260-024-00376-x)
- Aydinhan, Kolm, Mulvey & Shu (2024), *Identifying patterns in financial markets: extending the statistical
  jump model for regime identification*, Annals of Operations Research.
  [link](https://www.researchgate.net/publication/380569959_Identifying_patterns_in_financial_markets_extending_the_statistical_jump_model_for_regime_identification)
- Nystrup, Lindström & Madsen (2020), *Learning hidden Markov models with persistent states by penalizing
  jumps*, Expert Systems with Applications: the jump model used since v1.
- Baur & Lucey (2009) and the stock–bond correlation literature on flight to quality.
