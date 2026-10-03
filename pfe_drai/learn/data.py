"""US series for the Learn pages (docs/LEARN.md): download, cache, simulate and transform.

Display only. Nothing here feeds the regime model: the pipeline's catalog (data/catalog.py) is untouched,
so the settings fingerprint, the backtests and the published track record do not change.

Values are today's FRED vintages (revised), which is right for "where the US is today" and for teaching
history, but not point-in-time: the Fed odds say so where it matters (base rates).
"""

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

from ..config import resolve


@dataclass(frozen=True)
class Indicator:
    id: str
    transform: str
    series: tuple[str, ...]
    unit: str
    scale: float = 1.0
    ref: float | None = None


def _read(settings: dict, key: str) -> dict:
    return yaml.safe_load(resolve(settings["learn"][key]).read_text(encoding="utf-8"))


def series_catalog(settings: dict) -> dict[str, dict]:
    """{FRED id: {freq, owner}}."""
    return _read(settings, "indicators")["series"]


def load_indicators(settings: dict) -> dict[str, Indicator]:
    out = {}
    for name, spec in _read(settings, "indicators")["indicators"].items():
        series = spec.get("series", ())
        out[name] = Indicator(
            id=name,
            transform=spec.get("transform", "level"),
            series=(series,) if isinstance(series, str) else tuple(series),
            unit=spec["unit"],
            scale=float(spec.get("scale", 1.0)),
            ref=spec.get("ref"),
        )
    return out


def load_meetings(settings: dict) -> pd.DataFrame:
    """FOMC decision days: columns date, sep (with projections)."""
    rows = _read(settings, "fomc")["meetings"]
    frame = pd.DataFrame([{"date": pd.Timestamp(r["date"]), "sep": bool(r.get("sep", False))} for r in rows])
    return frame.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------- loading
