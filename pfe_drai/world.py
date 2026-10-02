"""World markets: country equity ETFs, their returns and a market-only stress state (docs/WORLD.md).

The regime model (stress, growth, inflation) is built on US macro data, so it is US-only.
For the other countries we only have market prices, so each one gets a transparent market
stress state computed from its own ETF, with the same thresholds everywhere:

    stress    21-day realised vol in the top 10% of its own last 5 years AND drawdown <= -10%
    elevated  21-day realised vol in the top 20% of its own last 5 years
    calm      otherwise

A new state is confirmed once it has held `world.confirm_days` days in a row.

Everything is computed from data available on the day (rolling windows, no look-ahead).

Two display-only extras sit on top, neither of which touches the states:

    local currency   returns, volatility and the currency's own share, from FRED H.10 exchange rates
    link to the US   rolling beta and correlation of each market with the US (SPY), on 5-day returns
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
    fx: dict | None = None  # {series, quote: per_usd|usd_per, vol} or {peg: local per USD}; None = USD


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


# ---------------------------------------------------------------- currency
CURRENCIES = ["usd", "local"]


def _fx_series(markets: list[Market]) -> dict[str, str]:
    """{FRED series id: quote} for the markets that have one (several markets can share a series)."""
    return {m.fx["series"]: m.fx.get("quote", "per_usd") for m in markets if m.fx and "series" in m.fx}


def fetch_fx(settings: dict, provider: str | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Daily exchange rates as local currency per USD, one column per market id, and {market id: error}.

    The rates are the Fed's H.10 noon buying rates in New York (FRED), published weekly: the latest
    days are usually missing. Nothing is carried forward here (see `local_view`). Markets in USD or
    with a peg have no column. Synthetic data simulates currencies; csv reads <csv_dir>/fx/<SERIES>.csv.
    """
    provider = provider or settings["data"]["provider"]
    markets = load_markets(settings)
    start, end = _period(settings)
    if provider == "synthetic":
        return simulate_fx(markets, start, end, settings["data"]["seed"]), {}
    if provider in ("fred", "tiingo"):
        return _cached(settings, "fx", end, lambda: _fetch_fred_fx(settings, markets, start, end))
    if provider == "csv":
        return _fetch_csv_fx(settings, markets, start, end)
    err = f"no exchange rates for provider '{provider}'"
    return pd.DataFrame(), {m.id: err for m in markets if m.fx and "series" in m.fx}


def _per_usd(rates: pd.Series, quote: str) -> pd.Series:
    return 1.0 / rates if quote == "usd_per" else rates


def _by_market(markets: list[Market], raw: dict[str, pd.Series], errors: dict[str, str]):
    series, failed = {}, {}
    for m in markets:
        if not (m.fx and "series" in m.fx):
            continue
        sid = m.fx["series"]
        if sid in raw:
            series[m.id] = _per_usd(raw[sid], m.fx.get("quote", "per_usd"))
        else:
            failed[m.id] = f"{sid}: {errors.get(sid, 'no data')}"
    return _frame(series, markets), failed


def _fetch_fred_fx(settings, markets, start, end):
    from .data.fred import fetch_fred

    env = settings["data"]["fred_api_key_env"]
    key = os.environ.get(env)
    if not key:
        raise RuntimeError(f"Set {env} to load exchange rates from FRED (local-currency returns)")
    raw, errors = {}, {}
    for sid in _fx_series(markets):  # one download per series: the euro covers five markets
        try:
            raw[sid] = fetch_fred(sid, key, start, end)
            if raw[sid].empty:
                raise ValueError("no observations")
        except Exception as exc:  # noqa: BLE001 - one missing series must not hide the others
            raw.pop(sid, None)
            errors[sid] = str(exc)
    return _by_market(markets, raw, errors)


def _fetch_csv_fx(settings, markets, start, end):
    folder = resolve(settings["data"]["csv_dir"]) / "fx"
    raw, errors = {}, {}
    for sid in _fx_series(markets):
        path = folder / f"{sid}.csv"
        if not path.exists():
            errors[sid] = f"missing {path} (columns: date,value)"
            continue
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
        raw[sid] = frame["value"].loc[start:end].astype(float).dropna()
    return _by_market(markets, raw, errors)


