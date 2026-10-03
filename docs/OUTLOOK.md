# Regime outlook from history

"Expansion since last July: how long does this usually last, and what came after it before?"
`pfe_drai/outlook.py` answers with **base rates**: counts of what the model displayed in the past. It is not
a forecast and not advice. It fits nothing and changes no model, setting, published entry or backtest
number (the settings fingerprint stays `7d25ca34…`; `tests/test_outlook.py`).

Where to see it:

- **Dashboard**, "Outlook from history" block (FR "Ce que dit l'historique"), under "Why this regime": the
  current spell, the lengths of past spells of the same regime (dots, with today's age as a dashed line), the
  regime that came next when such a spell ended, and an expander with every regime and every spell.
- **API**: `GET /regime/outlook?model=&date=&lang=` returns the numbers, every spell and the sentences (`text`).
- **Command line**: `python -m pfe_drai --provider fred outlook` (`--date YYYY-MM-DD`, `--json`).

## Which history

The published track record only began on 2026-10-01, too short to count spells. The base rates come from
the **out-of-sample walk-forward path** of the displayed model: the regime the dashboard shows on each day,
each day predicted by a model fitted only on earlier data (the same path as the dashboard timeline). With
real data and model v2.2 this starts in April 2009. When a past date is chosen, only the path up to that day
is used, so the outlook on 2020-03-20 is what could have been counted that evening.

## Spells

- A **spell** is a run of days with the same displayed regime.
- A run shorter than **5 market days** (`MIN_DAYS`) is a **blip**: it is put back into the regime before it,
  so a two-day flicker neither splits a long spell nor counts as a "next regime". The run on the date shown
  is never folded, even when it is younger than 5 days; the text then says it is that young.
- Lengths are in **market days** (days of the data); the current spell also shows calendar days.
- Lengths use **complete** spells only: the first spell started before the history (its length is unknown)
  and the current one has not ended.
- "Next regime" counts every spell that ended, the first one included.

## What is shown

1. How long the current spell has run, since when, and the interruptions folded into it.
2. Past spells of the same regime: how many, median length, middle half (25th to 75th percentile),
   shortest and longest.
3. How many of them lasted longer than today's age, and how much longer they went on (median). If none
   did, the text says this spell is already the longest in the history.
4. Which regime followed when a spell of this regime ended, as shares with counts.

Fewer than 5 complete spells: a warning that the shares rest on very few cases. On Slowdown, a second
warning: the displayed Slowdown matched outside growth references (CFNAI, GDP below potential) about as
often as chance (docs/SLOWDOWN_V23.md), so its spells say more about the model than about the economy.

## Limits

- These are the model's own regimes, not an official dating of the cycle: a spell ends when the model's
  reading changes, which can come from noise as much as from the economy.
- Seventeen years hold few spells of each regime. A share of "3 out of 4" is a count, not a probability.
- Spells are not independent and the past period (2009 to now) had its own policy and shocks. Nothing here
  says the next spell will look like the past ones.
- The 5-day blip threshold is a display choice, fixed before looking at real data. It changes the counts,
  not any model, alarm or published reading.
