"""Alert rules computed over the whole history (so the app can show past alerts too)."""

import pandas as pd


def compute_alerts(
    probs: pd.DataFrame,
    scores: pd.DataFrame,
    settings: dict,
    early: pd.DataFrame | None = None,
    score: pd.Series | None = None,
) -> pd.DataFrame:
    """`score`: what the stress alarm reads (the detector score of `combined`), default P(stress)."""
    cfg = settings["alerts"]
    confirm = settings["validation"]["confirm_days"]
    rows = []

    regime = probs.idxmax(axis=1)
    codes = pd.Series(pd.factorize(regime)[0], index=regime.index, dtype=float)
    held = codes.rolling(confirm).std().fillna(1.0).eq(0.0)  # same regime for `confirm` days
    stable = regime.where(held).ffill()
    changed = stable.ne(stable.shift()) & stable.shift().notna()
    for date in stable.index[changed]:
        rows.append(
            {
                "date": date,
                "type": "regime_change",
                "severity": "high",
                "old": stable.shift().loc[date],
                "new": stable.loc[date],
                "value": None,
            }
        )

    p = probs["stress"] if score is None else score
    up = (p > cfg["stress_probability"]) & (p.shift() <= cfg["stress_probability"])
    for date in p.index[up]:
        rows.append(
            {
                "date": date,
                "type": "stress_probability",
                "severity": "high",
                "old": None,
                "new": None,
                "value": float(p.loc[date]),
            }
        )

    if early is not None and "stress" in early:
        e = early["stress"]
        up = (e > cfg["early_warning_probability"]) & (e.shift() <= cfg["early_warning_probability"])
        for date in e.index[up]:
            rows.append(
                {
                    "date": date,
                    "type": "early_warning",
                    "severity": "medium",
                    "old": None,
                    "new": None,
                    "value": float(e.loc[date]),
                }
            )

    jumps = scores.diff(5)
    for dim in scores.columns:
        big = (jumps[dim].abs() > cfg["score_jump"]) & (jumps[dim].abs().shift() <= cfg["score_jump"])
        for date in jumps.index[big]:
            rows.append(
                {
                    "date": date,
                    "type": "score_jump",
                    "severity": "low",
                    "old": dim,
                    "new": None,
                    "value": float(jumps.loc[date, dim]),
                }
            )

    frame = pd.DataFrame(rows, columns=["date", "type", "severity", "old", "new", "value"])
    return frame.sort_values("date", ascending=False).reset_index(drop=True)
