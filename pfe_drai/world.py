"""World markets: country equity ETFs, their returns and a market-only stress state (docs/WORLD.md).

The regime model (stress, growth, inflation) is built on US macro data, so it is US-only.
For the other countries we only have market prices, so each one gets a transparent market
stress state computed from its own ETF, with the same thresholds everywhere:

    stress    21-day realised vol in the top 10% of its own last 5 years AND drawdown <= -10%
    elevated  21-day realised vol in the top 20% of its own last 5 years
    calm      otherwise

A new state is confirmed once it has held `world.confirm_days` days in a row.

Everything is computed from data available on the day (rolling windows, no look-ahead).
"""

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

from .config import resolve

STATES = ["calm", "elevated", "stress"]
REGIONS = ["world", "europe", "americas", "asia"]
HORIZONS = ["1D", "1W", "1M", "3M", "YTD", "1Y"]
_OFFSETS = {
    "1D": None,  # previous close
    "1W": pd.DateOffset(weeks=1),
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "1Y": pd.DateOffset(years=1),
}


@dataclass(frozen=True)
class Market:
    id: str  # ISO 3166-1 alpha-3, used to place it on the map
    ticker: str
    region: str
    tracks: str
    benchmark: str
    name: dict
    beta: float = 1.0  # synthetic data only
    vol: float = 0.15  # synthetic data only


def _read(settings: dict) -> dict:
    return yaml.safe_load(resolve(settings["world"]["markets"]).read_text(encoding="utf-8"))


def load_markets(settings: dict) -> list[Market]:
    return [Market(**m) for m in _read(settings)["markets"]]


def load_replay(settings: dict) -> list[dict]:
    """Past episodes to replay on the map: [{date, name: {fr, en}}]."""
    return [{**r, "date": pd.Timestamp(r["date"])} for r in _read(settings).get("replay", [])]


