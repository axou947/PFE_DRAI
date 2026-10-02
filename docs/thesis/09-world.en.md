# World markets

## What it is

The regime model needs US macroeconomic data, so it exists only for the United States. The world-markets view is a separate, simpler tool: for 20 country equity markets it shows returns over a chosen horizon, a market-only stress state, and how closely each market moves with the United States. It is **descriptive**. It has none of the validation of Chapters 4 to 7: no episode latency, no false-alarm rate, no probability.

## Data

Official index levels are licensed, so each market is read through a US-listed country ETF from Tiingo (the same source as the US model), with SPY for the United States. Prices are therefore in dollars and include the currency move, closes are at the New York close (for Asia and Australia the local session closed earlier), the tracked indices differ from the local benchmarks, and ETFs start at different dates. A local-currency view converts with the Federal Reserve's H.10 exchange rates read from FRED, which are weekly, so the latest days are not available in local currency.

## Market stress state

The state of a market is computed from its own prices only, with rolling windows (no look-ahead, tested):

- **Stress**: 21-day realised volatility in the top {{config.world.stress.vol_percentile|pct0}} of its own last five years *and* a drawdown from the 1-year high beyond {{config.world.stress.drawdown|pct0}};
- **Elevated**: volatility in the top {{config.world.elevated.vol_percentile|pct0}} of its own last five years;
- **Calm** otherwise.

A new state counts once it has held {{config.world.confirm_days}} days in a row. The thresholds mirror the frozen episode rule, were set on 2026-10-01 before any real country data was looked at, are the same for every market and have not been tuned. Volatility is ranked within each market's own history, so a structurally volatile market is not always elevated.

## The link to the United States

For each market the view shows the correlation and beta against SPY on overlapping {{config.world.link.return_days}}-day returns over windows of {{config.world.link.windows.0}} and {{config.world.link.windows.1}} business days, the correlation on days when the United States is in stress against the other days, and partial lead and lag terms. These settings were fixed on 2026-10-02 before any real number was looked at.

## Real-data checks

The only checks on real data are sanity checks, run once each and published as they came out.

{{quote:WORLD.md#Real-data check (2026-10-01)}}

{{quote:WORLD.md#Real-data check (2026-10-02): local currency and link to the US}}

The first check shows the expected behaviour (every market in stress in March 2020, the first one hit being South Korea) and the second shows the usual rise of correlations in crises (the average correlation of the other 19 markets with the United States rose between a calm autumn 2019 and the March 2020 crash). They show that the view behaves sensibly. They are not a validation: the report makes no claim that these states predict anything, and the lead and lag columns are read in calm periods, not as a crisis measure.
