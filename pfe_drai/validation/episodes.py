"""Dates the start of each stress episode with a rule fixed before any backtest.

A stress episode starts on the first day when either
- the equity drawdown from its 252-day high falls below `drawdown_threshold`, or
- 21-day realised volatility rises above its expanding `vol_quantile` percentile,
and ends when the drawdown recovers above `recovery_drawdown` or after
`max_duration_days`. A start needs a fresh crossing of either line, at least
`min_gap_days` after the previous start.
"""

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


def find_episodes(equity: pd.Series, settings: dict) -> list[Episode]:
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
    episodes: list[Episode] = []
    last_start = None
    for i in np.flatnonzero((dd_cross | vol_cross).values):
        start = dates[i]
        if last_start is not None and i - last_start < cfg["min_gap_days"]:
            continue
        stop = min(i + cfg["max_duration_days"], len(dates) - 1)
        recovered = np.flatnonzero((dd.iloc[i + 5 : stop + 1] > cfg["recovery_drawdown"]).values)
        j = i + 5 + recovered[0] if len(recovered) else stop
        j = min(j, len(dates) - 1)
        trigger = "drawdown" if dd_cross.iloc[i] else "volatility"
        episodes.append(Episode(start, dates[j], trigger, float(dd.iloc[i : j + 1].min())))
        last_start = i
    return episodes


def episode_mask(index: pd.DatetimeIndex, episodes: list[Episode]) -> pd.Series:
    mask = pd.Series(False, index=index)
    for ep in episodes:
        mask.loc[ep.start : ep.end] = True
    return mask
