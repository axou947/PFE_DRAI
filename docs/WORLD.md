# World markets tab

The **World markets** tab (`Marchés mondiaux`) shows 20 equity markets on a world map, in three views:

- **Returns**: close-to-close return over 1D, 1W, 1M, 3M, YTD or 1Y, in USD or in local currency.
- **Market stress**: a Calm / Elevated / Stress state for each country, computed from its own prices.
- **Link to the US**: how closely each market moves with the US (rolling correlation or beta against SPY).

Controls: region zoom (World, Europe, Americas, Asia-Pacific), any date since the data starts, and a
list of past episodes to replay (`replay` in `config/markets.yaml`). Clicking a country (or picking it
in the list) shows its price over 3 years with its stress periods shaded, its last close, return,
21-day volatility, volatility rank and drawdown. A breadth chart shows the share of markets elevated
or in stress over time, next to the US model's stress probability. The full table downloads as CSV.

The same numbers are available from the command line and the API:

```
python -m pfe_drai --provider fred world --date 2020-03-16 --horizon 1M
python -m pfe_drai --provider fred world --date 2020-03-16 --horizon 1M --currency local --link --window 63
GET /world?date=2020-03-16&horizon=1M&lang=en           (add &currency=local for local currency)
GET /world/link?date=2020-03-16&window=252&lang=en
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

- Full macro regimes outside the US: the euro area would need ECB / Eurostat data with release dates
  (point-in-time), the UK ONS data, and the same validation as the US model.

## Local-currency returns (display only)

Toggle **Currency: USD / Local currency** on the Returns view (default USD, unchanged), `--currency local`
on the CLI, `GET /world?currency=local` on the API (adds `return_local`, `currency`, `vol_local`,
`fx_status` per market; `return` and the state stay in USD).

- **Source**: FRED H.10 daily exchange rates, a Federal Reserve release (free; cite the source; the
  usual FRED notice applies). Series per market are in `config/markets.yaml` (`fx:`), including the
  quote direction (`per_usd` or `usd_per`; GBP, EUR and AUD are quoted as USD per unit and inverted).
  The five euro markets share `DEXUSEU`. The Saudi riyal is pegged (3.75 per USD): no currency effect.
  Needs `FRED_API_KEY`; downloaded once a day into `data_cache/world/`, one request per series.
- **Maths**: local price = USD price x local per USD on the same date, so
  `local return = (1 + USD return) x rate(last close) / rate(base close) - 1` and
  `currency effect = USD return - local return`, exactly. The tab also shows 21-day volatility in local
  currency. These are display values: the stress state keeps its USD definition (changing it would be a rule change).
- **Timing approximation**: H.10 rates are noon buying rates in New York, the ETF closes at 16:00 New York time.
  Close enough for a 1-day to 1-year return, but not an exact close-to-close conversion.
- **Freshness trap**: the Fed publishes H.10 **weekly**, so the latest days have no rate. They are shown
  blank ("FX rates not yet published"), **never forward-filled**. Only a gap of at most `world.fx_fill_days`
  (2) trading days inside the series is carried (Fed holidays that are not NYSE holidays, such as Columbus Day).
- **Before the first real run**: the series ids were written from the H.10 release table without being able
  to query FRED from the build environment. Any id FRED rejects is reported as "FX not loaded" for its
  markets (the rest still work), so the first run checks them. Euro-only alternative later: ECB euro
  reference rates (daily); its terms of use would need checking first.
- Synthetic mode simulates one random-walk currency per series (volatility in `fx.vol`), independent of the
  simulated equities, labelled simulated like the rest.

## Link to the US ("moves with")

Windows and rules were fixed on **2026-10-02, before any real number was looked at**, in `world.link`:

| Setting | Value |
|---|---|
| Headline return | overlapping **5-day** log returns (ETFs of Asia and Australia track a session already closed) |
| Windows | **63** (about a quarter) and **252** business days (a year), selectable on the tab |
| Valid window | at least 90% of it holds a return pair |
| Stress vs other days | over the last **1260** days (5 years), split by the **US market stress state** (SPY, the same rule as every country); needs **20** US stress days or the value is blank |
| Average line | mean correlation of the 19 other markets with the US, at least 5 markets |

- Measures per market: correlation, beta (covariance with SPY over the variance of SPY), the same two in
  US-stress days and in other days, and on **daily** returns the same-day correlation, the correlation of
  the market with the US of the previous day ("follows the US by a day") and with the US of the next day
  ("moves a day before"). Those two lag values include the same-day link times the US's own
  autocorrelation, so read them as a comparison between markets, not as a causal delay.
- Everything uses returns up to the day shown only (`tests/test_world.py::test_link_has_no_look_ahead`).
  The US row shows correlation 1 and beta 1; it is left out of the average.
- Overlapping 5-day returns make neighbouring days correlated: the numbers are descriptive, and their
  usual standard errors would be too small. No significance claim is made.
- Wording is "moves with", never "is driven by"; nothing here is a forecast, a signal or a causal claim.
  The chart extends the breadth chart with the average correlation and shades the US stress periods:
  correlations tend to rise in crises. Any lead-lag between breadth and the US stress probability is
  not in the app (it would be exploratory, and would need its own note with the number of observations).
- **Real values to record after the first real run**: average correlation of the 19 markets with the US in
  2019 versus March 2020 (63-day window). Not run yet.

## Real-data check (2026-10-01)

Run once on real data (Tiingo, all 20 ETFs loaded), thresholds unchanged:
`python -m pfe_drai --provider fred world --date 2020-03-16`.

- All 20 markets in **Stress** on 2020-03-16, 0 elevated. Each one's 21-day vol ranked at 100% of
  its last 5 years, with drawdowns from -22% (China) to -54% (Brazil) and 1-month returns from -19%
  to -49% in USD.
- The states began between 2020-02-26 (South Korea, the first market hit by Covid) and 2020-03-16
  (China). The US entered Stress on 2020-03-09.
- Brazil (vol 144%) and Australia (109%) show how much the USD amplifies local moves.
