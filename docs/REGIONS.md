# UK, Japan and emerging markets: data decisions and pre-registration

**Status: pre-registered on 2026-10-03, before any real run of these three regions. Not run yet.**

Three experimental regions are added the way the euro area was ([EURO.md](EURO.md)): `--region uk`, `--region japan` and
`--region em`, each an overlay of `config/settings.yaml` in `config/regions/<region>.yaml`. The US model (v2.2), its frozen
episode rule, its daily publication, its track record and its settings fingerprint are not touched (tested in
`tests/test_regions.py`). This page fixes the data, the episode rule, the model and the numeric decision rule of each region
**before any real run**. Results are added under "Results" as they come out; nothing above that heading changes afterwards. A
failure is published and that region stays labelled experimental.

## Which data, and does it need a new API key?

**No new key.** Every new source is free and key-free; the existing `FRED_API_KEY` and `TIINGO_API_KEY` cover the rest.

| Need | Chosen source | Key | Why |
|---|---|---|---|
| Country equity | Tiingo: EWU, EWJ, EEM (as the world map and the euro area) | Tiingo (have it) | Index levels (FTSE, Nikkei, TOPIX, MSCI) are licensed; ETFs are the free stand-in |
| Local currency | FRED H.10 daily rates DEXUSUK, DEXJPUS | FRED (have it) | Removes the dollar's moves from the UK and Japan series (the euro lesson below) |
| UK gilt yields, breakeven | Bank of England IADB (CSV) | none | Official daily curves, nominal and index-linked |
| Japan JGB yields | Ministry of Finance Japan (CSV) | none | Official daily benchmark yields, 1 to 40 years |
| Industrial production, unemployment, long-term rates | OECD Data Explorer (SDMX), Key Short-Term Economic Indicators | none | One dataset with the same codes for every country; CC BY 4.0 |
| Consumer prices, policy rates | BIS data portal (SDMX) | none | Consumer prices for every country, kept up to date (the OECD and FRED copies of Japan's CPI stopped) |

Alternatives checked on 2026-10-03 and not used:

- **FRED alone.** FRED's international macro series are copies of the OECD's Main Economic Indicators, and several stopped:
  Japan's CPI (`JPNCPIALLMINMEI`) ends in June 2021. FRED has no daily gilt or JGB curve. FRED stays for the exchange rates.
- **The OECD for consumer prices.** Its consumer price index for Japan ends in June 2021 and Mexico's in July 2024 (checked
  2026-10-03); the BIS long series has every country used here up to July or August 2026.