# ---------------------------------------------------------------- prices
def _period(settings: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    cfg = settings["data"]
    end = pd.Timestamp(cfg["end"]) if cfg.get("end") else pd.Timestamp.today().normalize()
    return pd.Timestamp(cfg["start"]), end


def fetch_prices(settings: dict, provider: str | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Daily closes, one column per market id, and {market id: error} for markets that failed.

    Sources follow data.provider: synthetic simulates; fred and tiingo read Tiingo (FRED has no
    country ETFs); yahoo reads yfinance (research only); csv reads <csv_dir>/markets/<TICKER>.csv.
    """
    provider = provider or settings["data"]["provider"]
    markets = load_markets(settings)
    start, end = _period(settings)
    if provider == "synthetic":
        return simulate_markets(markets, start, end, settings["data"]["seed"]), {}
    if provider in ("fred", "tiingo"):
        return _cached(settings, "tiingo", end, lambda: _fetch_tiingo(settings, markets, start, end))
    if provider == "yahoo":
        return _fetch_yahoo(markets, start, end)
    if provider == "csv":
        return _fetch_csv(settings, markets, start, end)
    raise ValueError(f"No world market prices for provider '{provider}'")


def _cached(settings, source, end, fetch):
    """Keep one download per source and day on disk: about 20 Tiingo calls a day, not one per app start."""
    folder = resolve(settings["data"]["cache_dir"]) / "world"
    path = folder / f"{source}-{end.date()}.pkl"
    if path.exists():
        return pd.read_pickle(path)
    prices, errors = fetch()
    if not errors:
        folder.mkdir(parents=True, exist_ok=True)
        pd.to_pickle((prices, errors), path)
    return prices, errors


def _frame(series: dict[str, pd.Series], markets: list[Market]) -> pd.DataFrame:
    frame = pd.DataFrame(series)
    return frame.reindex(columns=[m.id for m in markets if m.id in frame]).sort_index()


def _fetch_tiingo(settings, markets, start, end):
    from .data.tiingo import fetch_tiingo

    env = settings["data"]["tiingo_api_key_env"]
    key = os.environ.get(env)
    if not key:
        raise RuntimeError(f"Set {env} to load world market prices from Tiingo")
    series, errors = {}, {}
    for m in markets:
        try:
            series[m.id] = fetch_tiingo(m.ticker, key, start, end)
        except Exception as exc:  # noqa: BLE001 - one missing ticker must not hide the others
            errors[m.id] = f"{m.ticker}: {exc}"
    return _frame(series, markets), errors


def _fetch_yahoo(markets, start, end):  # pragma: no cover - optional dependency, research use only
    import yfinance as yf

    close = yf.download([m.ticker for m in markets], start=start, end=end, auto_adjust=True)["Close"]
    series = {m.id: close[m.ticker].dropna() for m in markets if m.ticker in close}
    return _frame(series, markets), {m.id: f"{m.ticker}: no data" for m in markets if m.id not in series}


def _fetch_csv(settings, markets, start, end):
    folder = resolve(settings["data"]["csv_dir"]) / "markets"
    series, errors = {}, {}
    for m in markets:
        path = folder / f"{m.ticker}.csv"
        if not path.exists():
            errors[m.id] = f"missing {path} (columns: date,value)"
            continue
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        series[m.id] = frame["value"].loc[start:end].astype(float)
    return _frame(series, markets), errors


# Regional shocks of the simulator, on top of the simulated US market (dates mirror history).
_SHOCKS = [
    ("europe", "2010-04-26", "2010-06-30"),
    ("europe", "2011-07-01", "2011-12-15"),
    ("europe", "2022-02-21", "2022-03-31"),
    ("asia", "2015-06-15", "2016-02-15"),
    ("americas", "2015-05-01", "2016-01-29"),  # hits Brazil and Mexico through their own beta
    ("africa", "2018-04-16", "2018-09-28"),
]


def simulate_markets(markets: list[Market], start, end, seed: int = 42) -> pd.DataFrame:
    """Country prices driven by the simulated US market, a regional factor and their own noise."""
    from .data.synthetic import simulate

    data, _ = simulate(str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date()), seed)
    us = data["equity"]
    r_us = np.log(us).diff().fillna(0.0).to_numpy()
    index = us.index
    rng = np.random.default_rng(seed + 1)
    n = len(index)
    regional = {}
    for region in sorted({m.region for m in markets}):  # fixed order: same draws on every run
        shock = np.zeros(n, dtype=bool)
        for reg, a, b in _SHOCKS:
            if reg == region:
                shock |= (index >= a) & (index <= b)
        vol = np.where(shock, 0.30, 0.07) / np.sqrt(252)
        drift = np.where(shock, -0.45, 0.0) / 252
        regional[region] = drift + vol * rng.standard_normal(n)
    out = {}
    for m in markets:
        if m.vol == 0:
            out[m.id] = us
            continue
        noise = m.vol / np.sqrt(252) * rng.standard_t(5, n) * np.sqrt(3 / 5)
        exposed = 0.6 if m.region == "americas" and m.id not in ("BRA", "MEX") else 1.0
        r = m.beta * r_us + exposed * regional[m.region] + noise + 0.02 / 252
        out[m.id] = pd.Series(50 * np.exp(np.cumsum(r)), index=index)
    return _frame(out, markets)


# ---------------------------------------------------------------- analytics
def indicators(prices: pd.DataFrame, settings: dict) -> dict[str, pd.DataFrame]:
    """Realised vol (annualised), its percentile in the market's own history, drawdown, and state.

    State codes: 0 calm, 1 elevated, 2 stress, NaN while a market has too little history.
    """
    cfg = settings["world"]
    returns = np.log(prices).diff()
    vol = returns.rolling(cfg["vol_window"], min_periods=cfg["vol_window"]).std() * np.sqrt(252)
    vol_pct = vol.rolling(cfg["vol_history_days"], min_periods=cfg["vol_min_history"]).rank(pct=True)
    high = prices.rolling(cfg["drawdown_window"], min_periods=1).max()
    drawdown = prices / high - 1
    s, e = cfg["stress"], cfg["elevated"]
    stress = (vol_pct >= s["vol_percentile"]) & (drawdown <= s["drawdown"])
    elevated = vol_pct >= e["vol_percentile"]
    state = pd.DataFrame(np.where(stress, 2.0, np.where(elevated, 1.0, 0.0)), index=prices.index, columns=prices.columns)
    known = vol_pct.notna() & prices.notna()
    # A new state counts once it has held `confirm_days` days in a row, as for the regime alerts.
    days = cfg["confirm_days"]
    stable = pd.concat([state.shift(k) == state for k in range(days)]).groupby(level=0).all()
    state = state.where(stable & known).ffill().where(known)
    return {"vol": vol, "vol_pct": vol_pct, "drawdown": drawdown, "state": state}


def period_return(series: pd.Series, as_of, horizon: str) -> float:
    """Close-to-close return of one market over `horizon`, ending at the last close on or before `as_of`."""
    s = series.loc[:as_of].dropna()
    if len(s) < 2:
        return float("nan")
    last = s.index[-1]
    if horizon == "1D":
        base = s.iloc[-2]
    else:
        ref = pd.Timestamp(last.year - 1, 12, 31) if horizon == "YTD" else last - _OFFSETS[horizon]
        before = s.loc[:ref]
        if before.empty:
            return float("nan")
        base = before.iloc[-1]
    return float(s.iloc[-1] / base - 1)


def state_since(state: pd.Series, as_of) -> pd.Timestamp | None:
    """First day of the current run of the same state."""
    s = state.loc[:as_of].dropna()
    if s.empty:
        return None
    changes = s.index[s != s.shift()]
    return changes[-1]


def snapshot(prices: pd.DataFrame, ind: dict, markets: list[Market], as_of, horizon: str, stale_days: int = 5) -> pd.DataFrame:
    """One row per market on `as_of`: last close, return over `horizon`, vol, drawdown and state."""
    as_of = pd.Timestamp(as_of)
    rows = []
    for m in markets:
        if m.id not in prices:
            continue
        s = prices[m.id].loc[:as_of].dropna()
        last = s.index[-1] if len(s) else None
        stale = last is None or (as_of - last).days > stale_days
        code = ind["state"][m.id].loc[:as_of].dropna()
        row = {
            "id": m.id,
            "ticker": m.ticker,
            "region": m.region,
            "date": last,
            "close": float(s.iloc[-1]) if len(s) else float("nan"),
            "return": float("nan") if stale else period_return(prices[m.id], as_of, horizon),
            "vol": float(ind["vol"][m.id].loc[:as_of].iloc[-1]) if not stale else float("nan"),
            "vol_pct": float(ind["vol_pct"][m.id].loc[:as_of].iloc[-1]) if not stale else float("nan"),
            "drawdown": float(ind["drawdown"][m.id].loc[:as_of].iloc[-1]) if not stale else float("nan"),
            "state": None if stale or code.empty or code.index[-1] != last else STATES[int(code.iloc[-1])],
            "since": None if stale else state_since(ind["state"][m.id], as_of),
        }
        rows.append(row)
    out = pd.DataFrame(rows).set_index("id")
    # Object columns keep None for "no state" (a string column would turn it into NaN).
    for col in ("state", "since"):
        out[col] = pd.Series([r[col] for r in rows], index=out.index, dtype=object)
    return out


def breadth(state: pd.DataFrame) -> pd.DataFrame:
    """Per day: number of markets with a state, and the share of them in elevated and in stress."""
    known = state.notna().sum(axis=1)
    out = pd.DataFrame(
        {
            "markets": known,
            "elevated": (state == 1).sum(axis=1) / known.replace(0, np.nan),
            "stress": (state == 2).sum(axis=1) / known.replace(0, np.nan),
        }
    )
    return out[known > 0]
