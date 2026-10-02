# Validation framework

## Dating stress episodes with a frozen rule

Detection is scored against stress episodes that a fixed rule dates from the equity series (SPY) alone. An episode starts at the first crossing of a {{config.validation.episodes.drawdown_threshold|pct0}} drawdown from the 252-day high, or when {{config.validation.episodes.vol_window}}-day realised volatility rises above its expanding {{config.validation.episodes.vol_quantile|pct0}} quantile. It ends when the drawdown recovers above {{config.validation.episodes.recovery_drawdown|pct0}}, or after {{config.validation.episodes.max_duration_days}} business days, and at least {{config.validation.episodes.min_gap_days}} business days separate the end of an episode from the next start.

{{table:rules}}

The parameters are **frozen**. Their SHA-256, `{{config.validation.episodes.frozen.sha256}}`, was fixed on {{config.validation.episodes.frozen.date|date}}, before any backtest on real data, and the code refuses to run with a rule whose parameters no longer match it. A new version of the rule would need a new hash, a date and a public reason. The rule is deliberately independent of the models: the episodes cannot be adjusted to flatter a detector.

## Detection, delay and false alarms

A stress alarm is on when the detector score exceeds {{backtest.current.rules.alarm_threshold|1}} for {{backtest.current.rules.confirm_days}} consecutive days. An episode counts as detected if an alarm falls between {{backtest.current.rules.lookback_days}} business days before its dated start and {{backtest.current.rules.detection_window_days}} business days after it; later than that it is missed. The **delay of every episode** is reported, not only the median, and a negative delay means that an alarm was already on before the dated start. This is not always foresight: an alarm left on by an earlier dip also gives a negative delay (Chapter 5 shows examples).

A **false alarm** is the onset of an alarm outside every episode (widened by the look-back). Two measures guard against a metric that could be fooled. A signal that stays on would score almost no false-alarm onsets, and a median over detected episodes improves by missing the hard ones. So the report also gives the median delay over *all* episodes (a missed one counting as the end of the detection window) and the **share of calm days with the alarm on**.

The targets, fixed before testing, are a median delay of at most {{backtest.current.targets.max_median_latency_days}} business days, at most {{backtest.current.targets.max_false_positives_per_year|1}} false alarms per year and at most {{backtest.current.targets.max_false_alarm_share|pct0}} of calm days in false alarm.

## Walk-forward evaluation

Every model is evaluated walk-forward on an expanding window: it is fitted on the past, predicts forward, and is refitted every {{config.validation.refit_every_days}} business days (every {{config.models.gbm.refit_every_days}} for the gradient boosting models, which are slower to fit), after a minimum training window of {{config.validation.min_train_days}} business days. Days whose outcome is not yet known are left out of each fit, and tests check that the jump model's filter, the onset detector and the calibrator never use the future (removing recent data changes no earlier prediction).

## Scoring a probability

The stress probability is checked against an event: **inside an episode, or one starts within {{backtest.current.rules.calibration_horizon_days}} business days**. The scores are the Brier score, the log loss, the expected calibration error (days grouped in 10 bins of predicted probability, the gap between the average prediction and the observed frequency in each bin, weighted by days) and the Brier skill against always predicting the observed frequency.

## The pre-registration protocol

A model change follows the same sequence every time. The problem, the change and the numeric decision rule, with every condition, are written in a document and pushed **before any run on real data**. The design is chosen on simulated data and on a real holdout that precedes the out-of-sample period. The real backtest is then run **once**. The results are appended under a "Results" heading whatever they are, and nothing above that heading is edited afterwards. A change that fails keeps the previous model in place. Because the real episodes become known to the designer after the first run, the protocol also records that they are *seen*: any retuning needs a new pre-registration with a reason fixed beforehand.

This is not a guarantee against all forms of overfitting. It makes the choices, the order in which they were made and the failures visible, which is what a reader needs in order to weigh the results.

## Evidence and proof

Three words are used consistently. A choice is **pre-registered** when its decision rule was written before the real run. The backtest is **evidence**: out of sample, but computed after the fact with the episodes seen. The live record is **proof**: it is written each evening before the outcome is known (Chapter 10).
