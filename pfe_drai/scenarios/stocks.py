"""Single stocks in your own portfolio: their move in each historical scenario window.

- Listed before the window: its actual total return over the window (adjusted closes, dividends
  and splits included). Marked "actual".
- Not listed yet: beta x the S&P 500 (SPY) return over the window, beta from daily returns over
  the last two years. Marked "estimated". This keeps only the market part of the move: what was
  specific to the company, its sector or its size at the time is not in it.

Prices come from Tiingo (US listings and ADRs) and live in memory only: nothing is written to
disk. Only the tickers are sent to Tiingo, never the weights.
"""

import dataclasses
import os
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from .library import Scenario
from .portfolio import STOCK

BENCHMARK = "SPY"  # the S&P 500, listed since January 1993: covers every scenario window
HISTORY_START = "1993-01-29"
BETA_DAYS = 504  # two years of trading days
MIN_BETA_DAYS = 120
MAX_START_GAP = pd.Timedelta(days=7)  # a price within a week before the window start counts as listed


@dataclass
class StockMove:
    ticker: str
    first_date: str  # first price Tiingo has
    beta: float | None  # to SPY, last two years; None with too short a history
    moves: dict[str, float]  # scenario id -> return over the window
    sources: dict[str, str]  # scenario id -> "actual" or "estimated"


class StockDataError(ValueError):
    def __init__(self, errors: list[dict]):
        self.errors = errors
        super().__init__("; ".join(f"{e['code']} {e}" for e in errors))


def window_return(prices: pd.Series, start, end) -> float | None:
    """Return from the last close on or before `start` to the last close on or before `end`, if listed then."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    before = prices.loc[:start]
    if before.empty or start - before.index[-1] > MAX_START_GAP or prices.index[-1] < end:
        return None
    return float(prices.loc[:end].iloc[-1] / before.iloc[-1] - 1)


def beta(prices: pd.Series, bench: pd.Series, days: int = BETA_DAYS) -> float | None:
    returns = pd.concat([prices.pct_change(), bench.pct_change()], axis=1, join="inner").dropna().tail(days)
    if len(returns) < MIN_BETA_DAYS:
        return None
    stock, market = returns.iloc[:, 0], returns.iloc[:, 1]
    return float(stock.cov(market) / market.var())


def stock_moves(tickers: list[str], scenarios: list[Scenario], fetch: Callable[[str], pd.Series]) -> dict[str, StockMove]:
    """Each ticker's move in each scenario; raise StockDataError listing every ticker that failed.

    `fetch(ticker)` returns adjusted daily closes, raises LookupError for an unknown ticker.
    """
    try:
        bench = fetch(BENCHMARK)
    except Exception as exc:
        raise StockDataError([{"code": "fetch_failed", "ticker": BENCHMARK, "reason": type(exc).__name__}]) from None
    out, errors = {}, []
    for ticker in tickers:
        try:
            prices = fetch(ticker).dropna()
        except LookupError:
            errors.append({"code": "unknown_ticker", "ticker": ticker})
            continue
        except Exception as exc:  # network, rate limit: say which ticker, keep the others
            errors.append({"code": "fetch_failed", "ticker": ticker, "reason": type(exc).__name__})
            continue
        if prices.empty:
            errors.append({"code": "unknown_ticker", "ticker": ticker})
            continue
        b = beta(prices, bench)
        moves, sources = {}, {}
        for sc in scenarios:
            actual = window_return(prices, sc.start, sc.end)
            if actual is not None:
                moves[sc.id], sources[sc.id] = actual, "actual"
            elif b is not None:
                moves[sc.id], sources[sc.id] = b * window_return(bench, sc.start, sc.end), "estimated"
        if len(moves) < len(scenarios):
            errors.append({"code": "short_history", "ticker": ticker, "since": str(prices.index[0].date())})
            continue
        out[ticker] = StockMove(ticker, str(prices.index[0].date()), b, moves, sources)
    if errors:
        raise StockDataError(errors)
    return out


def with_stocks(scenarios: list[Scenario], moves: dict[str, StockMove]) -> list[Scenario]:
    """The scenarios with each stock's move added as a "stock:<TICKER>" shock, so impact_table,
    holdings_impact and the committee note treat a stock like any asset class."""
    return [
        dataclasses.replace(sc, shocks={**sc.shocks, **{f"{STOCK}:{tk}": m.moves[sc.id] for tk, m in moves.items()}})
        for sc in scenarios
    ]


def tiingo_fetcher(settings: dict) -> Callable[[str], pd.Series]:
    """Adjusted closes from Tiingo, kept in memory by the caller. Live data only."""
    import httpx

    from ..data.tiingo import fetch_tiingo

    if settings["data"]["provider"] not in ("fred", "tiingo"):
        raise StockDataError([{"code": "needs_live"}])
    env = settings["data"]["tiingo_api_key_env"]
    key = os.environ.get(env)
    if not key:
        raise StockDataError([{"code": "needs_key", "env": env}])
    end = pd.Timestamp.today().normalize()

    def fetch(ticker: str) -> pd.Series:
        try:
            return fetch_tiingo(ticker, key, HISTORY_START, end)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LookupError(ticker) from None
            raise

    return fetch
