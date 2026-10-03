# Learn pages: beginner and professional

Two tabs teach the same economics at two depths. **Learn (beginner)** uses plain words and analogies; **Learn (pro)** adds
formulas, the mechanics, the caveats and reading lists. Until the app has user accounts, the visitor picks the tab. Both tabs
share each concept's key points, live indicators and links, so a beginner who moves to the pro tab finds the same story with
more depth, never a different one.

US only for now. Other zones show a note and keep their other tabs.

## What is on the page

| Section | Beginner | Pro |
|---|---|---|
| **Today** | the US economy on the analysis date: key indicators with their 3- and 12-month change, trend and rank in their own history; the Fed's next meeting and the odds of a cut, hold or hike; six recession warning lights | same, plus the implied rate path, every Taylor rule, the nearest historical months and the split by our regime |
| **Concepts** | 26 cards (16 macro, 7 micro, 3 on our model): what it is, why it can be good, why it can be bad, what usually comes next, with today's readings and a chart | same cards plus the mechanics (equations) and reading list |
| **Map** | cause and effect between the concepts; cards at an extreme of their history today are highlighted | same, with the label of each link |
| **History** | 16 episodes from the 1973 oil shock to the 2023 bank failures, on one timeline of the Fed's rate; the past episodes whose start looks most like the analysis date; for each: what happened, what the Fed did, the lesson, a dated timeline, the episode's numbers from FRED (rate path, inflation and unemployment peaks, VIX, months of recession) and its starting conditions next to today's | same, plus the curve and oil, what economists still debate, what our regime model said (from 2004) and a reading list |
| **Lab** | five tabs: Fed rule (Taylor calculator); rates and bonds (real rate, bond price when rates move, recession odds from the yield curve); household (mortgage, what a past dollar is worth today, real pay rise); public debt (debt path from deficit, interest and growth) | same, plus u* and r* sliders and the rules' history, bond coupon, duration and convexity, the curve model's monthly history, the debt-stabilising primary balance and the Phillips curve |
| **Glossary** | about 50 terms, searchable, linked to their card | pro definitions |
| **Quiz** | one question per card, with the explanation | pro questions |
| **Ask GAMA** | GAMA, the AI tutor: the question box and examples are there, but **the tutor is under construction**: clicking shows "coming soon" and sends nothing anywhere | same |

The dashboard has an "Understand this regime" button that opens the card explaining today's regime in both tabs. The sidebar
date works here too: pick a past day to see what the page would have said then (with today's data vintages, see Limits).

Every text is written in advance and reviewed, in French and English, in `config/learn/` (cards, glossary, episodes). Nothing
is generated on the fly.

## Data

Everything comes from **FRED** with the existing `FRED_API_KEY`: no new key. About 40 series (`config/learn/indicators.yaml`)
are downloaded once a day and cached in `data_cache/learn/`. Without the key, or with `--provider synthetic`, the page runs
on a simulated US economy and says so in a banner.

Excluded on purpose because their licences forbid redistribution: CME FedWatch and fed funds futures, ICE BofA indices,
Moody's and S&P series, the University of Michigan survey, Freddie Mac mortgage rates. The VIX is shown with Cboe's
attribution. The page footer cites FRED and the original publishers.

The `learn:` settings sit outside the keys of the model fingerprint (`features`, `regimes`, `models`, `validation`, `data`):
the regime model, its fingerprint and the published track record are unchanged (tested in `tests/test_learn.py`).

## The Fed odds: three lenses

None of them is a forecast of ours. They are shown side by side, and the page says when they disagree.

1. **Treasury bills (market).** A bill's yield is about the average overnight rate expected over its life plus a small
   basis. The basis is the median of bill yield minus effective fed funds on "quiet" days of the last 3 years (no target
   change within one bill life before or after), with a default when there are fewer than 60 such days. With a move of the
   same size at each FOMC meeting in the window, the implied change is solved exactly and read FedWatch-style: 0.4 expected
   hikes of 25 bp = 40% hike, 60% hold. Done for the 3-month and 6-month bills. Bills are a noisier public proxy than
   futures: they carry term and supply premia, so this lens is an approximation.
2. **Taylor rules (benchmark).** Taylor (1993), balanced approach and an inertial version, with core PCE inflation, an
   output gap from Okun's law (2 x (NROU - UNRATE)) and r* = 1%. The median rule against the actual target gives a direction
   (beyond +/-50 bp). A rule is a yardstick, not a probability.
3. **Historical base rates.** Month ends since 1985 described by core inflation, the unemployment gap, the 6-month
   unemployment trend and the Fed's change over the past year. The 40 months most like the analysis date (standardised
   distance) give the share of cuts, holds and hikes over the next 3 months (a move beyond 0.1 point). Outcomes not yet
   known on the analysis date are never used. The same split by our regime is shown in the pro tab.

