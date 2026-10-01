"""Is P(stress) a probability? Calibration of the stress probability against what followed.

"Calibrated" means: on the days the model said about 70%, stress followed about 70% of the time.
The event is fixed in `validation.calibration` (docs/CALIBRATION.md): the day is inside an episode
of the frozen rule, or one starts within `target_horizon_days` business days. That is the event
the detector is scored on (an early signal up to a week before the dated start counts).

Scores, lower is better for the first three:
- Brier: mean squared gap between the probability and the outcome (0 or 1);
- log loss: penalises confident mistakes most (a 99% call that does not happen);
- ECE (expected calibration error): days grouped by predicted probability in 10 bins, the gap
  between the average prediction and the observed frequency in each bin, weighted by its days;
- Brier skill: 1 - Brier / Brier of always saying the observed frequency (above 0 = useful).
"""

import numpy as np
import pandas as pd

from .episodes import Episode, onset_target

#: Probabilities are clipped to this range for the log loss, so one 0% or 100% call stays finite.
EPS = 1e-4


def stress_event(index: pd.DatetimeIndex, episodes: list[Episode], settings: dict) -> pd.Series:
    """1 when the day is inside an episode or one starts within the horizon; NaN while not known yet."""
    h = settings["validation"]["calibration"]["target_horizon_days"]
    return onset_target(index, episodes, h).rename("stress_event")


def reliability(p: pd.Series, outcome: pd.Series, bins: int = 10) -> pd.DataFrame:
    """One row per probability bin with days: mean predicted, observed frequency, number of days."""
    frame = pd.DataFrame({"p": p, "y": outcome.astype(float)}).dropna()
    edges = np.linspace(0, 1, bins + 1)
    frame["bin"] = np.clip(np.digitize(frame["p"], edges[1:-1], right=True), 0, bins - 1)
    out = frame.groupby("bin").agg(predicted=("p", "mean"), observed=("y", "mean"), count=("y", "size"))
    out["low"], out["high"] = edges[out.index], edges[out.index + 1]
    return out.reset_index(drop=True)[["low", "high", "predicted", "observed", "count"]]


def calibration_scores(p: pd.Series, outcome: pd.Series, bins: int = 10) -> dict:
    """Brier, log loss, ECE, Brier skill and the reliability table, on the days where the outcome is known."""
    frame = pd.DataFrame({"p": p, "y": outcome.astype(float)}).dropna()
    if frame.empty:
        nan = float("nan")
        empty = {k: nan for k in ("brier", "log_loss", "ece", "brier_skill", "base_rate", "mean_p")}
        return {"n_days": 0, **empty, "reliability": reliability(p.iloc[:0], outcome.iloc[:0], bins)}
    q, y = frame["p"].clip(EPS, 1 - EPS), frame["y"]
    rel = reliability(frame["p"], y, bins)
    brier = float(((frame["p"] - y) ** 2).mean())
    base = float(y.mean())
    reference = base * (1 - base)
    return {
        "n_days": int(len(frame)),
        "brier": brier,
        "log_loss": float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean()),
        "ece": float((rel["count"] * (rel["predicted"] - rel["observed"]).abs()).sum() / rel["count"].sum()),
        "brier_skill": float(1 - brier / reference) if reference > 0 else float("nan"),
        "base_rate": base,
        "mean_p": float(frame["p"].mean()),
        "reliability": rel,
    }


def calibration_report(p_stress: pd.Series, episodes: list[Episode], settings: dict, until=None) -> dict:
    """Calibration of `p_stress` up to `until` (default: every day whose outcome is already known)."""
    p = p_stress if until is None else p_stress.loc[:until]
    event = stress_event(p_stress.index, episodes, settings).reindex(p.index)
    if until is not None:
        # On a past date, the outcome of its last `horizon` days was not known yet: leave them out,
        # so the score shown for a date only uses what was known on that date.
        h = settings["validation"]["calibration"]["target_horizon_days"]
        event.iloc[max(len(event) - h, 0) :] = np.nan
    return calibration_scores(p, event, settings["validation"]["calibration"].get("bins", 10))


def json_number(value):
    """Rounded float, None for NaN (JSON has no NaN)."""
    if isinstance(value, float):
        return None if value != value else round(value, 4)
    return value


def to_json(report: dict) -> dict:
    """Plain numbers for the API and the daily track record."""
    rel = report["reliability"]
    out = {k: json_number(v) for k, v in report.items() if k != "reliability"}
    out["reliability"] = [
        {
            "low": round(r.low, 2),
            "high": round(r.high, 2),
            "predicted": round(r.predicted, 4),
            "observed": round(r.observed, 4),
            "days": int(r.count),
        }
        for r in rel.itertuples()
    ]
    return out
