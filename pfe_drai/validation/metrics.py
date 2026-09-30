"""Detection latency, false positives, calibration and accuracy."""

import numpy as np
import pandas as pd

from .episodes import Episode, episode_mask


def stress_signal(p_stress: pd.Series, threshold: float, confirm_days: int) -> pd.Series:
    """True once P(stress) has stayed above the threshold for `confirm_days` days."""
    above = p_stress > threshold
    return above.rolling(confirm_days).sum() >= confirm_days


def latencies(signal: pd.Series, episodes: list[Episode], settings: dict) -> pd.DataFrame:
    cfg = settings["validation"]["episodes"]
    rows = []
    dates = signal.index
    for ep in episodes:
        if ep.start < dates[0]:
            continue
        pos = dates.searchsorted(ep.start)
        lo, hi = max(0, pos - cfg["lookback_days"]), min(len(dates), pos + cfg["detection_window_days"])
        window = signal.iloc[lo:hi]
        hits = np.flatnonzero(window.values)
        latency = int(lo + hits[0] - pos) if len(hits) else None
        rows.append(
            {
                "start": ep.start,
                "end": ep.end,
                "trigger": ep.trigger,
                "max_drawdown": ep.max_drawdown,
                "latency_days": latency,
                "detected": latency is not None,
            }
        )
    return pd.DataFrame(rows)


def false_positives_per_year(signal: pd.Series, episodes: list[Episode], settings: dict) -> float:
    cfg = settings["validation"]["episodes"]
    margin = pd.Timedelta(days=cfg["lookback_days"] * 7 / 5)
    onsets = signal & ~signal.shift(1, fill_value=False)
    widened = [Episode(e.start - margin, e.end, e.trigger, e.max_drawdown) for e in episodes]
    inside = episode_mask(signal.index, widened)
    false = int((onsets & ~inside).sum())
    years = (signal.index[-1] - signal.index[0]).days / 365.25
    return false / years if years else float("nan")


def brier(p: pd.Series, outcome: pd.Series) -> float:
    return float(((p - outcome.astype(float)) ** 2).mean())


def reliability(p: pd.Series, outcome: pd.Series, bins: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"p": p, "y": outcome.astype(float)})
    frame["bin"] = pd.cut(frame["p"], np.linspace(0, 1, bins + 1), include_lowest=True)
    out = frame.groupby("bin", observed=True).agg(predicted=("p", "mean"), observed=("y", "mean"), count=("y", "size"))
    return out.reset_index(drop=True)


def evaluate(
    probs: pd.DataFrame,
    equity: pd.Series,
    episodes: list[Episode],
    settings: dict,
    truth: pd.Series | None = None,
    rule: pd.Series | None = None,
) -> dict:
    cfg = settings["validation"]
    p_stress = probs["stress"]
    signal = stress_signal(p_stress, cfg["stress_probability_threshold"], cfg["confirm_days"])
    lat = latencies(signal, episodes, settings)
    in_episode = episode_mask(probs.index, episodes)
    detected = lat[lat["detected"]] if len(lat) else lat
    pred = probs.idxmax(axis=1)
    result = {
        "episodes": lat,
        "n_episodes": int(len(lat)),
        "detected": int(lat["detected"].sum()) if len(lat) else 0,
        "median_latency": float(detected["latency_days"].median()) if len(detected) else float("nan"),
        "false_positives_per_year": false_positives_per_year(signal, episodes, settings),
        "brier_stress": brier(p_stress, in_episode),
        "reliability": reliability(p_stress, in_episode),
        "switches_per_year": float((pred != pred.shift()).sum() / max((probs.index[-1] - probs.index[0]).days / 365.25, 1e-9)),
    }
    if truth is not None:
        result["accuracy_truth"] = float((pred == truth.reindex(pred.index)).mean())
    if rule is not None:
        result["agreement_rule"] = float((pred == rule.reindex(pred.index)).mean())
    targets = cfg["targets"]
    result["meets_latency_target"] = bool(result["median_latency"] <= targets["max_median_latency_days"])
    result["meets_fp_target"] = bool(result["false_positives_per_year"] <= targets["max_false_positives_per_year"])
    return result
