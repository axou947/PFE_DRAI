# Detecting stress: from v1 to v2

## Version 1 and why it was slow

The first default model, `combined`, takes the regimes of the jump model and sets P(stress) to the maximum of the jump model and a gradient boosting model. It was chosen on simulated data. The one real run, made after the choice was pushed, is quoted here as published.

{{quote:DETECTION.md#Real data (run once, 2026-10-01)}}

On the 11 real out-of-sample episodes, version 1 caught 5, with a median delay of 11 days, which fails the latency target. The pre-registration of version 2 gives two reasons, found by reading the code and not the episodes. First, the models learn a different event from the one they are scored on: gradient boosting learns the label "stress score above 1", while the episodes are dated by a drawdown or volatility rule, so a fall of 10% can happen while the stress score stays low and no model trained on that label can call it. Second, the inputs are slow and their scale drifts: expanding z-scores over a history that contains 2008 shrink every later reading, and a quarter-long credit change reacts late by construction.

## Version 2: a stress-onset detector

Version 2 adds a third stress source, a detector of the *start* of an episode (`models/onset.py`), so that P(stress) is the maximum of the jump, gradient boosting and onset outputs.

- **Target**: the frozen episodes themselves, not the rule label. A day is positive if an episode starts within {{config.models.onset.horizon_days}} business days or started less than {{config.models.onset.after_start_days}} business days ago.
- **Inputs**: fast market indicators in their own units, so a value means the same in 1998 and in 2025: drawdown, 5-, 10- and 21-day returns and realised volatility, volatility against the frozen rule's line, the VIX, its 5-day log change and its ratio to its 3-month mean.
- **Hold**: a probability holds {{config.models.onset.hold_days}} days (minimum time on), against flicker around the threshold.
- **Learner**: gradient boosting or logistic regression, refitted every {{config.models.onset.refit_every_days}} business days on the past only.

By construction, version 2 can only raise P(stress), so on any data it detects every episode that version 1 detects, no later. What it can cost is false alarms, and that is what the decision rule watched.

## Selection and decision

The design was chosen on simulated data. The learner and its inputs were then chosen on a real holdout the models had never scored (1999 to 2009, before the out-of-sample period), by a selection rule written beforehand: a candidate must meet both false-alarm targets on its own, the lowest median delay over all episodes wins, and ties go to fewer false positives.

{{quote:DETECTION_V2.md#Results > Step 1: holdout}}

The selected detector, gradient boosting on market inputs, was then run once on the 11 real episodes, with the decision rule that version 2 is adopted if it meets both false-alarm targets.

{{quote:DETECTION_V2.md#Results > Step 2: the 11 real episodes}}

Version 2 was adopted: every episode was caught within four days of its dated start and the latency target was met for the first time on real data.

## The current version, from its backtest record

The tables and figures below are generated from the backtest record of version {{meta.model_version}}, the version published today. It carries the calibrated probability (Chapter 6) and the Slowdown change (Chapter 7); neither changes the stress alarm, which still reads the detector score, so its episode delays are those of version 2 (the check of Appendix A confirms this against the table quoted above).

{{table:metrics}}

{{table:episodes}}

{{figure:latency}}

{{figure:timeline}}

## What it costs, and what it does not show

- **False alarms rise** from {{cell:DETECTION_V2.md#Results > Step 2: the 11 real episodes | v1 (jump + gbm) | FP / yr}} to {{cell:DETECTION_V2.md#Results > Step 2: the 11 real episodes | v2 (jump + gbm + onset) | FP / yr}} per year between versions 1 and 2 (quoted above); the current record has {{backtest.current.metrics.false_positives_per_year|2}} per year, close to the limit of {{backtest.current.targets.max_false_positives_per_year|1}}. Over the {{backtest.current.metrics.n_days}} out-of-sample days there are {{backtest.current.metrics.n_alarms}} alarms, of which {{backtest.current.metrics.n_false_alarms}} are false. A reader of the live record should expect roughly one false alarm a year.
- **A large negative delay is not foresight.** The largest negative delays, of the order of 20 business days in the table above, usually mean that an alarm from an earlier dip was still running when the episode started.
- **The detector watches the market the rule is built on.** Its speed partly comes from reading the same drawdown and volatility the episode rule dates, so a delay near 0 means "on the day the rule dates the start". The negative delays are the forecasting part, and they are shown episode by episode.
- **{{backtest.current.metrics.n_episodes}} episodes are few**, and a median moves a lot with one episode. The holdout adds a few more from a different era, and both runs point the same way, but this is evidence and not proof. The episodes are now seen: no retuning is allowed without a new pre-registration.
