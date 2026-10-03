"""FRED / ALFRED provider (https://fred.stlouisfed.org/docs/api/fred/).

Needs a free API key in the environment variable named by data.fred_api_key_env.
Series without a FRED id (ETF prices) are taken from the fallback provider
set in data.fred_fallback: tiingo for real prices, synthetic to run without a Tiingo key.
Commercial use must show: "This product uses the FRED® API but is not endorsed or
certified by the Federal Reserve Bank of St. Louis."

Revised series (catalog `revised=True`: claims, industrial production, CPI) are read from
ALFRED as first releases, dated on the day they were published. Today's FRED values are
revised figures that nobody had at the time, so a backtest on them would see the future.
"""

import os

import httpx
import pandas as pd

from .base import DataProvider, get_provider, register
from .catalog import CATALOG, TESTED

URL = "https://api.stlouisfed.org/fred/series/observations"
# ALFRED's whole real-time range: every vintage ever published.
REALTIME_ALL = ("1776-07-04", "9999-12-31")
PAGE = 100_000  # maximum rows per request


def fetch_fred(series_id: str, api_key: str, start, end, vintage: str | None = None) -> pd.Series:
    """Download one series. Pass `vintage` (YYYY-MM-DD) for point-in-time values from ALFRED."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": str(pd.Timestamp(start).date()),
        "observation_end": str(pd.Timestamp(end).date()),
    }
    if vintage:
        params["realtime_start"] = params["realtime_end"] = vintage
    response = httpx.get(URL, params=params, timeout=30)
    response.raise_for_status()
    rows = response.json()["observations"]
    values = pd.to_numeric(pd.Series({r["date"]: r["value"] for r in rows}), errors="coerce")
    values.index = pd.to_datetime(values.index)
    return values.dropna()


def fetch_vintages(series_id: str, api_key: str, start, end) -> pd.DataFrame:
    """Every published value of a series: one row per (date, value, realtime_start)."""
    rows, offset = [], 0
    while True:
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": str(pd.Timestamp(start).date()),
            "observation_end": str(pd.Timestamp(end).date()),
            "realtime_start": REALTIME_ALL[0],
            "realtime_end": REALTIME_ALL[1],
            "limit": PAGE,
            "offset": offset,
        }
        response = httpx.get(URL, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        page = payload["observations"]
        rows += page
        offset += len(page)
        if not page or offset >= int(payload.get("count", offset)):
            break
    frame = pd.DataFrame(rows, columns=["date", "value", "realtime_start"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["realtime_start"] = pd.to_datetime(frame["realtime_start"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna()


def first_releases(vintages: pd.DataFrame, frequency: str, fallback_lag_days: int = 0) -> pd.Series:
    """First published value of each observation, indexed by the day it was published.

    ALFRED only keeps vintages from a series' first archived release onwards: older
    observations all show that first vintage as their release date. Those are dated at
    the end of their period plus `fallback_lag_days` instead, as the other providers are.
    """
    if vintages.empty:
        return pd.Series(dtype=float)
    first = vintages.sort_values("realtime_start").groupby("date", as_index=False).first()
    period_end = first["date"] + pd.offsets.MonthEnd(0) if frequency == "monthly" else first["date"]
    estimated = period_end + pd.Timedelta(days=fallback_lag_days)
    archive_start = vintages["realtime_start"].min()
    before_archive = (first["realtime_start"] == archive_start) & (archive_start > estimated + pd.Timedelta(days=31))
    first["released"] = first["realtime_start"].where(~before_archive, estimated)
    # Several periods published the same day (after a delay): the newest one is the latest level.
    first = first.sort_values(["released", "date"])
    newest_before = first["date"].cummax().shift()
    first = first[newest_before.isna() | (first["date"] > newest_before)]
    first = first.drop_duplicates("released", keep="last")
    return pd.Series(first["value"].to_numpy(), index=pd.DatetimeIndex(first["released"]), dtype=float)


@register
class FredProvider(DataProvider):
    name = "fred"

    def fetch(self, start, end):
        return self.fetch_subset(list(CATALOG), start, end)

    def fetch_subset(self, names, start, end):
        cfg = self.settings["data"]
        key = os.environ.get(cfg["fred_api_key_env"])
        if not key:
            raise RuntimeError(
                f"Set {cfg['fred_api_key_env']} to use FRED (free key: https://fredaccount.stlouisfed.org/apikeys)"
            )
        point_in_time = cfg.get("point_in_time", True)
        lags = cfg.get("publication_lag_days", {})
        data = {}
        missing = []
        for name in names:
            series = CATALOG[name] if name in CATALOG else TESTED[name]
            if "fred" not in series.source_ids:
                missing.append(name)
            elif series.revised and point_in_time:
                vintages = fetch_vintages(series.source_ids["fred"], key, start, end)
                data[name] = first_releases(vintages, series.frequency, lags.get(name, 0))
                self.release_dated.add(name)
            else:
                data[name] = fetch_fred(series.source_ids["fred"], key, start, end)
        if missing:
            fallback_name = cfg.get("fred_fallback", "synthetic")
            fallback = get_provider({**self.settings, "data": {**cfg, "provider": fallback_name}})
            extra = fallback.fetch_subset(missing, start, end)
            data.update({name: extra[name] for name in missing})
            # Partly simulated data is not live: it must not reach the track record.
            self.is_live = fallback.is_live
        return data
