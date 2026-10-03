"""Simulated market data with known regimes.

Used until real APIs are plugged in. The simulator follows a regime path that mimics
the main post-2000 crises, fills the gaps with a random but persistent chain, then
generates every catalog series from regime-dependent dynamics. Because the true regime
is known, it also lets us measure detection latency against the ground truth.
"""

import numpy as np
import pandas as pd

from .base import DataProvider, register

# Scripted episodes that mirror real history, so charts and scenarios line up.
SCRIPT = [
    ("2000-09-01", "2001-09-07", "slowdown"),
    ("2001-09-10", "2001-10-12", "stress"),
    ("2001-10-15", "2002-06-14", "slowdown"),
    ("2002-06-17", "2002-10-11", "stress"),
    ("2005-09-01", "2006-07-31", "overheating"),
    ("2007-08-01", "2008-08-29", "slowdown"),
    ("2008-09-01", "2009-03-31", "stress"),
    ("2009-04-01", "2009-09-30", "slowdown"),
    ("2011-07-25", "2011-10-14", "stress"),
    ("2013-05-20", "2013-07-15", "overheating"),
    ("2015-08-17", "2015-09-30", "stress"),
    ("2015-10-01", "2016-01-08", "slowdown"),
    ("2016-01-11", "2016-02-19", "stress"),
    ("2018-02-01", "2018-02-23", "stress"),
    ("2018-10-04", "2018-12-31", "stress"),
    ("2020-02-21", "2020-04-17", "stress"),
    ("2020-04-20", "2020-07-31", "slowdown"),
    ("2021-06-01", "2022-04-29", "overheating"),
    ("2022-05-02", "2022-06-30", "stress"),
    ("2022-07-01", "2022-10-31", "overheating"),
    ("2025-04-01", "2025-04-30", "stress"),
]

REGIMES = ["expansion", "overheating", "slowdown", "stress"]

# Regime-dependent targets. Annualised equity drift and vol, then levels in %.
PARAMS = {
    #              eq_mu  eq_vol  slope  hy_spread  cpi_yoy  ip_yoy  claims  rate_drift
    "expansion": (0.20, 0.12, 1.30, 3.5, 2.2, 3.0, 230_000, 0.002),
    "overheating": (0.06, 0.17, 0.10, 3.9, 4.8, 2.0, 215_000, 0.012),
    "slowdown": (-0.02, 0.21, 0.80, 5.5, 1.8, -1.0, 320_000, -0.008),
    "stress": (-0.70, 0.45, 1.00, 9.5, 1.2, -6.0, 520_000, -0.020),
}


# Unemployment rate target (%) by regime. Drawn after every other series, so adding it left them unchanged.
UNRATE = {"expansion": 4.2, "overheating": 3.8, "slowdown": 5.8, "stress": 6.5}


def _regime_path(index: pd.DatetimeIndex, rng: np.random.Generator) -> pd.Series:
    path = pd.Series(index=index, dtype=object)
    for start, end, regime in SCRIPT:
        path.loc[start:end] = regime
    calm = ["expansion", "overheating", "slowdown"]
    weights = np.array([0.7, 0.15, 0.15])
    state = "expansion"
    for i, value in enumerate(path.values):
        if isinstance(value, str):
            state = "expansion" if value == "stress" else value
            continue
        if rng.random() < 1 / 160:  # mean calm spell of about 8 months
            state = rng.choice(calm, p=weights)
        path.iloc[i] = state
    return path


def _ou(target: np.ndarray, speed: float, noise: float, start: float, rng) -> np.ndarray:
    out = np.empty(len(target))
    x = start
    for i, tgt in enumerate(target):
        x = x + speed * (tgt - x) + noise * rng.standard_normal()
        out[i] = x
    return out


