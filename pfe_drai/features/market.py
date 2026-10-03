"""Fast market inputs for the stress-onset detector (docs/DETECTION_V2.md).

The dimension scores use expanding z-scores and quarter-long changes: they suit regimes but
move slowly, and one extreme year (2008) shrinks every later reading. These inputs are daily,
in their own units (returns, annualised vol, VIX points, ratios), and use one week to one
month of data, so the same value means the same thing in 1998, 2011 or 2025.

Two input sets are pre-registered:
- `market`:        equity and VIX only (SPY since 1993, VIX since 1990);
- `market_credit`: plus investment-grade credit against Treasuries (LQD/IEF, 2002+).
  LQD rather than HYG because HYG starts in 2007: one series keeps one meaning everywhere.

Two more are read only by the challengers (docs/CHALLENGERS.md), never by the published model:
- `market_vix_term`: plus the VIX over the 3-month VIX (FRED VXVCLS, from Dec 2007);
- `market_hy_fund`:  plus a high-yield fund against a Treasury fund (VWEHX/VFITX, from 1991).
"""

import numpy as np
import pandas as pd

from .build import align

MARKET = [
    "drawdown",  # from the 252-day high (negative)
    "return_5d",
    "return_10d",
    "return_21d",
    "vol_5d",  # realised vol, annualised
    "vol_10d",
    "vol_21d",
    "vol_to_limit",  # 21-day vol / the episode rule's volatility line (1 = on the line)
    "vix",
    "vix_change_5d",  # log change
    "vix_to_3m_mean",
]
CREDIT = ["credit_5d", "credit_21d"]  # IG bonds lagging Treasuries (positive = stress)
# Challengers only (docs/CHALLENGERS.md): never read by the published model. NaN when their series are missing.
VIX_TERM = ["vix_term", "vix_term_change_5d"]  # VIX over the 3-month VIX (above 1 = inverted, panic)
HY_FUND = ["hy_credit_5d", "hy_credit_21d"]  # high-yield fund lagging the Treasury fund (positive = stress)
INPUT_SETS = {
    "market": MARKET,
    "market_credit": MARKET + CREDIT,
    "market_vix_term": MARKET + VIX_TERM,
    "market_hy_fund": MARKET + HY_FUND,
}
NEEDED = {
    "market": ["equity", "vix"],
    "market_credit": ["equity", "vix", "ig_bond", "treasury"],
    "market_vix_term": ["equity", "vix", "vix3m"],
    "market_hy_fund": ["equity", "vix", "hy_fund", "treasury_fund"],
}
EXTRA = VIX_TERM + HY_FUND


def market_inputs(prices: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """Every input of both sets, computed on past data only. Credit is NaN when LQD/IEF are missing."""
    rule = settings["validation"]["episodes"]
    eq = prices["equity"]
    log_eq = np.log(eq)
    ret = log_eq.diff()
    f = pd.DataFrame(index=prices.index)
    f["drawdown"] = eq / eq.rolling(252, min_periods=21).max() - 1
    for n in (5, 10, 21):
        f[f"return_{n}d"] = log_eq.diff(n)
    for n in (5, 10, 21):
        f[f"vol_{n}d"] = ret.rolling(n).std() * np.sqrt(252)
    # Same definition as the frozen episode rule's volatility line (validation/episodes.py).
    vol = ret.rolling(rule["vol_window"]).std()
    f["vol_to_limit"] = vol / vol.expanding(252).quantile(rule["vol_quantile"]).shift(1)
    vix = prices["vix"]
    f["vix"] = vix
    f["vix_change_5d"] = np.log(vix).diff(5)
    f["vix_to_3m_mean"] = vix / vix.rolling(63).mean()
    if {"ig_bond", "treasury"} <= set(prices.columns):
        credit = np.log(prices["ig_bond"] / prices["treasury"])
        f["credit_5d"] = -credit.diff(5)
        f["credit_21d"] = -credit.diff(21)
    else:
        f["credit_5d"] = f["credit_21d"] = np.nan
    if "vix3m" in prices:
        term = vix / prices["vix3m"]
        f["vix_term"] = term
        f["vix_term_change_5d"] = term.diff(5)
    else:
        f["vix_term"] = f["vix_term_change_5d"] = np.nan
    if {"hy_fund", "treasury_fund"} <= set(prices.columns):
        hy = np.log(prices["hy_fund"] / prices["treasury_fund"])
        f["hy_credit_5d"] = -hy.diff(5)
        f["hy_credit_21d"] = -hy.diff(21)
    else:
        f["hy_credit_5d"] = f["hy_credit_21d"] = np.nan
    return f[MARKET + CREDIT + EXTRA]


def market_frame(raw: dict[str, pd.Series], settings: dict, release_dated: set[str] = frozenset()) -> pd.DataFrame:
    """Market inputs on business days, from the start of the price history (not of the z-scores)."""
    names = [n for n in ("equity", "vix", "ig_bond", "treasury", "vix3m", "hy_fund", "treasury_fund") if n in raw]
    prices = align({n: raw[n] for n in names}, {}, release_dated)
    return market_inputs(prices, settings)
