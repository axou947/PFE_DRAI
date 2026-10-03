"""Helpers shared by the region providers (euro area, UK, Japan, emerging markets).

None of the region sources exposes first releases through a public API, so their series are dated by
the day they could have been public: the end of the reference period plus a conservative release lag.
"""

import numpy as np
import pandas as pd


def realised_vol_percent(equity: pd.Series, window: int = 21) -> pd.Series:
    """Annualised realised volatility of daily log returns, in % (the stand-in for an implied volatility index)."""
    return (np.log(equity).diff().rolling(window).std() * np.sqrt(252) * 100).dropna()


def check_fresh(name: str, series: pd.Series, end, max_stale_days: int) -> None:
    """Refuse a series that stopped updating: a stale last value would be carried forward as if it were current.

    Statistical offices re-base and replace datasets (Eurostat's HICP in 2026, the OECD's copy of Japan's CPI
    in 2021), so an old code can keep answering with a series that ends months or years ago.
    """
    if series.empty or (pd.Timestamp(end) - series.index[-1]).days > max_stale_days:
        last = series.index[-1].date() if len(series) else "no data"
        raise ValueError(f"Series '{name}' is stale: its last reference period is {last}. Its source code needs updating.")


def release_dated(series: pd.Series, lag_days: int, monthly: bool) -> pd.Series:
    """Date a series by the day it was public: end of its period (months) plus a conservative lag."""
    out = series.copy()
    out.index = (out.index + pd.offsets.MonthEnd(0) if monthly else out.index) + pd.Timedelta(days=lag_days)
    return out[~out.index.duplicated(keep="last")].sort_index()
