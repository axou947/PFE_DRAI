# Your own portfolio in Scenarios

The Scenarios tab measured the historical stress scenarios on three model funds only
(config/funds.yaml). It now also takes your own weights: paste them or upload a CSV, and the
impact of every scenario in the library is shown, ranked by how close it is to today's regime,
with the contribution of each holding.

## Kept in memory only

- The app reads the pasted text or uploaded file on each run, in memory. Nothing is written to
  disk, cached (no `st.cache_*`), logged, stored in the track record or published. Closing the
  page forgets it.
- `POST /scenarios/portfolio` reads the CSV from the request body and returns the result; it
  writes nothing.
- `python -m pfe_drai scenarios --portfolio file.csv` reads the file and prints the result.
- The committee note can include your weights, but only if you download it yourself.

No model, setting or published entry changes: the settings fingerprint is unchanged.

## Format

One row per holding. Comma, semicolon (French Excel) or tab separated; header optional.

```csv
holding,asset_class,weight
MSCI World ETF,equity_world,40
Euro STOXX 50 ETF,equity_europe,10
Euro government bonds,gov_bonds,25
Corporate bonds,ig_credit,15
Gold ETC,gold,5
Money market,cash,5
```

```csv
ligne;classe_d_actif;poids
Amundi MSCI World;Actions monde;55,5
Or physique;Or;4,5
Fonds euros;Monétaire;40
```

| Column | Header names read | Required |
|---|---|---|
| holding | holding, name, nom, ligne, titre, ticker, isin, fund, fonds, position | no (the class is used as the name) |
| asset class | asset_class, asset, class, classe, classe_d_actif, actif, category | yes |
| weight | weight, poids, pct, percent, allocation, share, part (else the last column) | yes |

Without a header: 2 columns = class, weight; 3 columns = holding, class, weight.

**Asset classes** are the ones the scenarios carry a shock for (config/scenarios.yaml):
`equity_world`, `equity_europe`, `gov_bonds`, `ig_credit`, `hy_credit`, `gold`, `commodities`, `cash`.
The French and English names shown in the app work too ("Actions monde", "Government bonds"),
as do a few common aliases (govies, treasuries, high yield, haut rendement, or, liquidités,
money market...). Several holdings of the same class add up.

**Weights** are percent summing to 100, or fractions summing to 1. "40 %", "40,5" and "40.5" are
read. A rounding gap of up to half a point (e.g. 100.2) is spread across the holdings pro rata
and said in a warning; anything further is an error.

## Errors

Every problem is listed at once, with its line, in French or English:

- unknown asset class (the accepted list follows), empty class;
- stock without a ticker, malformed ticker, ticker Tiingo does not know, too short a history;
- weight that is not a number, negative weight (short positions are not handled);
- weights not summing to 100 or 1;
- no asset-class or weight column in the header;
- a number read as an asset class, which usually means decimal commas with a comma separator:
  use semicolons;
- empty file, more than 500 rows, larger than 200 KB.

## Single stocks

A row with class `stock` (or `action`, `shares`, `titre vif`) and a ticker is priced from its own
history instead of a class shock:

```csv
holding,asset_class,ticker,weight
MSCI World ETF,equity_world,,40
Apple,stock,AAPL,10
Tesla,stock,TSLA,10
Euro government bonds,gov_bonds,,30
Gold ETC,gold,,5
Money market,cash,,5
```

- The ticker comes from a `ticker` (or `symbol`) column; without one, a holding name written as a
  ticker (`AAPL`) is taken as the ticker. Headerless 4 columns = holding, class, ticker, weight.
- **Listed before the scenario**: the actual total return over the window, from Tiingo adjusted
  closes (dividends and splits included), close before the start to close on the end date.
- **Listed later** (Tesla in 2000 or 2008): an estimate, beta to the S&P 500 (SPY) from daily
  returns over the last two years x the SPY return over the window. Marked ≈ in the per-holding
  table and listed in the "Single stocks" table. It keeps only the market part of the move: what was
  specific to the company, its sector or its size then is not in it.
- Real data only (`--provider fred` or `tiingo`) and the Tiingo key (TIINGO_API_KEY). On simulated
  data, or without the key, the app says so.
- Tiingo covers US listings and ADRs. A non-US stock goes through its US listing or ADR (LVMUY for
  LVMH, TTE for TotalEnergies); an unknown ticker is reported by name.
- A stock with less than six months of prices cannot be estimated and is reported.
- Only the tickers go to Tiingo, never the weights. Prices are kept for the browser session in
  memory (st.session_state), never on disk.

## What the number means

Impact = sum over holdings of weight x the indicative shock of the holding's asset class over the
scenario window. A fund is treated as its whole asset class, not as itself; a single stock given
with class `stock` takes its own move (above). The shocks are indicative (see config/scenarios.yaml) and the
result describes what those past episodes did to such a mix; it is not a forecast or advice.
