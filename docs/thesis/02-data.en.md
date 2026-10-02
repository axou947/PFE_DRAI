# Data and point-in-time discipline

## Sources

The real-data setup combines two sources. Macroeconomic series and the VIX come from FRED and ALFRED (Federal Reserve Bank of St. Louis); daily prices of four exchange-traded funds (SPY for US equities, HYG for high-yield credit, LQD for investment-grade credit and IEF for Treasuries) come from Tiingo. Twelve indicators built from them feed three dimension scores (stress, growth, inflation, Chapter 3). The data provider is chosen in `config/settings.yaml`; a synthetic provider and a CSV provider exist for tests and for work without keys. The record used for the results of this report was produced with the provider `{{backtest.current.data_provider}}`.

## Point in time

A backtest is only honest if each day sees what was known on that day. Three rules enforce it.

- **First releases.** Jobless claims, industrial production and the CPI are revised after publication. With the FRED provider, each of these series is read from ALFRED as its *first release*, dated on its release day, so no later revision leaks into the past. Observations older than the ALFRED archive fall back to fixed publication lags (claims {{config.data.publication_lag_days.claims}} days, CPI {{config.data.publication_lag_days.cpi}} days, industrial production {{config.data.publication_lag_days.indpro}} days). Reading today's revised values instead is possible (`data.point_in_time`) and is known to leak the future.
- **Expanding statistics.** Every indicator is a z-score computed on the past only, with at least {{config.features.zscore_min_periods}} observations, clipped at ±{{config.features.zscore_clip|0}}.
- **Walk-forward fitting.** Models are refitted on a growing window using only past days and predict the following period (Chapter 4).

One limit is known and kept: a year-on-year change compares two first releases, not the year-ago figure as it stood revised on that day.

## Coverage

The history is limited by the shortest series. HYG starts in 2007; until its credit measure is available, the investment-grade pair LQD against IEF (from 2002) stands in, standardised on its own past. The 10-year breakeven inflation rate (from 2003) is then the shortest series, so real-data features start in March 2004. The first {{config.validation.min_train_days}} business days (five years) are used for training, so the first out-of-sample prediction falls at the start of the record's period, {{backtest.current.period.start|date}}, and the 2008 crisis is inside the training window and not scored.

## Licences

Data licences shaped the design. The S&P 500 level on FRED is copyrighted and starts in 2016, so SPY is used instead. ICE BofA credit spreads cannot be redistributed and cover only recent years, and Moody's BAA10Y and Yahoo data are limited to research use, so none of them is used. Tiingo's free tier is enough for research, while showing prices to clients would be redistribution and needs a separate agreement. For this reason the public record contains **model outputs, episode dates and drawdowns, never market prices**, and so does this report.

## Simulated data

The synthetic provider follows a regime path that mirrors the main crises since 2000, fills the gaps with a persistent random chain and generates every series from regime-dependent dynamics. The true regime is known, which lets designs be tested where the truth is available. It is also known to overstate the models (the jump model in particular, Chapter 5), so it is used to choose designs and never to claim performance. The daily publication refuses simulated data.