def _period(settings: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = settings["data"].get("end")
    end = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    return pd.Timestamp(settings["learn"]["start"]), end


def fetch(settings: dict, provider: str | None = None) -> tuple[dict[str, pd.Series], bool, dict[str, str]]:
    """({FRED id: series}, is_live, {FRED id: error}).

    synthetic simulates everything. Any other provider reads FRED (the macro source of the real model),
    which needs FRED_API_KEY; without it the page falls back to simulated data and says so.
    """
    provider = provider or settings["data"]["provider"]
    start, end = _period(settings)
    ids = list(series_catalog(settings))
    if provider == "synthetic":
        return simulate(ids, start, end, settings["data"]["seed"]), False, {}
    key = os.environ.get(settings["data"]["fred_api_key_env"])
    if not key:
        error = f"Set {settings['data']['fred_api_key_env']} to read the Learn data from FRED"
        return simulate(ids, start, end, settings["data"]["seed"]), False, {"FRED": error}
    return _cached(settings, end, lambda: _fetch_fred(ids, key, start, end))


def _cached(settings, end, fetch_all):
    """One download per day on disk: about 40 FRED calls a day, not 40 per app start."""
    folder = resolve(settings["data"]["cache_dir"]) / "learn"
    path = folder / f"fred-{end.date()}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    data, errors = fetch_all()
    result = (data, True, errors)
    if not errors:
        folder.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(result, path)
    return result


def _fetch_fred(ids, key, start, end):
    from ..data.fred import fetch_fred

    data, errors = {}, {}
    for series_id in ids:
        try:
            data[series_id] = fetch_fred(series_id, key, start, end)
        except Exception as exc:  # noqa: BLE001 - one missing series must not hide the others
            errors[series_id] = str(exc)
    return data, errors


# ---------------------------------------------------------------- transforms
def _asof(series: pd.Series, dates) -> np.ndarray:
    """Last value of `series` on or before each date (NaN before the first)."""
    pos = series.index.searchsorted(pd.DatetimeIndex(dates), side="right") - 1
    values = series.to_numpy(dtype=float)
    out = np.where(pos >= 0, values[np.clip(pos, 0, None)], np.nan)
    return out


def _years_back(series: pd.Series, months: int) -> np.ndarray:
    return _asof(series, series.index - pd.DateOffset(months=months))


def policy_target(data: dict[str, pd.Series]) -> pd.Series:
    """Fed funds target: the single target (DFEDTAR) until 2008-12-15, then the middle of the range."""
    parts = []
    if "DFEDTAR" in data and not data["DFEDTAR"].empty:
        parts.append(data["DFEDTAR"])
    if "DFEDTARU" in data and "DFEDTARL" in data:
        mid = ((data["DFEDTARU"] + data["DFEDTARL"]) / 2).dropna()
        if parts:
            mid = mid[mid.index > parts[0].index[-1]]
        parts.append(mid)
    if not parts:
        return pd.Series(dtype=float)
    return pd.concat(parts).sort_index()


def target_range(data: dict[str, pd.Series], date) -> tuple[float, float] | None:
    """(lower, upper) of the target range on `date`, or None before ranges (2008-12-16)."""
    if "DFEDTARU" not in data or data["DFEDTARU"].empty:
        return None
    up, low = _asof(data["DFEDTARU"], [date])[0], _asof(data["DFEDTARL"], [date])[0]
    return None if np.isnan(up) or np.isnan(low) else (float(low), float(up))


def compute(indicator: Indicator, data: dict[str, pd.Series]) -> pd.Series:
    """The indicator's history from the raw series (empty if a series is missing)."""
    if indicator.transform == "policy":
        return policy_target(data)
    if any(s not in data or data[s].empty for s in indicator.series):
        return pd.Series(dtype=float)
    a = data[indicator.series[0]].dropna()
    kind = indicator.transform
    if kind == "level":
        out = a
    elif kind == "yoy":
        out = pd.Series(100 * (a.to_numpy() / _years_back(a, 12) - 1), index=a.index)
    elif kind == "ann3m":
        out = pd.Series(100 * ((a.to_numpy() / _years_back(a, 3)) ** 4 - 1), index=a.index)
    elif kind == "avg_diff3":
        out = pd.Series((a.to_numpy() - _years_back(a, 3)) / 3, index=a.index)
    elif kind in ("spread", "gap_pct", "ratio_pct"):
        b = data[indicator.series[1]].dropna()
        # The slower series is carried forward to the faster one's dates (e.g. NROU is quarterly).
        index = a.index if len(a) >= len(b) else b.index
        va, vb = _asof(a, index), _asof(b, index)
        if kind == "spread":
            values = va - vb
        elif kind == "gap_pct":
            values = 100 * (va / vb - 1)
        else:
            values = 100 * va / vb
        out = pd.Series(values, index=index)
    else:
        raise ValueError(f"Unknown transform '{kind}' for {indicator.id}")
    return (out * indicator.scale).replace([np.inf, -np.inf], np.nan).dropna()


def compute_all(indicators: dict[str, Indicator], data: dict[str, pd.Series]) -> dict[str, pd.Series]:
    return {name: compute(ind, data) for name, ind in indicators.items()}


# ---------------------------------------------------------------- simulation
def simulate(ids, start, end, seed: int = 42) -> dict[str, pd.Series]:
    """A coherent simulated US economy, so the page works without keys. Never shown as real.

    Monthly core: an unemployment gap with recessions, inflation that responds to it, and a Fed
    that follows a Taylor rule in 25 bp steps at its meetings. Everything else hangs off that core.
    """
    rng = np.random.default_rng(seed + 7)
    months = pd.date_range(pd.Timestamp(start).to_period("M").to_timestamp(), end, freq="MS")
    n = len(months)
    gap = np.zeros(n)
    recession = np.zeros(n, dtype=bool)
    shock_left = 0
    for i in range(1, n):
        if shock_left == 0 and rng.random() < 1 / 100 and gap[i - 1] < 0.5:
            shock_left = int(rng.integers(7, 13))
        if shock_left:
            gap[i] = gap[i - 1] + 0.35 + 0.1 * rng.standard_normal()
            recession[i] = True
            shock_left -= 1
        else:
            gap[i] = 0.975 * gap[i - 1] - 0.012 + 0.08 * rng.standard_normal()
    nrou = 5.6 - 1.4 * np.linspace(0, 1, n)
    unrate = np.clip(nrou + gap, 3.2, 14.0)
    core = np.zeros(n)
    core[0] = 3.5
    oil_infl = 0.0
    headline = np.zeros(n)
    for i in range(1, n):
        oil_infl = 0.9 * oil_infl + 0.25 * rng.standard_normal()
        core[i] = 0.985 * core[i - 1] + 0.015 * 2.1 - 0.012 * gap[i - 1] + 0.06 * rng.standard_normal()
        headline[i] = core[i] + oil_infl
    headline[0] = core[0]
    # The Fed: Taylor-rule target, moved at meetings in 25 bp steps, floor at 0-0.25.
    meeting_months = {1, 3, 4, 6, 7, 9, 10, 12}
    target = np.zeros(n)
    target[0] = 7.0
    desired = np.zeros(n)
    for i in range(n):
        desired[i] = 1.0 + core[i] + 0.5 * (core[i] - 2) - 1.0 * gap[i]
        if i == 0:
            continue
        target[i] = target[i - 1]
        if months[i].month in meeting_months:
            diff = desired[i] - target[i - 1]
            if abs(diff) > 0.375:
                step = 0.5 if abs(diff) > 2.0 else 0.25
                target[i] = target[i - 1] + np.sign(diff) * step
        target[i] = max(target[i], 0.125)
    target = np.round(target * 8) / 8

    days = pd.bdate_range(months[0], end)
    m_of_day = np.clip(months.searchsorted(days, side="right") - 1, 0, n - 1)

    def daily(values, noise, ar=0.97):
        e = np.zeros(len(days))
        shocks = rng.standard_normal(len(days)) * noise
        for i in range(1, len(days)):
            e[i] = ar * e[i - 1] + shocks[i]
        return pd.Series(np.asarray(values)[m_of_day] + e, index=days)

    def monthly(values):
        return pd.Series(np.asarray(values), index=months)

    def quarterly(values):
        q = months.month.isin([1, 4, 7, 10])
        return pd.Series(np.asarray(values)[q], index=months[q])

    def index_from_growth(annual_pct, base=100.0):
        return base * np.exp(np.cumsum(np.log1p(np.asarray(annual_pct) / 1200)))

    pressure = np.clip(desired - target, -1.5, 1.5)  # where the Fed is heading
    tgt = monthly(target)
    out: dict[str, pd.Series] = {}
    out["DFEDTAR"] = tgt[tgt.index < "2008-12-16"].reindex(days[days < "2008-12-16"], method="ffill")
    after = days[days >= "2008-12-16"]
    mid_after = pd.Series(target[m_of_day], index=days)[after]
    out["DFEDTARU"] = mid_after + 0.125
    out["DFEDTARL"] = mid_after - 0.125
    out["DFF"] = pd.Series(target[m_of_day], index=days) - 0.05 + 0.01 * rng.standard_normal(len(days))
    term = lambda k: daily(target + k * pressure, 0.012, 0.9)  # noqa: E731
    out["DGS1MO"] = term(0.15) + 0.0
    out["DGS3MO"] = term(0.35) + 0.08
    out["DGS6MO"] = term(0.6) + 0.12
    out["DGS2"] = daily(target + 1.0 * pressure + 0.25, 0.03)
    infl_exp = 2.2 + 0.25 * (core - 2.2)
    out["DGS10"] = daily(1.2 + infl_exp + 0.25 * target - 0.15 * gap, 0.04)
    out["T10YIE"] = daily(infl_exp - 0.1 * gap, 0.02)
    out["T5YIFR"] = daily(2.3 + 0.1 * (core - 2.2), 0.02)
    out["DFII10"] = out["DGS10"] - out["T10YIE"]
    out["CPILFESL"] = monthly(index_from_growth(core))
    out["CPIAUCSL"] = monthly(index_from_growth(headline))
    out["PCEPILFE"] = monthly(index_from_growth(core - 0.35))
    out["PCEPI"] = monthly(index_from_growth(headline - 0.4))
    out["UNRATE"] = monthly(np.round(unrate, 1))
    out["NROU"] = quarterly(nrou)
    payroll_growth = np.clip(150 - 120 * np.diff(gap, prepend=gap[0]) * 10, -900, 450) + 40 * rng.standard_normal(n)
    out["PAYEMS"] = monthly(110_000 + np.cumsum(payroll_growth))
    claims = pd.Series(np.exp(np.log(240_000) + 0.25 * gap / 2 + 0.05 * rng.standard_normal(n)), index=months)
    weeks = pd.date_range(months[0], end, freq="W-SAT")
    out["ICSA"] = claims.reindex(weeks, method="ffill") * np.exp(0.03 * rng.standard_normal(len(weeks)))
    out["JTSJOL"] = monthly(np.clip(7000 - 1300 * gap, 2500, 12000) + 150 * rng.standard_normal(n))
    wage = 2.0 + core * 0.6 - 0.5 * gap + 0.2 * rng.standard_normal(n)
    out["CES0500000003"] = monthly(index_from_growth(wage, 20.0))
    growth = 2.2 - 1.6 * np.diff(gap, prepend=gap[0]) * 12 + 0.6 * rng.standard_normal(n)
    out["OPHNFB"] = quarterly(index_from_growth(1.5 + 0.3 * rng.standard_normal(n), 80.0))
    real_gdp = index_from_growth(growth, 10_000.0)
    out["GDPC1"] = quarterly(real_gdp)
    out["GDPPOT"] = quarterly(real_gdp * np.exp(gap / 2 / 100))
    nominal = real_gdp * np.asarray(out["PCEPI"]) / 100
    out["GDP"] = quarterly(nominal)
    out["CP"] = quarterly(nominal * (0.09 - 0.006 * gap + 0.004 * rng.standard_normal(n)))
    out["INDPRO"] = monthly(index_from_growth(growth * 1.4 - 1.0, 90.0))
    out["RSAFS"] = monthly(index_from_growth(growth + headline + 0.5, 200_000.0))
    u3 = pd.Series(unrate).rolling(3, min_periods=1).mean()
    out["SAHMREALTIME"] = monthly(np.clip(u3 - u3.rolling(12, min_periods=1).min().shift(1).bfill(), 0, None).to_numpy())
    out["USREC"] = monthly(recession.astype(float))
    out["PSAVERT"] = monthly(np.clip(6 + 0.8 * gap + 0.5 * rng.standard_normal(n), 1, 30))
    out["TDSP"] = quarterly(9.5 + 0.15 * target - 0.1 * gap)
    out["DRCCLACBS"] = quarterly(np.clip(2.6 + 0.5 * gap, 1.2, 7))
    out["HOUST"] = monthly(np.clip(1500 - 60 * target - 150 * gap + 60 * rng.standard_normal(n), 450, 2300))
    oil = pd.Series(70 * np.exp(np.cumsum(0.08 * rng.standard_normal(n)) * 0.6), index=months)
    out["DCOILWTICO"] = daily(oil.to_numpy(), 0.8)
    out["DTWEXBGS"] = daily(100 + 2 * target + 4 * np.maximum(gap, 0), 0.4)
    walcl = np.where(target < 0.5, 4_000_000 + np.cumsum(target < 0.5) * 40_000, 1_000_000.0)
    out["WALCL"] = pd.Series(walcl, index=months).reindex(weeks, method="ffill")
    out["M2SL"] = monthly(index_from_growth(5.5 - 0.5 * target + 1.5 * np.maximum(gap, 0), 3000.0))
    out["GFDEGDQ188S"] = quarterly(np.clip(55 + np.cumsum(0.05 + 0.25 * np.maximum(gap, 0)), 40, 140))
    out["VIXCLS"] = daily(16 + 6 * np.maximum(np.diff(gap, prepend=gap[0]) * 12, 0) + 2 * recession, 0.8, 0.95).clip(lower=9)
    out = {k: v.loc[start:end].dropna() for k, v in out.items()}
    return {k: out[k] for k in ids if k in out}
