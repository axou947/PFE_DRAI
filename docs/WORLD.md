# World markets tab

The **World markets** tab (`Marchés mondiaux`) shows 20 equity markets on a world map, in two views:

- **Returns**: close-to-close return over 1D, 1W, 1M, 3M, YTD or 1Y.
- **Market stress**: a Calm / Elevated / Stress state for each country, computed from its own prices.

Controls: region zoom (World, Europe, Americas, Asia-Pacific), any date since the data starts, and a
list of past episodes to replay (`replay` in `config/markets.yaml`). Clicking a country (or picking it
in the list) shows its price over 3 years with its stress periods shaded, its last close, return,
21-day volatility, volatility rank and drawdown. A breadth chart shows the share of markets elevated
or in stress over time, next to the US model's stress probability. The full table downloads as CSV.

The same numbers are available from the command line and the API:

```
python -m pfe_drai --provider fred world --date 2020-03-16 --horizon 1M
GET /world?date=2020-03-16&horizon=1M&lang=en
```

## Data: country ETFs, not index levels

Official index levels (S&P 500, CAC 40, DAX, FTSE 100, Nikkei 225, ...) are licensed by their
publishers; the free feeds that carry them (yfinance, stooq) are research-only, and FRED's SP500 is
S&P copyright and starts in 2016. Each market is therefore shown through a **US-listed country ETF**
(iShares MSCI country funds, SPY for the US), read from Tiingo, the source the project already uses.
`config/markets.yaml` lists each ETF, the index it tracks, and the local benchmark it stands in for
(shown as context only).

What this changes, and what the app says on the tab:

- Prices are in **USD**: a return includes the currency move against the dollar.
- Closes are at the **New York close**: for Asia and Australia the local session closed earlier, so
  a "1D" move partly reflects the next local session.
- Tracked indices differ from the local benchmark (MSCI France is not the CAC 40), but they cover the
  same large companies.
- ETFs start at different dates (MCHI 2011, INDA 2012, KSA 2015). Before that a market shows as
  "no data".

Licence: Tiingo's free tier allows 1,000 requests a day (the tab uses about 20, cached once per day
in `data_cache/world/`); internal commercial use is the $50/month plan. **Showing these prices to
clients is redistribution** and needs a separate agreement with Tiingo (and possibly the ETF issuer).

With `--provider synthetic` the prices are simulated: each country follows the simulated US market
(its own beta), a regional factor with scripted regional shocks (euro crisis, China 2015, ...) and
its own noise. They are for demonstration only.

## Market stress state per country

The regime model (stress, growth, inflation) uses US macro data (FRED/ALFRED), so it exists only for
the United States. The other countries have no macro inputs in the project. The state on the map is
therefore **market-only** and says nothing about growth or inflation:

| State | Rule (from the market's own ETF, on each day) |
|---|---|
| Stress | 21-day realised volatility in the top 10% of its own last 5 years **and** drawdown from the 1-year high beyond -10% |
| Elevated | 21-day realised volatility in the top 20% of its own last 5 years |
| Calm | otherwise |

- A new state counts once it has held 3 days in a row (as for the regime alerts).
- Volatility is ranked within each market's own history, so a structurally volatile market (Brazil)
  is not always "elevated" and a quiet one (Switzerland) can still be stressed.
- The thresholds mirror the project's frozen episode rule (-10% drawdown, high volatility), were set
  on 2026-10-01 before looking at any real country data, and are the same for every market. They are
  in `settings.yaml` under `world:` and have not been tuned.
- Everything uses rolling windows only, so the state on a past date is what was knowable that day
  (`tests/test_world.py::test_states_have_no_look_ahead`).
- A market needs one year of volatility history before it gets a state.

This is a descriptive gauge of how stressed each market is, not a forecast and not a buy or sell
signal.

## What it does not do yet

- Returns in local currency (removing the USD effect with FRED daily exchange rates).
- How closely each market moves with the US (rolling correlation, contagion).
- Full macro regimes outside the US: the euro area would need ECB / Eurostat data with release dates
  (point-in-time), the UK ONS data, and the same validation as the US model.
