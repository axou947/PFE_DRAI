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
| **History** | 8 episodes (1973 oil shock, Volcker, 1994, dot-com, 2008, 2019, Covid, 2022 inflation): what happened, what the Fed did, the lesson, on a chart | same at the pro level |
| **Lab** | Taylor rule calculator, real rate (Fisher) calculator, mortgage payment calculator | same, plus u* and r* sliders, the rules' history against the actual rate, and the Phillips curve scatter |
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
| `pfe_drai/learn/cards.py` | cards, glossary, episodes, quiz, search |
| `app/learn_page.py` | the two tabs |
| `config/learn/` | indicators, FOMC calendar, cards, glossary, episodes |
