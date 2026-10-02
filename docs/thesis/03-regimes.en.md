# Regimes on three dimensions

## Three dimension scores

Regimes are not read on two axes but on three scores, each the average of expanding z-scores (only the past is used, monthly releases dated by their publication day). A high score means more of the dimension.

| Dimension | Indicators |
|---|---|
| Stress | VIX level, 21-day realised volatility, credit stress (HYG against IEF, LQD before 2007), drawdown from the 1-year high |
| Growth | 6-month equity momentum, 10y-2y curve slope, industrial production (1 year), jobless claims (3 months, sign flipped) |
| Inflation | CPI (1 year), 10-year breakeven level, breakeven change (3 months), 2-year rate change (6 months) |

## The rule that defines the four regimes

A transparent rule on the three scores, set in `regimes.rule`, labels every day of history. It is applied in this order:

1. **Stress** if the stress score exceeds {{config.regimes.rule.stress_threshold|1}}, whatever growth and inflation do;
2. otherwise **Inflationary overheating** if the inflation score exceeds {{config.regimes.rule.inflation_threshold|1}};
3. otherwise **Slowdown** if the growth score is below {{config.regimes.rule.growth_threshold|1}} (growth below its own historical median since version v2.2, Chapter 7);
4. otherwise **Expansion**.

Each regime is therefore a region of the three-dimensional space, not a quadrant. The rule is both the label that the supervised models learn and the reference that names the states of the unsupervised ones. This has a consequence stated again in the limitations: the regimes are defined by a rule, not observed, so agreement with the rule is not agreement with an independent truth (the Slowdown regime is the one case checked against an outside measure, Chapter 7).

## Naming the states of unsupervised models

The jump model and k-means group days into four states that have no name. At every walk-forward refit, each state takes the name of the regime whose centre is closest to its own. The centre of a regime is the average position, on the three scores, of the training days the rule puts in that regime. For each state the evidence is kept: the distance, its number of training days and the share of those days the rule puts in each regime. The share of its own name is the state's *agreement with the rule*, and a state under 50% is called mixed. Two states can share a name, and a regime absent from the training window names no state. Nothing is set by hand.

## What the real data showed

The naming was chosen on simulated data. On real data, one pre-registered run checked that detection did not regress and described the states.

{{quote:REGIMES.md#Results > Real data, 2026-10-01}}

Two readings follow. The Stress state is clean at every refit, which is what the detection chapters rely on. The Slowdown state is not a distinct group of days, which motivated the work of Chapter 7.
