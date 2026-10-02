# Calibrating the stress probability

## The problem

"Calibrated" means that on the days the system says about 30% stress, stress follows about three times in ten. The version 2 score, the maximum of three models, is a good *detector score* but not a probability. The jump model's probabilities swing between 0% and 100%, the maximum of three numbers is biased upwards when the models disagree, and most days the score is near zero, including many days inside long episodes that no model flags any more. On simulated data the uncalibrated score had a Brier score of about 0.22 and a calibration error of about 0.20 (see the pre-registration).

## The change

The published probability becomes a Platt scaling of the detector score,

P(stress) = sigmoid(b + w × logit(score)),

with two parameters refitted every {{config.models.combined.stack.refit_every_days}} business days on past days only. The weight is kept non-negative, so that a higher score can never lower the probability, and a ridge penalty (strength {{config.models.combined.stack.l2|1}}) keeps it small. A calibrator fitted on in-sample predictions would learn their overconfidence, so the three models start predicting {{config.models.combined.stack.warmup_days}} days into the data and the calibrator learns only from out-of-sample scores. The alarm does not change: it keeps reading the detector score.

## The decision rule and the result

The rule written before the single real run was: the calibrated probability stays if, on the same real out-of-sample days, it has a **lower Brier score and a lower expected calibration error** than the version 2 score. Otherwise it goes back to the maximum.

{{quote:CALIBRATION.md#Results > The one real-data run}}

Both conditions held and the calibrated probability was adopted. The check that the alarm itself was unchanged also passed: detections, delays, false alarms and alarm time are identical to version 2, episode by episode.

## The current version, from its backtest record

For the published version {{meta.model_version}}, the record gives a Brier score of {{backtest.current.metrics.brier|3}}, an expected calibration error of {{backtest.current.metrics.ece|3}}, a log loss of {{backtest.current.metrics.log_loss|3}} and a Brier skill of {{backtest.current.metrics.brier_skill|2}} against always predicting the observed frequency ({{backtest.current.metrics.base_rate|pct1}} of days are in the stress event). They differ slightly from the figures quoted above because the Slowdown change of Chapter 7 altered the model after that run.

{{table:reliability}}

{{figure:reliability}}

## What the run also showed

- The version 2 score was overconfident at the top and underconfident at the bottom: its days above 90% saw stress about two times in three, and its days under 10% saw it more than 5% of the time.
- The calibrated probability is now too cautious above 30%: days at 40 to 50% saw stress about three times in four. Those bins hold a few hundred days from a handful of crises, so part of this is noise, but the direction is consistent. In practice, when the probability passes 40%, it should be read as "stress more likely than not". The calibrator's weight rose from about 0.1 to about 0.3 as history accumulated, so the bias shrinks by itself.
- The regime is calmer: fewer regime switches per year, with the same alarm days.

## What this does not claim

{{backtest.current.metrics.n_episodes}} crises are few, and days are not independent: a month inside one crisis is about twenty correlated days, so the top bins of the reliability table rest on a handful of episodes and stay noisy. The scores say whether the probability is better than the earlier one, not that it is exact. The probability is about the frozen rule's episodes (a 10% fall or a volatility spike), not about losses or any other definition of a crisis.