def simulate_fx(markets: list[Market], start, end, seed: int = 42) -> pd.DataFrame:
    """Random-walk currencies (local per USD) with each series' own volatility, for demos and tests.

    They are independent of the simulated equities: they show how the toggle works, not how real
    currencies behave in a crisis.
    """
    from .data.synthetic import simulate

    data, _ = simulate(str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date()), seed)
    index = data["equity"].index
    rng = np.random.default_rng(seed + 2)
    walks = {}
    for sid in sorted(_fx_series(markets)):  # fixed order: same draws on every run
        vol = next(m.fx.get("vol", 0.08) for m in markets if m.fx and m.fx.get("series") == sid)
        walks[sid] = np.exp(np.cumsum(vol / np.sqrt(252) * rng.standard_normal(len(index))))
    out = {m.id: pd.Series(walks[m.fx["series"]], index=index) for m in markets if m.fx and "series" in m.fx}
    return _frame(out, markets)


def fx_rates(fx: pd.DataFrame, markets: list[Market], index: pd.DatetimeIndex, fill_days: int) -> pd.DataFrame:
    """Local per USD on the ETF's trading days, one column per market (a USD market has a constant 1).

    A rate is carried over a gap of at most `fill_days` trading days (Fed holidays that are not NYSE
    holidays) and **never past the last published date**: beyond it the rate is missing, not repeated.
    """
    out = {}
    for m in markets:
        if m.fx is None:
            out[m.id] = pd.Series(1.0, index=index)
        elif "peg" in m.fx:
            out[m.id] = pd.Series(float(m.fx["peg"]), index=index)
        elif m.id in fx:
            raw = fx[m.id].dropna()
            aligned = raw.reindex(raw.index.union(index)).ffill(limit=fill_days).reindex(index)
            out[m.id] = aligned.where(aligned.index <= raw.index[-1]) if len(raw) else pd.Series(np.nan, index=index)
        else:
            out[m.id] = pd.Series(np.nan, index=index)
    return pd.DataFrame(out, index=index)


def _window(series: pd.Series, as_of, horizon: str):
    """(base date, last date) of the close-to-close window `period_return` uses, or None."""
    s = series.loc[:as_of].dropna()
    if len(s) < 2:
        return None
    last = s.index[-1]
    if horizon == "1D":
        return s.index[-2], last
    ref = pd.Timestamp(last.year - 1, 12, 31) if horizon == "YTD" else last - _OFFSETS[horizon]
    before = s.loc[:ref]
    return (before.index[-1], last) if len(before) else None