FOMC decision days are in `config/learn/fomc.yaml` (2025 to 2027); outside it they are estimated every 45 days.

## Recession warning lights

Sahm rule (red at 0.5, amber at 0.3), 10-year minus 3-month curve (red when inverted, amber if inverted in the past year),
jobless claims 4-week average against its 52-week low (amber +15%, red +30%), payroll growth over 3 months (amber under
50k, red negative), real GDP year on year (amber under 1%, red negative) and our stress alarm. Thresholds are in
`config/settings.yaml` under `learn.checklist`. They describe, they do not date recessions.

## History: closest episodes and numbers

The "closest episode" box compares the analysis date with the first day of every episode that had already started (no
look-ahead in the time machine; the episode under way is left out) on five features: policy rate, core PCE inflation,
unemployment, 10y-3m spread and the Fed's 12-month change. Each difference is divided by that feature's standard deviation
since 1985 and the root mean square is the distance. Resemblance is not a forecast. Episode numbers are read from the same
FRED series inside the episode window (revised data). Episode texts, timelines and reading lists are in
`config/learn/episodes.yaml`.

## Lab formulas

- Bond: exact repricing of an annual-coupon bond; modified duration and convexity by finite differences.
- Yield-curve recession odds: New York Fed probit (Estrella and Trubin 2006), P = Φ(-0.5333 - 0.6330 × (10y - 3m)), fitted
  on 1959-2006; it signalled a recession in 2022-24 that had not come by the time of writing.
- Purchasing power: CPI-U ratio (CPIAUCSL). Real pay: (1 + w) / (1 + π) - 1 with average hourly earnings and CPI.
- Public debt: d(t+1) = d(t)(1 + r)/(1 + g) + primary deficit; stabilising primary balance d(r - g)/(1 + g).

## Limits

- FRED serves today's vintages: revised data. A past date in the time machine therefore shows what we know now about that
  day, not what was known then (the regime model itself uses first releases, see the point-in-time section of the README).
- Base rates rest on a few Fed cycles; neighbours are correlated months, so 40 neighbours are not 40 independent cases.
- Bill-implied odds include premia and can move with Treasury supply; compare with FedWatch privately, never republish it.
- Card texts are written for general education, not advice.

## GAMA, the AI tutor (coming soon)

The Ask section is in place in both tabs so the layout is final, but the tutor is switched off: the button only shows
"under construction". When it is built it will answer from the cards and today's data at the tab's level, citing the card
it used.

## Code

| File | Role |
|---|---|
| `pfe_drai/learn/data.py` | FRED download and cache, simulated economy, indicator transforms |
| `pfe_drai/learn/fed.py` | the three Fed lenses and the next meeting |
| `pfe_drai/learn/today.py` | readings, recession lights, cards in focus |
| `pfe_drai/learn/history.py` | episode numbers, closest episodes, regime mix |
| `pfe_drai/learn/lab.py` | calculator formulas |
| `pfe_drai/learn/cards.py` | cards, glossary, episodes, quiz, search |
| `app/learn_page.py` | the two tabs |
| `config/learn/` | indicators, FOMC calendar, cards, glossary, episodes |