def simulate(start: str, end: str, seed: int = 42) -> tuple[dict[str, pd.Series], pd.Series]:
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(start, end)
    regimes = _regime_path(index, rng)
    p = np.array([PARAMS[r] for r in regimes])
    eq_mu, eq_vol, slope_t, hy_t, cpi_t, ip_t, claims_t, rate_drift = p.T
    n = len(index)

    # Volatility adjusts faster when stress starts than when it fades.
    vol = np.empty(n)
    v = eq_vol[0]
    for i in range(n):
        speed = 0.25 if eq_vol[i] > v else 0.05
        v = v + speed * (eq_vol[i] - v)
        vol[i] = v
    daily_vol = vol / np.sqrt(252)
    eq_ret = eq_mu / 252 + daily_vol * rng.standard_t(5, n) * np.sqrt(3 / 5)
    equity = 1400 * np.exp(np.cumsum(eq_ret))
    vix = np.clip(_ou(vol * 100 * 1.15, 0.3, 1.0, 20, rng), 9, 90)

    # Rates: 2-year yield drifts with the regime; the curve slope follows its own target.
    us2y = np.empty(n)
    y = 6.0
    for i in range(n):
        y = float(np.clip(y + rate_drift[i] + 0.04 * rng.standard_normal(), 0.05, 7.0))
        us2y[i] = y
    slope = _ou(slope_t, 0.01, 0.03, 0.8, rng)
    us10y = np.clip(us2y + slope, 0.3, 9.0)

    hy_spread = np.clip(_ou(hy_t, 0.03, 0.08, 4.0, rng), 2.0, 22.0)
    ig_spread = 0.3 * hy_spread
    d10 = np.diff(us10y, prepend=us10y[0]) / 100
    treasury_ret = us10y / 100 / 252 - 7.5 * d10
    ig_ret = (us10y + ig_spread) / 100 / 252 - 8.0 * (d10 + np.diff(ig_spread, prepend=ig_spread[0]) / 100)
    hy_ret = (us10y + hy_spread) / 100 / 252 - 4.0 * (d10 + np.diff(hy_spread, prepend=hy_spread[0]) / 100)
    treasury = 100 * np.exp(np.cumsum(treasury_ret))
    ig_bond = 100 * np.exp(np.cumsum(ig_ret))
    hy_bond = 100 * np.exp(np.cumsum(hy_ret))

    cpi_yoy = _ou(cpi_t, 0.006, 0.02, 3.0, rng)
    breakeven = np.clip(_ou(0.7 * cpi_yoy + 0.6, 0.05, 0.03, 2.3, rng), -0.5, 4.0)
    ip_yoy = _ou(ip_t, 0.012, 0.05, 3.0, rng)
    claims = np.clip(_ou(claims_t, 0.02, 4000, 280_000, rng), 150_000, 3_000_000)
    # Unemployment moves slowly: it follows its regime target over months (Sahm rule, docs/SAHM_HY.md).
    unrate = np.clip(_ou(np.array([UNRATE[r] for r in regimes]), 0.006, 0.01, 4.5, rng), 2.5, 15.0)

    cpi_index = 170 * np.exp(np.cumsum(cpi_yoy / 100 / 252))
    ip_index = 90 * np.exp(np.cumsum(ip_yoy / 100 / 252))

    def daily(values):
        return pd.Series(values, index=index)

    def sample(values, freq):
        return daily(values).resample(freq).last().dropna()

    data = {
        "equity": daily(equity),
        "vix": daily(vix),
        "hy_bond": daily(hy_bond),
        "ig_bond": daily(ig_bond),
        "treasury": daily(treasury),
        "us10y": daily(us10y),
        "us2y": daily(us2y),
        "breakeven10": daily(breakeven),
        "claims": sample(claims, "W-SAT"),
        "indpro": sample(ip_index, "ME"),
        "cpi": sample(cpi_index, "ME"),
        "unrate": sample(unrate, "ME"),
        # Challengers (docs/CHALLENGERS.md), no random draw: the 3-month VIX is a smoother, slightly higher version of
        # the VIX (it sits above it in calm markets and below it in a spike), and the two mutual funds read like the
        # high-yield bond and Treasury series.
        "vix3m": daily(0.4 * vix + 0.6 * pd.Series(vix).ewm(halflife=42).mean().to_numpy() + 1.5),
        "hy_fund": daily(hy_bond),
        "treasury_fund": daily(treasury),
    }
    return data, regimes.rename("truth")


@register
class SyntheticProvider(DataProvider):
    """Simulated data. Set data.provider: synthetic in config/settings.yaml."""

    name = "synthetic"
    is_live = False

    def __init__(self, settings: dict):
        super().__init__(settings)
        self._truth: pd.Series | None = None

    def fetch(self, start, end):
        data, self._truth = simulate(str(start.date()), str(end.date()), self.settings["data"]["seed"])
        return data

    def truth(self):
        return self._truth