def local_view(
    prices: pd.DataFrame, rates: pd.DataFrame, markets: list[Market], as_of, horizon: str, vol_window: int
) -> pd.DataFrame:
    """Local-currency view on `as_of`, one row per market: display values only, the states stay in USD.

    local price = USD price x local per USD, on the same date. So local return = (1 + USD return)
    x rate(last close) / rate(base close) - 1, and `currency` = USD return - local return, exactly.
    A market whose rate is not published for the last close (or the base) has NaN and
    `fx_status` "pending", never an older or repeated value. Statuses: ok, usd (no conversion
    needed or pegged), pending (FX not yet published), missing (no rate series loaded).
    """
    as_of = pd.Timestamp(as_of)
    rows = {}
    for m in markets:
        if m.id not in prices:
            continue
        usd = period_return(prices[m.id], as_of, horizon)
        win = _window(prices[m.id], as_of, horizon)
        r = rates[m.id].loc[:as_of] if m.id in rates else pd.Series(dtype=float)
        has_series = m.fx is not None and "series" in m.fx
        status = "usd" if not has_series else "ok"
        if win is None:
            local = float("nan")
        else:
            base, last = win
            r_last, r_base = r.get(last, np.nan), r.get(base, np.nan)
            local = float((1 + usd) * r_last / r_base - 1) if r_last == r_last and r_base == r_base else float("nan")
            if local != local and has_series:
                status = "missing" if (m.id not in rates or rates[m.id].isna().all()) else "pending"
        lp = np.log(prices[m.id] * rates[m.id]) if m.id in rates else pd.Series(dtype=float)
        vol = lp.diff().rolling(vol_window, min_periods=vol_window).std() * np.sqrt(252) if len(lp) else lp
        v = vol.loc[:as_of]
        # Volatility only when the rate covers the same last close as the price.
        last_close = prices[m.id].loc[:as_of].dropna().index[-1:]
        v_last = float(v.get(last_close[0], np.nan)) if len(last_close) else float("nan")
        rows[m.id] = {
            "return_local": local,
            "currency": usd - local if local == local else float("nan"),
            "vol_local": v_last,
            "fx_status": status,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


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


# ---------------------------------------------------------------- link to the US
@dataclass(frozen=True)
class LinkStats:
    """Rolling measures of how closely each market moves with the US (SPY), by window in business days.

    `corr`, `beta`, `corr_1d`, `follows` and `leads` are {window: frame}; the others use the stress window.
    """

    corr: dict
    beta: dict
    corr_1d: dict
    follows: dict  # corr(market today, US yesterday): the market follows the US with a day's delay
    leads: dict  # corr(market yesterday, US today): the market moves a day before the US
    corr_stress: pd.DataFrame
    corr_calm: pd.DataFrame
    stress_days: pd.DataFrame
    avg_corr: dict  # {window: mean correlation of the other markets with the US}


def link_to_us(prices: pd.DataFrame, ind: dict, settings: dict) -> LinkStats:
    """Beta and correlation with the US on overlapping 5-day log returns (the headline), plus 1-day checks.

    Weekly returns because Asian and Australian ETFs trade in New York hours but track a session that
    closed earlier: same-day correlation with SPY is biased low and a lag shows up (see follows/leads).
    Every value on a day uses only returns up to that day.
    """
    cfg = settings["world"]["link"]
    logp = np.log(prices)
    r1, rk = logp.diff(), logp.diff(cfg["return_days"])
    us1, usk = r1["USA"], rk["USA"]

    def need(w):  # a window counts once 90% of it holds a return pair
        return int(np.ceil(w * cfg["min_share"]))

    corr, beta, corr_1d, follows, leads, avg = {}, {}, {}, {}, {}, {}
    others = [c for c in prices.columns if c != "USA"]
    for w in cfg["windows"]:
        corr[w] = rk.rolling(w, min_periods=need(w)).corr(usk).clip(-1, 1)  # clip: float noise, e.g. 1.0000000002
        beta[w] = rk.rolling(w, min_periods=need(w)).cov(usk).div(usk.rolling(w, min_periods=need(w)).var(), axis=0)
        corr_1d[w] = r1.rolling(w, min_periods=need(w)).corr(us1).clip(-1, 1)
        follows[w] = r1.rolling(w, min_periods=need(w)).corr(us1.shift(1)).clip(-1, 1)
        leads[w] = r1.shift(1).rolling(w, min_periods=need(w)).corr(us1).clip(-1, 1)
        mean = corr[w][others].mean(axis=1)
        avg[w] = mean.where(corr[w][others].notna().sum(axis=1) >= cfg["min_markets"])

    # Same measure on the days the US market is in stress, and on the other days (window: stress_window).
    us_state = ind["state"]["USA"]
    sw, floor = cfg["stress_window"], cfg["min_stress_days"]

    def on(mask):
        x = rk.copy()
        x.loc[~mask.to_numpy(), :] = np.nan
        return x.rolling(sw, min_periods=floor).corr(usk.where(mask)).clip(-1, 1), mask.rolling(sw, min_periods=1).sum()

    stress_mask = us_state == 2
    calm_mask = us_state.isin([0, 1])
    corr_stress, n_stress = on(stress_mask)
    corr_calm, _ = on(calm_mask)
    # Too few stress days in the window: no number rather than a noisy one.
    corr_stress = corr_stress.mul(np.where(n_stress >= floor, 1.0, np.nan), axis=0)
    stress_days = pd.DataFrame({c: n_stress for c in prices.columns})
    return LinkStats(corr, beta, corr_1d, follows, leads, corr_stress, corr_calm, stress_days, avg)


def link_snapshot(
    stats: LinkStats, markets: list[Market], prices: pd.DataFrame, as_of, window: int, stale_days: int = 5
) -> pd.DataFrame:
    """One row per market on `as_of` (US included, correlation 1): the link measures for `window`."""
    as_of = pd.Timestamp(as_of)
    cols = {
        "corr": stats.corr[window],
        "beta": stats.beta[window],
        "corr_1d": stats.corr_1d[window],
        "follows": stats.follows[window],
        "leads": stats.leads[window],
        "corr_stress": stats.corr_stress,
        "corr_calm": stats.corr_calm,
        "stress_days": stats.stress_days,
    }
    rows = {}
    for m in markets:
        if m.id not in prices:
            continue
        last = prices[m.id].loc[:as_of].dropna().index[-1:]
        stale = len(last) == 0 or (as_of - last[0]).days > stale_days
        rows[m.id] = {k: float("nan") if stale else float(f.loc[:as_of, m.id].iloc[-1]) for k, f in cols.items()}
        if m.id == "USA":  # a market's lead or lag against itself is its own autocorrelation: not shown
            rows[m.id].update(follows=float("nan"), leads=float("nan"))
    return pd.DataFrame.from_dict(rows, orient="index")
