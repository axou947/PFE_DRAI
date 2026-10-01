"""Dates the start of each stress episode with a rule fixed before any backtest.

A stress episode starts on the first day when either
- the equity drawdown from its 252-day high falls below `drawdown_threshold`, or
- 21-day realised volatility rises above its expanding `vol_quantile` percentile,
and ends when the drawdown recovers above `recovery_drawdown` or after
`max_duration_days`. A start needs a fresh crossing of either line, at least
`min_gap_days` after the end of the previous episode, and the drawdown must have
recovered above `recovery_drawdown` since then (re-arming). Re-arming keeps a market
that never recovered (e.g. 2009, early 2023) from opening a new episode, while two
distinct falls a few months apart (2015 then 2016, March then May 2022) stay two episodes.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Episode:
    start: pd.Timestamp
    end: pd.Timestamp
    trigger: str
    max_drawdown: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"], d["end"] = self.start.date().isoformat(), self.end.date().isoformat()
        return d


# Parameters of the episode rule. Changing any of them changes every latency.
RULE_KEYS = (
    "drawdown_threshold",
    "vol_window",
    "vol_quantile",
    "min_gap_days",
    "recovery_drawdown",
    "max_duration_days",
    "detection_window_days",
    "lookback_days",
)


def rule_fingerprint(settings: dict) -> str:
    """SHA-256 of the episode rule parameters (published with every track record entry)."""
    cfg = settings["validation"]["episodes"]
    rule = {key: cfg[key] for key in RULE_KEYS}
    return hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()


def check_frozen(settings: dict) -> None:
    """Refuse to date episodes with a rule that differs from the frozen one.

    The rule is frozen in validation.episodes.frozen (sha256 + date) before any backtest,
    so a latency can never come from a rule tuned after looking at the results.
    """
    frozen = settings["validation"]["episodes"].get("frozen") or {}
    expected = frozen.get("sha256")
    if expected and rule_fingerprint(settings) != expected:
        raise ValueError(
            f"The episode rule was frozen on {frozen.get('date')} and its parameters have changed. "
            "Restore them, or record a new version (new sha256 and date) and publish why."
        )


def find_episodes(equity: pd.Series, settings: dict) -> list[Episode]:
    check_frozen(settings)
    cfg = settings["validation"]["episodes"]
    dd = equity / equity.rolling(252, min_periods=21).max() - 1
    vol = np.log(equity).diff().rolling(cfg["vol_window"]).std()
    vol_limit = vol.expanding(252).quantile(cfg["vol_quantile"]).shift(1)
    dd_hit = dd <= cfg["drawdown_threshold"]
    vol_hit = vol > vol_limit
    # An episode starts on a fresh crossing, not on every day spent below the line.
    dd_cross = dd_hit & ~dd_hit.shift(1, fill_value=False)
    vol_cross = vol_hit & ~vol_hit.shift(1, fill_value=False)
    dates = equity.index
    recovered_days = (dd > cfg["recovery_drawdown"]).values
    episodes: list[Episode] = []
    last_end = None
    for i in np.flatnonzero((dd_cross | vol_cross).values):
        start = dates[i]
        if last_end is not None:
            if i - last_end < cfg["min_gap_days"] or not recovered_days[last_end + 1 : i].any():
                continue
        stop = min(i + cfg["max_duration_days"], len(dates) - 1)
        recovered = np.flatnonzero((dd.iloc[i + 5 : stop + 1] > cfg["recovery_drawdown"]).values)
        j = i + 5 + recovered[0] if len(recovered) else stop
        j = min(j, len(dates) - 1)
        trigger = "drawdown" if dd_cross.iloc[i] else "volatility"
        episodes.append(Episode(start, dates[j], trigger, float(dd.iloc[i : j + 1].min())))
        last_end = j
    return episodes


def episode_mask(index: pd.DatetimeIndex, episodes: list[Episode]) -> pd.Series:
    mask = pd.Series(False, index=index)
    for ep in episodes:
        mask.loc[ep.start : ep.end] = True
    return mask