- **e-Stat (Japan's official statistics API).** Free, but needs an application id (`appId`) from a Japanese registration;
  the OECD and BIS copies of the same series need nothing. It is the first fallback if the OECD drops a Japanese series.
- **ONS API (UK official statistics).** Free and key-free, but the OECD copy has the same series under the same codes as the
  other countries, so one parser serves every region. Fallback if the OECD drops a UK series.
- **Bank of Japan time-series API** (key-free since February 2026): no CPI, production, labour or JGB yields in it.
- **Paid vendors** (EODHD, Nasdaq Data Link, LSEG, Bloomberg): would give local index levels and implied volatility (VFTSE, Nikkei
  VI), but their licences forbid showing the data to clients without a redistribution agreement, the problem the audits found
  for index levels. Not worth a key for an experimental view.

The sandbox where the code was written cannot reach any of these servers. Codes and formats were checked against the live
services' documentation and sample answers on 2026-10-03; Phase A (`data`, below) is the real check, and a wrong code stops the
run with the server's message, it never produces silent numbers.

## What was learnt from the euro area, and what changes

The euro area failed its rule on one condition (calibration skill, [EURO.md](EURO.md#results)). Its untested suspects were a
dollar-priced ETF and an alarm that stays on after an episode ends. Without retuning anything the euro run has seen:

1. **UK and Japan equity is in local currency.** EWU and EWJ are converted with the FRED H.10 rate of the same day, so the
   episode rule dates falls of UK and Japanese equities, not of the pound or the yen against the dollar. The H.10 rate is a
   noon New York rate published weekly: a market price known on the day, but the latest few days have no converted price
   until the Fed publishes it.
2. **Emerging markets stay in dollars, on purpose.** There is no single local currency, and emerging-market stress is to a
   large extent currency stress against the dollar (2013, 2015, 2018): a dollar measure is the one an investor in the index has.
3. **No holdout selection.** The euro holdout had 4 episodes and chose the US detector anyway. The three regions take the US
   onset detector as it is (`gbm` on `market` inputs): one degree of freedom fewer, and `holdout` refuses to run for them.
4. **The model is not changed.** The alarm-persistence hypothesis would be a change of the shared model; it is not made here.
   Instead, the three runs test it indirectly (pre-registered reading below).

## What each region reads

The pipeline, features, models and calibration are the US v2.2 ones, unchanged; only the inputs differ. The provider
(`pfe_drai/data/regional.py`, sources in `pfe_drai/data/official.py`) returns the pipeline's column names with each region's
meaning. Every series, code, lag and licence is in the overlay.

### United Kingdom (`--region uk`, `uk-v1`)

| Column | Series | Source | Frequency | Release lag |
|---|---|---|---|---|
| `equity` | EWU in pounds (dollar price / DEXUSUK) | Tiingo, FRED | daily | 0 |
| `vix` | 21-day realised volatility of `equity`, in % | computed | daily | 0 |
| `us10y` | 10-year nominal zero-coupon gilt yield `IUDMNZC` | Bank of England | daily | 1 day |
| `us2y` | 5-year nominal zero-coupon gilt yield `IUDSNZC` (the IADB has no 2-year series) | Bank of England | daily | 1 day |
| `breakeven10` | 10-year nominal minus real (RPI-linked) zero-coupon yield, `IUDMNZC - IUDMRZC` | Bank of England | daily | 1 day |
| `cpi` | Consumer prices, `WS_LONG_CPI` `M.GB.628` | BIS | monthly | 45 days |
| `indpro` | Production volume, industry excl. construction, s.a. (`KEI` `GBR.M.PRVM.IX.BTE.Y._Z`) | OECD | monthly | 60 days |
| `claims` | Unemployment rate, s.a. (`KEI` `GBR.M.UNEMP.PT_LF._T.Y._Z`) | OECD | monthly | 60 days |

Not available: a daily UK credit spread (`credit_stress` is dropped). The UK keeps the two breakeven features, which the euro
area did not have.

### Japan (`--region japan`, `japan-v1`)

| Column | Series | Source | Frequency | Release lag |
|---|---|---|---|---|
| `equity` | EWJ in yen (dollar price x DEXJPUS) | Tiingo, FRED | daily | 0 |
| `vix` | 21-day realised volatility of `equity`, in % (the Nikkei VI is licensed) | computed | daily | 0 |
| `us10y`, `us2y` | JGB benchmark yields, 10 and 2 years (`jgbcme_all.csv` and the current month's `jgbcme.csv`) | Ministry of Finance | daily | 1 day |
| `cpi` | Consumer prices, `WS_LONG_CPI` `M.JP.628` | BIS | monthly | 45 days |
| `indpro` | `KEI` `JPN.M.PRVM.IX.BTE.Y._Z` | OECD | monthly | 60 days |
| `claims` | Unemployment rate, `KEI` `JPN.M.UNEMP.PT_LF._T.Y._Z` | OECD | monthly | 60 days |

Not available: a daily credit spread and a daily breakeven (`credit_stress`, `breakeven_level`, `breakeven_change` dropped).

### Emerging markets (`--region em`, `em-v1`)

One aggregate, as investors hold it: the MSCI Emerging Markets index through EEM, with macro composites of the six largest
economies of that index that publish free monthly data. Weights are the index's country weights, rounded, mid-2025: **China 30,
India 17, Korea 11, Brazil 4, South Africa 3, Mexico 2**. Taiwan (about 18) has no series in these sources and is left out.

| Column | Series | Source | Frequency | Release lag |
|---|---|---|---|---|
| `equity` | EEM, in dollars | Tiingo | daily | 0 |
| `vix` | 21-day realised volatility of EEM, in % (Cboe's VXEEM starts in 2011) | computed | daily | 0 |
| `hy_bond`, `treasury` | EMB (dollar emerging-market sovereign bonds, from December 2007) against IEF | Tiingo | daily | 0 |
| `us10y` | Long-term government yield, composite of the six (`KEI` `IRLT`) | OECD | monthly | 35 days |
| `us2y` | Central bank policy rate, composite of the six (`WS_CBPOL` daily) | BIS | daily | 1 day |
| `cpi` | Consumer prices, composite of the six (`WS_LONG_CPI` `628`) | BIS | monthly | 45 days |
| `indpro` | Industrial production, composite of India, Korea, Brazil, Mexico (China and South Africa publish no index there) | OECD | monthly | 60 days |

Not available: a labour series covering China, India and Brazil (`jobless_claims` dropped, so the growth score averages
`equity_momentum`, `curve_slope` and `industrial_production`) and a breakeven (dropped). The credit series is the US formula
(`credit_stress`, EMB lagging Treasuries over a quarter): it starts in 2009, and the features start with it.

**Composites.** Each month (each day for policy rates), the weighted average of the reporting economies' changes: log changes
for price and production indices, differences for rates. Weights are renormalised over the economies that report; a period
counts only when they carry at least half of the composite's weight (a quarter for the long-term yield, set after Phase A, see
Results), so the latest months do not move on one small economy.
The changes are chained into one series. Its level is arbitrary, which changes nothing: every feature reads changes or expanding
z-scores, and a constant offset does not move a z-score (tested). One query per series serves all six economies (the OECD
allows 60 queries an hour).

### Weaknesses, stated up front

1. **Not point-in-time.** None of the sources exposes first releases. Monthly series are dated by the end of their month plus a
   conservative lag, so no value is used before it could have been public, but **industrial production and unemployment are
   revised and the backtests see revised values**. Daily market series are not revised.
2. **Realised, not implied, volatility** in all three regions: the stress score weighs realised volatility twice (as the euro).
3. **No credit series for the UK and Japan.** Their stress score reads volatility and drawdown only.
4. **The UK short rate is a 5-year yield**, so the UK curve slope is 10y-5y and the "2-year" change is a 5-year change.
5. **Japan's yields were held near zero** (2016-2024 yield-curve control): the curve slope and the short-rate change carry
   little information over those years.
6. **Emerging markets are a composite** with fixed weights that are not the weights of every past year, without Taiwan, and
   with a growth score of three inputs.
7. **Timing.** The ETFs close in New York, after London and Tokyo; the H.10 rate is a noon New York rate.

## The episode rule (frozen)

The US rule's **parameters, unchanged**, applied to each region's `equity` series (pounds, yen, EEM in dollars). No new degree
of freedom; the sha256 is the US one, `6741b6747b53b7cf5c1f9de0c5fedd9caccd111d49c9dbf63fde3a2010b8397a`, frozen in each overlay on
its own (`validation.episodes.frozen`, 2026-10-03). The dated episodes of these regions have **not** been looked at.

## Regimes and models

The same three dimensions, `regimes.rule` with the US values, the v2.2 growth score, the v2.2 model chain (jump + gbm + onset,
calibrated P(stress)) and the US onset detector (`gbm` on `market`), unchanged. Nothing is tuned on these regions' data.

## Decision rule (numeric, fixed before any real run)

The euro area's seven conditions, unchanged, applied to each region on its own. One real run per region:
`backtest`, then `calibration` and `states` on the same data. A region **passes** only if every condition holds for the default
(`combined`) model on its out-of-sample days:

1. at least 6 episodes are dated by the frozen rule (fewer = inconclusive, not a pass);
2. at least 80% of the episodes are detected;
3. median detection latency over detected episodes at most 5 business days;
4. at most 1.5 false alarms a year;
5. at most 10% of calm days with the alarm on;
6. calibrated P(stress): ECE at most 0.08 and Brier below that of always predicting the observed frequency (skill > 0);
7. a Slowdown state is named in at least half of the walk-forward refits (`states`).

A region that passes may be published daily in `track_record/<region>/` (a separate PR switches its `publish.enabled` and adds
a `continue-on-error` step to `.github/workflows/publish.yml`, so a regional failure cannot cost the US day). A region that
fails stays experimental; its results are published here and its episodes are then "seen".

**Pre-registered reading across regions.** If at least two of the three regions meet conditions 1 to 5 and fail condition 6,
as the euro area did, the calibration of the shared model, not each region's data, is the likely cause. That would be the stated
reason for a separate pre-registration of the calibrator (for instance the alarm-persistence hypothesis), tested on regions
not used to find it. If condition 6 holds in the UK and Japan in local currency, the dollar-priced ETF becomes the more likely
euro cause.

## Procedure (Henry, Windows PowerShell, in this order)

`FRED_API_KEY` and `TIINGO_API_KEY` must be set in the session (they already are for the US commands). No other key.

1. **Phase A, coverage only, no model.** For each region:
   `python -m pfe_drai --region uk data`, `python -m pfe_drai --region japan data`, `python -m pfe_drai --region em data`.
   Each prints, per series, its first and last day, release lag, licence and what it was read from (codes, and for each
   economy of a composite its last period). Paste the three outputs: coverage goes below, before any model is run.
2. **Once per region:** `python -m pfe_drai --region <region> backtest`, then `calibration`, then `states`. Results below.

## Results

### Phase A: coverage, run by Henry on 2026-10-03 (no model, before any real run)

Every code in the overlays answered on the first run.

| Region | Series | First | Last | Read from |
|---|---|---|---|---|
| UK | equity (EWU in pounds), vix | 1996-04-01 | 2026-09-25 | Tiingo EWU, FRED DEXUSUK |
| UK | us10y, us2y, breakeven10 | 1996-04-02 | 2026-10-01 | BoE IUDMNZC, IUDSNZC, IUDMNZC - IUDMRZC |
| UK | cpi | 1996-04-14 | 2026-10-15 | BIS M.GB.628, last period 2026-08 |
| UK | indpro, claims | 1996-04-29 | 2026-09-29, 2026-08-29 | OECD KEI GBR, last periods 2026-07, 2026-06 |
| Japan | equity (EWJ in yen), vix | 1996-04-01 | 2026-09-25 | Tiingo EWJ, FRED DEXJPUS |
| Japan | us10y, us2y | 1996-04-02 | 2026-10-02 | MoF JGB 10Y, 2Y |
| Japan | cpi | 1996-04-14 | 2026-09-14 | BIS M.JP.628, last period 2026-07 |
| Japan | indpro, claims | 1996-04-29 | 2026-09-29, 2026-10-30 | OECD KEI JPN, last periods 2026-07, 2026-08 |
| EM | equity (EEM), vix, treasury (IEF) | 2003-04-14 | 2026-10-02 | Tiingo |
| EM | hy_bond (EMB) | 2007-12-19 | 2026-10-02 | Tiingo |
| EM | us2y (policy rates) | 2003-04-14 | 2026-09-30 | BIS WS_CBPOL, last days CN, BR, MX 2026-09-29, ZA 09-28, KR 08-28, IN 07-23 |
| EM | cpi | 2003-04-14 | 2026-10-15 | BIS, last periods 2026-07 or 2026-08 |
| EM | indpro | 2003-04-29 | 2026-09-29 | OECD KEI IND, KOR, BRA, MEX, last period 2026-07 |
| EM | us10y (long-term yields) | 2012-02-04 | 2026-11-04 | OECD KEI IRLT, first periods BRA, KOR, MEX, ZAF 2002-01, IND 2011-12, CHN 2014-01 |

UK and Japan: features from 1998-05-04, out-of-sample from 2003-05-21. The equity series end a week early: the FRED H.10
rate is published weekly (expected, Weaknesses 7).

**One change after Phase A, before any model run.** At half the composite's weight, the emerging-market long-term yield only
started in February 2012 (India's series starts in 2011-12, China's in 2014-01), which put the features in 2013 and the
out-of-sample period in 2018, without the 2013, 2015 and 2016 emerging-market episodes. The long-term yield composite now counts
a month when a quarter of its weight reports (`min_weight: 0.25` in the overlay): Korea, Brazil, South Africa and Mexico carry it
from 2002, India and China join when their series start. Only coverage was seen, no episode, alarm or score. The other
composites keep half. The EM coverage after this change is to be re-run with `data` before the backtest; EMB (December 2007) then
binds, so features should start around 2009 and the out-of-sample period around 2014.

### Real backtests

Not run yet.
