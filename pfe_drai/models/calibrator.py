"""Calibrated P(stress): a small logistic regression on the models' stress probabilities (docs/CALIBRATION.md).

v2 shows the highest of three stress probabilities (jump, gbm, onset). The jump model swings
between 0% and 100%, and the highest of several numbers is a detector score, not a probability:
on simulated data, days at "90%" were followed by stress far less than 9 times in 10. Here

    P(stress) = sigmoid(b + w * logit(score))

learns, on past days only, how often stress followed each score: Platt scaling, two numbers.
With `inputs: sources` there is one weight per source instead (a stacked logistic). Few numbers on
purpose: the real history holds about a dozen crises, and a flexible calibrator (isotonic,
boosting) would learn them by heart. Weights are kept at zero or above, so a higher score can
never lower the probability.

The calibrator must learn from out-of-sample scores: an in-sample prediction is too confident.
The sources therefore start predicting `warmup_days` into the data (earlier than the backtest,
on the same refit dates), and at each refit the calibrator learns from the past out-of-sample
scores only, the last `target_horizon_days` days dropped (their outcome is not known yet).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit


def logits(p: pd.DataFrame, clip: float) -> pd.DataFrame:
    return pd.DataFrame(logit(p.clip(clip, 1 - clip).to_numpy()), index=p.index, columns=p.columns)


def fit_logistic(x: np.ndarray, y: np.ndarray, l2: float) -> tuple[float, np.ndarray]:
    """Logistic regression with non-negative weights and an L2 penalty (l2 / n on the weights)."""
    n, k = x.shape
    rate = float(np.clip(y.mean(), 1e-3, 1 - 1e-3))

    def loss(theta):
        z = theta[0] + x @ theta[1:]
        p = expit(z)
        value = np.mean(np.logaddexp(0, z) - y * z) + 0.5 * l2 * theta[1:] @ theta[1:] / n
        grad = np.r_[np.mean(p - y), x.T @ (p - y) / n + l2 * theta[1:] / n]
        return value, grad

    start = np.r_[np.log(rate / (1 - rate)), np.zeros(k)]
    res = minimize(loss, start, jac=True, method="L-BFGS-B", bounds=[(None, None)] + [(0.0, None)] * k)
    return float(res.x[0]), res.x[1:]


@dataclass
class Calibrated:
    stress: pd.Series  # calibrated P(stress)
    calibrated: pd.Series  # False on days that fell back to the highest source (too little history)
    fits: pd.DataFrame  # one row per refit: first day predicted, intercept, weights, training days and events


def calibrate_walk_forward(sources: dict[str, pd.Series], event: pd.Series, settings: dict, start: pd.Timestamp) -> Calibrated:
    """Calibrated P(stress) from `start` on, refit every `refit_every_days` on the past only.

    `sources` are out-of-sample stress probabilities that begin before `start`; `event` is the
    stress event (validation.calibration.stress_event), NaN where not known yet.
    """
    cfg = settings["models"]["combined"]["stack"]
    h = settings["validation"]["calibration"]["target_horizon_days"]
    p = pd.DataFrame(sources).dropna()
    x = logits(p, cfg["clip"]) if cfg.get("transform", "logit") == "logit" else p
    y = event.reindex(p.index)
    first = p.index.searchsorted(start)
    if first >= len(p):
        raise ValueError("No day to predict after the start of the calibrated period")
    stress, calibrated, fits = [], [], []
    for cut in range(first, len(p), cfg["refit_every_days"]):
        end = min(cut + cfg["refit_every_days"], len(p))
        # Outcome of day t is known on day t + h: the last h training days are left out (purging).
        train = y.iloc[: max(cut - h, 0)].dropna()
        events = int(train.sum())
        block = slice(cut, end)
        row = {"first_day": p.index[cut], "train_days": len(train), "event_days": events}
        if events < cfg["min_event_days"] or events == len(train):
            # Not enough stress days in the past to learn from: highest source, as v2.
            stress.append(p.iloc[block].max(axis=1))
            calibrated.append(pd.Series(False, index=p.index[block]))
            fits.append({**row, "intercept": np.nan, **dict.fromkeys(p.columns, np.nan)})
            continue
        b, w = fit_logistic(x.loc[train.index].to_numpy(), train.to_numpy(), cfg["l2"])
        stress.append(pd.Series(expit(b + x.iloc[block].to_numpy() @ w), index=p.index[block]))
        calibrated.append(pd.Series(True, index=p.index[block]))
        fits.append({**row, "intercept": b, **dict(zip(p.columns, w, strict=True))})
    return Calibrated(pd.concat(stress).rename("stress"), pd.concat(calibrated).rename("calibrated"), pd.DataFrame(fits))
