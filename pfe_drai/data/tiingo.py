"""Tiingo provider for daily ETF prices (https://www.tiingo.com/documentation/end-of-day).

Needs a free API key in the environment variable named by data.tiingo_api_key_env.
Free tier: 1,000 requests/day, 30+ years of history. Internal commercial use is a paid plan;
showing raw prices to clients is redistribution and is licensed separately.

Tiingo only covers market prices. Use it as the FRED fallback (provider: fred,
fred_fallback: tiingo) to get every catalog series from real sources.
"""

import os

import httpx
import pandas as pd

from .base import DataProvider, register
from .catalog import CATALOG, TESTED

URL = "https://api.tiingo.com/tiingo/daily/{ticker}/prices"
FX_URL = "https://api.tiingo.com/tiingo/fx/{pair}/prices"


def fetch_tiingo(ticker: str, api_key: str, start, end) -> pd.Series:
    """Download adjusted daily closes (dividends and splits included) for one ticker."""
    params = {
        "startDate": str(pd.Timestamp(start).date()),
        "endDate": str(pd.Timestamp(end).date()),
        "resampleFreq": "daily",
    }
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    response = httpx.get(URL.format(ticker=ticker.lower()), params=params, headers=headers, timeout=30)
    response.raise_for_status()
    rows = response.json()
    values = pd.Series({r["date"][:10]: r["adjClose"] for r in rows}, dtype=float)
    values.index = pd.to_datetime(values.index)
    return values.dropna().sort_index()


def fetch_tiingo_fx(pair: str, api_key: str, start, end) -> pd.Series:
    """Daily closes of a currency pair (e.g. gbpusd = dollars per pound, usdjpy = yen per dollar)."""
    params = {
        "startDate": str(pd.Timestamp(start).date()),
        "endDate": str(pd.Timestamp(end).date()),
        "resampleFreq": "1day",
    }
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    response = httpx.get(FX_URL.format(pair=pair.lower()), params=params, headers=headers, timeout=30)
    response.raise_for_status()
    values = pd.Series({r["date"][:10]: r["close"] for r in response.json()}, dtype=float)
    values.index = pd.to_datetime(values.index)
    return values.dropna().sort_index()


@register
class TiingoProvider(DataProvider):
    name = "tiingo"

    def fetch(self, start, end):
        return self.fetch_subset(list(CATALOG), start, end)

    def fetch_subset(self, names, start, end):
        env = self.settings["data"]["tiingo_api_key_env"]
        key = os.environ.get(env)
        if not key:
            raise RuntimeError(f"Set {env} to use Tiingo (free key: https://www.tiingo.com/account/api/token)")
        known = {**TESTED, **CATALOG}
        return {
            name: fetch_tiingo(known[name].source_ids["tiingo"], key, start, end)
            for name in names
            if "tiingo" in known[name].source_ids
        }
