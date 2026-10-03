"""Region provider for the UK, Japan and emerging markets (docs/REGIONS.md).

Each series of a region is described in its overlay (config/regions/<region>.yaml, `data.regional.series`):
where it comes from, what it means, when it was public. This module only knows how to read each kind of
source; which code, which countries and which weights is data, fixed in the overlay before any real run.

Sources (`source:`):

    tiingo        a US-listed ETF, adjusted close; with `fx`, converted to the local currency with a FRED H.10 rate
    realised_vol  21-day realised volatility of the region's equity series, in % (the stand-in for a VIX)
    boe           Bank of England IADB, daily; `minus` subtracts a second code (nominal - real = breakeven)
    mof           Japan Ministry of Finance JGB yields, daily; `column` is the maturity (2Y, 10Y)
    oecd, bis     SDMX: `key` with an `{area}` placeholder; `areas` maps each area to its weight

Several `areas` make a composite (emerging markets): the weighted average of each area's monthly change
(log change for an index, difference for a rate), chained into one series. A period counts only when the
areas reporting it carry at least `min_weight` of the total weight, so a ragged edge does not move the
composite on one small country. The composite's level is arbitrary; every feature reads changes or
expanding z-scores, which a constant offset does not move.

Point-in-time: none of these sources exposes first releases. Monthly series are dated by the end of their
month plus a conservative `lag_days` (not fully point-in-time for revised series, as in docs/EURO.md).
"""

import os

import httpx
import numpy as np
import pandas as pd

from .base import DataProvider, register
from .dating import check_fresh, realised_vol_percent, release_dated
from .fred import fetch_fred
from .official import fetch_bis, fetch_boe, fetch_mof, fetch_oecd
from .tiingo import fetch_tiingo, fetch_tiingo_fx

MARKET_SOURCES = {"tiingo", "realised_vol"}  # market prices: dated on their own day, never stale-checked here
STALE_DAYS = {"monthly": 150, "daily": 30}


def composite(frame: pd.DataFrame, weights: dict[str, float], kind: str, min_weight: float = 0.5) -> pd.Series:
    """Weighted average of each area's change, chained into one series (see the module docstring)."""
    w = pd.Series({area: weight for area, weight in weights.items() if area in frame.columns}, dtype=float)
    if w.empty:
        raise ValueError(f"No data for any area of the composite ({', '.join(weights)})")
    needed = min_weight * float(sum(weights.values()))
    frame = frame[list(w.index)].sort_index()
    if kind == "rate":
        # Policy rates are step functions: carry each area's last level, but never past its own last observation.
        last = frame.apply(pd.Series.last_valid_index)
        frame = frame.ffill().apply(lambda col: col.where(col.index <= last[col.name]))
        changes = frame.diff()
    else:
        changes = np.log(frame).diff()
    reported = changes.notna().mul(w).sum(axis=1)
    mean = changes.fillna(0).mul(w).sum(axis=1) / reported.where(reported > 0)
    mean = mean.where(reported >= needed)
    covered = frame.notna().mul(w).sum(axis=1) >= needed
    if not covered.any():
        raise ValueError(f"The areas with data ({', '.join(w.index)}) never reach {min_weight:.0%} of the composite's weight")
    first = covered.idxmax()
    mean = mean.loc[first:]
    mean.iloc[0] = 0.0
    if kind == "rate":
        anchor = float((frame.loc[first] * w).sum() / w[frame.loc[first].notna()].sum())
        level = anchor + mean.fillna(0).cumsum()
    else:
        level = 100 * np.exp(mean.fillna(0).cumsum())
    # A period below `min_weight` is not a value: it is left out and `align` carries the last level.
    return level[mean.notna()].rename(None)


