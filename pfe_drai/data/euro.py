"""Euro-area provider: ECB Data Portal and Eurostat (both key-free) plus a euro-zone equity ETF from Tiingo.

Returns the pipeline's canonical column names with their euro-area meaning (docs/EURO.md):

    equity         euro-zone equity ETF (Tiingo, USD price; the index levels are licensed)
    vix            euro-zone realised volatility of that ETF, in % (VSTOXX is licensed by STOXX: not used)
    us10y, us2y    ECB AAA euro-area government yield curve, 10y and 2y (daily)
    credit_spread  10y all-issuer euro-area government yield minus the AAA one (daily): peripheral stress
    cpi            HICP all items, euro area (monthly index)
    indpro         industrial production, euro area (monthly index)
    claims         unemployment rate, euro area (monthly; the euro area has no weekly claims)

There is no free daily euro breakeven: the inflation dimension drops it (features.drop).

Point-in-time: neither source exposes first releases through its public API, so every monthly series
is dated by a conservative release lag (data.euro.series.<name>.lag_days) and the backtest is not fully
point-in-time for the revised ones. Nothing here silently uses today's revised value as if it was known
at the reference date. Series are returned already dated by release day (`release_dated`).
"""

import os

import httpx
import pandas as pd

from .base import DataProvider, register
from .tiingo import fetch_tiingo

ECB_URL = "https://data-api.ecb.europa.eu/service/data/{dataset}/{key}"
EUROSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}"

REQUIRED = ["equity", "vix", "us10y", "us2y", "credit_spread", "cpi", "indpro", "claims"]


def _period_start(period: str) -> pd.Timestamp:
    """'2024-03-15' -> that day; '2024-03' (Eurostat monthly) or '2024-Q1' -> first day of the period."""
    if "Q" in period:
        return pd.Period(period.replace("-", ""), freq="Q").to_timestamp()
    return pd.Timestamp(pd.Period(period).to_timestamp()) if len(period) == 7 else pd.Timestamp(period)


def parse_ecb(payload: dict) -> pd.Series:
    """One series of an SDMX-JSON message (format=jsondata) of the ECB Data Portal."""
    series = payload["dataSets"][0]["series"]
    if len(series) != 1:
        raise ValueError(f"Expected one ECB series, got {len(series)}: the key is not specific enough")
    observations = next(iter(series.values()))["observations"]
    time = payload["structure"]["dimensions"]["observation"][0]["values"]
    values = {_period_start(time[int(i)]["id"]): obs[0] for i, obs in observations.items() if obs and obs[0] is not None}
    return pd.Series(values, dtype=float).sort_index()


def parse_eurostat(payload: dict) -> pd.Series:
    """One series of a Eurostat JSON-stat 2.0 message: every dimension but time must be a single category."""
    ids, sizes = payload["id"], payload["size"]
    if any(size != 1 for dim, size in zip(ids, sizes, strict=True) if dim != "time"):
        raise ValueError("Eurostat response has more than one series: add a filter for every non-time dimension")
    time = payload["dimension"]["time"]["category"]["index"]
    position = {period: pos for period, pos in time.items()} if isinstance(time, dict) else {p: i for i, p in enumerate(time)}
    value = payload.get("value", {})
    value = value if isinstance(value, dict) else dict(enumerate(value))
    by_position = {pos: value[str(pos)] if str(pos) in value else value.get(pos) for pos in position.values()}
    values = {_period_start(period): by_position[pos] for period, pos in position.items() if by_position[pos] is not None}
    return pd.Series(values, dtype=float).sort_index()


def fetch_ecb(dataset: str, key: str, start, end) -> pd.Series:
    params = {"startPeriod": str(pd.Timestamp(start).date()), "endPeriod": str(pd.Timestamp(end).date()), "format": "jsondata"}
    response = httpx.get(ECB_URL.format(dataset=dataset, key=key), params=params, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return parse_ecb(response.json())


def fetch_eurostat(dataset: str, filters: dict, start) -> pd.Series:
    params = {"format": "JSON", "lang": "EN", "sinceTimePeriod": pd.Timestamp(start).strftime("%Y-%m"), **filters}
    response = httpx.get(EUROSTAT_URL.format(dataset=dataset), params=params, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return parse_eurostat(response.json())


def realised_vol_percent(equity: pd.Series, window: int = 21) -> pd.Series:
    """Annualised realised volatility of daily log returns, in % (the euro stand-in for the VIX level)."""
    import numpy as np

    return (np.log(equity).diff().rolling(window).std() * np.sqrt(252) * 100).dropna()


def release_dated(series: pd.Series, lag_days: int, monthly: bool) -> pd.Series:
    """Date a series by the day it was public: end of its period (months) plus a conservative lag."""
    out = series.copy()
    out.index = (out.index + pd.offsets.MonthEnd(0) if monthly else out.index) + pd.Timedelta(days=lag_days)
    return out[~out.index.duplicated(keep="last")].sort_index()


@register
class EuroProvider(DataProvider):
    name = "euro"

    def _cfg(self) -> dict:
        return self.settings["data"]["euro"]["series"]

    def fetch(self, start, end):
        cfg = self._cfg()
        env = self.settings["data"]["tiingo_api_key_env"]
        key = os.environ.get(env)
        if not key:
            raise RuntimeError(f"Set {env}: the euro-zone equity ETF comes from Tiingo (the ECB and Eurostat need no key)")
        data = {"equity": fetch_tiingo(cfg["equity"]["ticker"], key, start, end)}
        data["vix"] = realised_vol_percent(data["equity"])
        for name in ("us10y", "us2y"):
            data[name] = self._ecb(cfg[name], start, end)
        data["credit_spread"] = (
            self._ecb(cfg["credit_spread"]["all"], start, end) - self._ecb(cfg["credit_spread"]["aaa"], start, end)
        ).dropna()
        data["credit_spread"] = release_dated(data["credit_spread"], cfg["credit_spread"]["lag_days"], monthly=False)
        for name in ("cpi", "indpro", "claims"):
            spec = cfg[name]
            data[name] = release_dated(fetch_eurostat(spec["dataset"], spec["filters"], start), spec["lag_days"], monthly=True)
        self.release_dated.update(["us10y", "us2y", "credit_spread", "cpi", "indpro", "claims"])
        return {name: data[name].loc[pd.Timestamp(start) :] for name in REQUIRED}

    def _ecb(self, spec: dict, start, end) -> pd.Series:
        series = fetch_ecb(spec["dataset"], spec["key"], start, end)
        return release_dated(series, spec["lag_days"], monthly=False) if "lag_days" in spec else series

    def check(self, data):
        missing = [name for name in REQUIRED if name not in data]
        if missing:
            raise ValueError(f"Provider 'euro' is missing series: {', '.join(missing)}")


def describe(settings: dict) -> list[dict]:
    """What the euro catalog says about each series: source, licence, release lag, vintage (docs/EURO.md)."""
    rows = []
    for name, spec in settings["data"]["euro"]["series"].items():
        rows.append({"name": name, **{k: spec.get(k) for k in ("source", "licence", "vintage", "lag_days", "meaning")}})
    return rows
