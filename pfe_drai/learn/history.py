"""History lessons: each episode's numbers and the past episodes that look most like a given day.

Computed from the same FRED series as the rest of the Learn pages (today's vintages, so revised data).
"""

import numpy as np
import pandas as pd

from .data import _asof

# What "looks like today" means: the Fed's stance, inflation, jobs and the curve, plus the Fed's last-year move.
ANALOGUE_FEATURES = ("policy_rate", "core_pce_yoy", "unrate", "curve_10y_3m", "fed_last_year")


def _window(values: dict, name: str, start, end) -> pd.Series:
    s = values.get(name)
    return pd.Series(dtype=float) if s is None or s.empty else s.loc[start:end].dropna()


def numbers(values: dict, episode: dict, recessions: pd.Series | None = None) -> dict:
    """Key figures inside the episode window: the policy rate at start, high, low and end; the peak of
    core inflation, unemployment and VIX; the oil price range; months of recession (NBER)."""
    start, end = pd.Timestamp(episode["start"]), pd.Timestamp(episode["end"])
    out = {}
    rate = _window(values, "policy_rate", start, end)
    if not rate.empty:
        out.update(rate_start=float(rate.iloc[0]), rate_high=float(rate.max()), rate_low=float(rate.min()))
        out["rate_end"] = float(rate.iloc[-1])
    for name, key, fn in (
        ("core_pce_yoy", "inflation_high", "max"),
        ("unrate", "unemployment_low", "min"),
        ("unrate", "unemployment_high", "max"),
        ("vix", "vix_high", "max"),
        ("oil", "oil_low", "min"),
        ("oil", "oil_high", "max"),
        ("curve_10y_3m", "curve_low", "min"),
    ):
        s = _window(values, name, start, end)
        if not s.empty:
            out[key] = float(getattr(s, fn)())
    if recessions is not None and not recessions.empty:
        rec = recessions.loc[start:end]
        out["recession_months"] = int((rec.resample("ME").max() > 0.5).sum()) if not rec.empty else 0
    return out


def snapshot(values: dict, date) -> pd.Series:
    """The analogue features on `date` (latest value known then)."""
    date = pd.Timestamp(date)
    row = {}
    for name in ANALOGUE_FEATURES:
        if name == "fed_last_year":
            s = values.get("policy_rate")
            now, before = _asof(s, [date, date - pd.DateOffset(months=12)]) if s is not None else (np.nan, np.nan)
            row[name] = now - before
        else:
            s = values.get(name)
            row[name] = float(_asof(s, [date])[0]) if s is not None and not s.empty else np.nan
    return pd.Series(row)


def _scale(values: dict, end) -> pd.Series:
    """Typical spread of each feature (std over month-ends since 1985), so no feature dominates the distance."""
    months = pd.date_range("1985-01-31", pd.Timestamp(end), freq="ME")
    frame = pd.DataFrame([snapshot(values, m) for m in months[::3]])
    return frame.std().replace(0, 1).fillna(1)


def analogues(values: dict, episodes: list[dict], date, top: int = 3) -> list[dict]:
    """Episodes whose starting conditions are closest to `date`, nearest first.

    Only episodes that had started by `date` are compared (no look-ahead in the time machine), and the
    episode containing `date`, if any, is left out: it would match itself.
    """
    date = pd.Timestamp(date)
    today = snapshot(values, date)
    if today.isna().sum() > 1:
        return []
    scale = _scale(values, date)
    rows = []
    for ep in episodes:
        start, end = pd.Timestamp(ep["start"]), pd.Timestamp(ep["end"])
        if start > date or start <= date <= end:
            continue
        then = snapshot(values, start)
        both = today.notna() & then.notna()
        if both.sum() < 3:
            continue
        z = ((today[both] - then[both]) / scale[both]) ** 2
        distance = float(np.sqrt(z.mean()))
        rows.append({"id": ep["id"], "distance": distance, "then": then.to_dict(), "today": today.to_dict()})
    rows.sort(key=lambda r: r["distance"])
    return rows[:top]


def regime_mix(regimes: pd.Series | None, start, end) -> dict[str, float]:
    """Share of days in each of our regimes inside the window (empty when the model's history does not cover it)."""
    if regimes is None or regimes.empty:
        return {}
    part = regimes.loc[pd.Timestamp(start) : pd.Timestamp(end)].dropna()
    if part.empty:
        return {}
    return {str(k): float(v) for k, v in part.value_counts(normalize=True).items()}