@register
class RegionalProvider(DataProvider):
    name = "regional"

    def __init__(self, settings: dict):
        super().__init__(settings)
        #: What each series was read from, for the `data` command (codes, areas and their last period).
        self.details: dict[str, str] = {}

    def _cfg(self) -> dict:
        return self.settings["data"]["regional"]["series"]

    def _key(self, env_name: str, what: str) -> str:
        env = self.settings["data"][env_name]
        key = os.environ.get(env)
        if not key:
            raise RuntimeError(f"Set {env}: {what}")
        return key

    def fetch(self, start, end):
        return self.fetch_subset(list(self._cfg()), start, end)

    def fetch_subset(self, names, start, end):
        cfg = self._cfg()
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        data: dict[str, pd.Series] = {}
        wanted = [name for name in cfg if name in names]
        # The realised volatility is computed from the equity series: read it first if it is needed.
        if any(cfg[n]["source"] == "realised_vol" for n in wanted) and "equity" not in wanted:
            wanted = ["equity", *wanted]
        for name in wanted:
            spec = cfg[name]
            series = self._series(name, spec, data, start, end)
            if spec["source"] not in MARKET_SOURCES:
                frequency = spec.get("frequency", "daily")
                check_fresh(name, series, end, spec.get("max_stale_days", STALE_DAYS[frequency]))
                series = release_dated(series, spec.get("lag_days", 0), monthly=frequency == "monthly")
                self.release_dated.add(name)
            data[name] = series.loc[start:]
        return {name: data[name] for name in names if name in data}

    def _series(self, name: str, spec: dict, data: dict, start, end) -> pd.Series:
        source = spec["source"]
        if source == "tiingo":
            key = self._key("tiingo_api_key_env", f"'{name}' is the ETF {spec['ticker']} from Tiingo")
            prices = fetch_tiingo(spec["ticker"], key, start, end)
            self.details[name] = f"tiingo {spec['ticker']}"
            if "fx" in spec:
                prices = self._local_currency(name, prices, spec["fx"], start, end)
            return prices
        if source == "realised_vol":
            self.details[name] = "realised volatility of equity"
            return realised_vol_percent(data["equity"])
        if source == "boe":
            codes = [spec["code"], *([spec["minus"]] if "minus" in spec else [])]
            frame = fetch_boe(codes, start, end)
            series = frame[spec["code"]] - (frame[spec["minus"]] if "minus" in spec else 0)
            self.details[name] = "boe " + " - ".join(codes)
            return series.dropna()
        if source == "mof":
            self.details[name] = f"mof JGB {spec['column']}"
            return fetch_mof(start, end)[spec["column"]].dropna()
        if source in ("oecd", "bis"):
            return self._sdmx(name, spec, start)
        raise ValueError(f"Series '{name}': unknown source '{source}'")

    def _local_currency(self, name: str, prices: pd.Series, fx: dict, start, end) -> pd.Series:
        """A dollar ETF price in local currency: the region's market without the dollar's moves (docs/REGIONS.md).

        History is the FRED H.10 noon rate. H.10 is published once a week, so its last days are missing until
        then: with `fx.tiingo`, only the days after its last observation are filled with Tiingo's daily close of
        the same pair, so the latest closes are converted too. Earlier days are never touched.
        """
        key = self._key("fred_api_key_env", f"the exchange rate {fx['fred']} comes from FRED")
        rate = fetch_fred(fx["fred"], key, start, end)
        self.details[name] += f" in local currency (FRED {fx['fred']}"
        last = rate.index.max() if len(rate) else None
        if "tiingo" in fx and last is not None and last < pd.Timestamp(end):
            try:
                tiingo_key = self._key("tiingo_api_key_env", "the latest exchange rates come from Tiingo")
                recent = fetch_tiingo_fx(fx["tiingo"], tiingo_key, last + pd.Timedelta(days=1), end)
                rate = pd.concat([rate, recent[recent.index > last]])
                self.details[name] += f", then Tiingo {fx['tiingo']} after {last.date()}"
            except httpx.HTTPError as exc:  # the H.10 history still stands: the series just ends earlier
                self.details[name] += f"; Tiingo {fx['tiingo']} unavailable: {type(exc).__name__}"
        self.details[name] += ")"
        both = pd.concat({"price": prices, "rate": rate}, axis=1, join="inner").dropna()
        if fx["quote"] == "usd_per_local":  # e.g. DEXUSUK, dollars per pound
            return both["price"] / both["rate"]
        if fx["quote"] == "local_per_usd":  # e.g. DEXJPUS, yen per dollar
            return both["price"] * both["rate"]
        raise ValueError(f"fx.quote must be usd_per_local or local_per_usd, not {fx['quote']!r}")

    def _sdmx(self, name: str, spec: dict, start) -> pd.Series:
        areas = spec["areas"]
        key = spec["key"].format(area="+".join(areas))
        fetch = fetch_oecd if spec["source"] == "oecd" else fetch_bis
        # Monthly series start a year early: the first change needs the month before.
        frame = fetch(spec["flow"], key, pd.Timestamp(start) - pd.DateOffset(years=1))
        lasts = {area: (frame[area].last_valid_index() if area in frame else None) for area in areas}
        self.details[name] = f"{spec['source']} {spec['flow']} {key} | last: " + ", ".join(
            f"{area} {last.date() if last is not None else 'none'}" for area, last in lasts.items()
        )
        if len(areas) == 1:
            area = next(iter(areas))
            if area not in frame:
                raise ValueError(f"Series '{name}': no data for {area} ({spec['source']} {key})")
            return frame[area].dropna()
        return composite(frame, areas, spec.get("kind", "index"), spec.get("min_weight", 0.5))

    def check(self, data):
        missing = [name for name in self._cfg() if name not in data]
        if missing:
            raise ValueError(f"Provider 'regional' is missing series: {', '.join(missing)}")


def describe(settings: dict) -> list[dict]:
    """What the overlay says about each series: source, licence, release lag, vintage (docs/REGIONS.md)."""
    return [
        {"name": name, **{k: spec.get(k) for k in ("source", "licence", "vintage", "lag_days", "meaning")}}
        for name, spec in settings["data"]["regional"]["series"].items()
    ]
