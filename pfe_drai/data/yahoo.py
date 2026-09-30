"""Yahoo Finance provider through yfinance (pip install yfinance).

Research use only: Yahoo's terms generally forbid commercial use (see the re-audit).
"""

import pandas as pd

from .base import DataProvider, register
from .catalog import CATALOG


@register
class YahooProvider(DataProvider):
    name = "yahoo"

    def fetch(self, start, end):
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("pip install yfinance to use the yahoo provider") from exc
        tickers = {n: s.source_ids["yahoo"] for n, s in CATALOG.items() if "yahoo" in s.source_ids}
        prices = yf.download(list(tickers.values()), start=start, end=end, auto_adjust=True)["Close"]
        data = {name: prices[ticker].dropna() for name, ticker in tickers.items()}
        missing = [n for n in CATALOG if n not in data]
        if missing:
            raise RuntimeError(f"Yahoo has no data for {missing}: combine with FRED or CSV files")
        return data


def load_ohlc(ticker: str, start, end) -> pd.DataFrame:  # pragma: no cover - helper for notebooks
    import yfinance as yf

    return yf.download(ticker, start=start, end=end, auto_adjust=True)
