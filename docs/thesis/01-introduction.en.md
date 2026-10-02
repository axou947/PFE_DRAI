# Introduction

## The problem

The risk of a portfolio depends on the market environment it is in: the same positions behave differently in a calm expansion, a slowdown, an inflation surge or a crisis. This project builds a detector that, every business day, says which of four regimes the US market is in (Expansion, Inflationary overheating, Slowdown, Stress), gives a calibrated probability of stress and raises a stress alarm. It is meant as a descriptive risk tool for a risk function, with an explanation attached to each reading, not as a trading signal. The system describes the state of the market and flags the start of stress episodes. It does not forecast crises and it gives no investment advice.

## What this report claims, and what it does not

The models are standard ones: k-means, a statistical jump model, gradient boosting and a two-parameter logistic calibration. The project does not claim a new model. What it documents is a way of working that makes the results checkable:

- the rule that dates stress episodes is **frozen by a hash** before any backtest, and the code refuses a rule that no longer matches it;
- every model change is **pre-registered**: the problem, the change and the numeric decision rule are written and pushed before the single real-data run, and the results are appended under a "Results" heading whatever they are, never edited above it;
- the **latency of every episode** is published, not only a median, together with false alarms per year;
- failures are published as such (Chapters 7 and 8);
- a **live record** is written every business day, hash-chained and timestamped outside the repository (Chapter 10).

## Three levels of evidence

Every performance claim in this report names its data window and model version, and says whether the choice behind it was pre-registered or made after seeing the episodes.

1. **Simulated data** (a generator that reproduces the main crises since 2000) was used to choose designs. It is known to flatter the models, so it proves nothing about real markets.
2. **The real backtest** is walk-forward and out of sample, but it was computed after the fact, and since 2026-10-01 its stress episodes are *seen*: any later tuning needs a reason written down beforehand. It is **evidence**.
3. **The live record** is written each evening before the outcome is known and cannot be rewritten without breaking its hash chain. It is the **proof**, and it is still short: at the time of this build it holds {{live.days}} published day(s), the first on {{live.first_day|date}} and the latest on {{live.last_day|date}}.

## Headline result

For model version {{meta.model_version}}, on the {{backtest.current.metrics.n_episodes}} real stress episodes dated by the frozen rule between {{backtest.current.period.start|date}} and {{backtest.current.period.end|date}} (out of sample, computed after the fact, episodes seen): the stress alarm detected {{backtest.current.metrics.detected}} of them, with a median delay of {{backtest.current.metrics.median_latency|0}} business days relative to the dated start (a negative delay means the alarm was already on), at a cost of {{backtest.current.metrics.false_positives_per_year|2}} false alarms per year. The calibrated probability of stress has a Brier score of {{backtest.current.metrics.brier|3}} and an expected calibration error of {{backtest.current.metrics.ece|3}}. These numbers are read from the backtest record when the report is built; Chapter 5 gives them in full, episode by episode.

Two results are weak, and the report says so where they are presented: the Slowdown regime shown by the model matches an outside measure of activity no better than chance (Chapter 7), and the euro-area version failed its pre-registered decision rule (Chapter 8).

## How to read this report

Chapters 2 to 4 describe the data, the regimes and the validation framework. Chapters 5 to 7 follow three model changes through the same protocol: detection, calibration and the Slowdown regime. Chapter 8 applies the protocol to a new region and reports its failure. Chapter 9 describes the world-markets view, which is descriptive and not validated like the US model. Chapter 10 presents the live record and Chapter 11 the limitations. Appendix A gives what is needed to reproduce the document.

Tables, figures and numbers in this report are generated from the repository's records, and results that exist only in the project's documents are quoted verbatim with their source and commit. The command `python -m pfe_drai thesis --check` compares what the documents print with the records.
