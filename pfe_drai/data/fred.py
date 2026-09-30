"""FRED / ALFRED provider (https://fred.stlouisfed.org/docs/api/fred/).

Needs a free API key in the environment variable named by data.fred_api_key_env.
Series without a FRED id (ETF prices) are taken from the fallback provider
set in data.fred_fallback (default: synthetic) so the pipeline still runs.
"""

import os

import httpx
import pandas as pd

from .base import DataProvider, get_provider, register
from .catalog import CATALOG

URL = "https://api.stlouisfed.org/fred/series/observations"


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


@register
class FredProvider(DataProvider):
    name = "fred"

    def fetch(self, start, end):
        key = os.environ.get(self.settings["data"]["fred_api_key_env"])
        if not key:
            raise RuntimeError(
                f"Set {self.settings['data']['fred_api_key_env']} to use FRED "
                "(free key: https://fredaccount.stlouisfed.org/apikeys)"
            )
        data = {}
        missing = []
        for name, series in CATALOG.items():
            if "fred" in series.source_ids:
                data[name] = fetch_fred(series.source_ids["fred"], key, start, end)
            else:
                missing.append(name)
        if missing:
            fallback_name = self.settings["data"].get("fred_fallback", "synthetic")
            fallback = get_provider({**self.settings, "data": {**self.settings["data"], "provider": fallback_name}})
            extra = fallback.fetch(start, end)
            data.update({name: extra[name] for name in missing})
        return data
