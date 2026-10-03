# Challenger track record

**Status: set up on 2026-10-03, before any challenger was published.** Everything on this page is fixed before the
first live day. The published model stays **v2.2**, its settings fingerprint (`7d25ca34…`) and its daily entries
do not change.

## Why

Nine ideas were tested against v2.2 on 2026-10-03 ([MODEL_UPGRADES.md](MODEL_UPGRADES.md), [SAHM_HY.md](SAHM_HY.md)),
and none earned adoption. Some of them could not be tested fairly at all:

- the **VIX term structure** (FRED `VXVCLS`, the 3-month VIX) starts in December 2007, so it has almost no history
  before the out-of-sample period, and every crisis since 2009 has already been seen;
- **high-yield credit** looked neutral on simulated data, but the simulator's credit spread follows the regime
  slowly and cannot lead equities the way real spreads sometimes do.

A past that has been seen cannot be un-seen. The future has not been seen by anyone. A **challenger** is v2.2 with
one change, published live every market day next to the published model, with the same proofs, and scored only on
what happens after its first day.

## The challengers (`challengers` in `config/settings.yaml`)

| name | the one change | extra series |
|---|---|---|
| `vix_term` | the onset detector also reads VIX ÷ 3-month VIX (above 1 = inverted, panic) and its 5-day change | `vix3m`, FRED `VXVCLS` |
| `hy_credit` | the onset detector also reads a high-yield fund against a Treasury fund over 5 and 21 days | `hy_fund`, `treasury_fund`: Tiingo `VWEHX`, `VFITX` |

Everything else is v2.2: the same data, scores, jump model, gbm, calibration, alarm rule (0.5 for 3 days) and
frozen episode rule. Each challenger is trained walk-forward on the past like v2.2, so its first live day already
uses every past episode.

The **Sahm rule** is not a challenger: as a growth input it failed its real holdout (SAHM_HY.md), and a different
use of unemployment would need its own reason first.

## How it runs

The daily job ([publish.yml](../.github/workflows/publish.yml), step "Publish the challengers", after the US entry
and the regions) runs `python -m pfe_drai --provider fred challengers`:

1. Each challenger's day is published into `track_record/challengers/<name>/` in the same way as v2.2's: one JSON
   per market day with its regime, P(stress), alarm, `model_version` (`v2.2+<name>`) and `config_sha256`, an
   `index.csv` hash chain, and an OpenTimestamps proof. A day already published is not written again. Missed days
   are never back-filled.
2. The scorecard is rebuilt from the published entries only, never recomputed: `track_record/challengers/
   scorecard.md` and `scorecard.json`. It covers v2.2's own entries and each challenger's, from the first
   challenger day on: episodes scored, detected, median latency, false alarms (final and pending), who called each
   episode first, and the alarms started each month.
3. A challenger's failure never costs the US entry. The step only warns, and the other challenger still publishes.

Episodes are dated by the frozen rule (sha256 `6741b674…`) as for v2.2's live record. An episode whose detection
window has not elapsed, or a false alarm that could still turn true, is **pending**, not counted.

`python -m pfe_drai --provider fred challengers --backtest` prints each challenger on the past out-of-sample
period. **Those episodes were already seen, so it is informative only and decides nothing.** On simulated data
(seed 42): v2.2 18/18 detected, 0.60 false positives a year; `vix_term` 18/18, 0.65; `hy_credit` 17/18, 0.55.

## When a challenger may be put forward (fixed now)

A challenger is never retuned while it runs. A changed challenger is a new name and starts a new record.

It may be put forward for adoption only when **all** of these hold on its live record:

1. at least **3 stress episodes** have been scored (window elapsed) since its first day;
2. it detected **every** one of those episodes that v2.2 detected;
3. it is better on one side and not worse on the other: a median latency at least **1 business day** lower with no
   more final false alarms than v2.2, **or** fewer final false alarms with a median latency no higher;
4. it meets the product's limits over its live days: at most **1.5** false alarms a year and at most **10%** of calm
   days in alarm (`validation.targets`);
5. its hash chain is intact.

Meeting them does not adopt it. It opens a pre-registration, written before any further run, deciding whether it
replaces v2.2. Until then the published model, the alerts and the app stay on v2.2.

## What this does not claim

- **It is slow.** The frozen rule dates about one episode a year (12 from 2008 to 2025), so three live episodes may
  take years. That is the cost of evidence nobody has seen. The monthly view shows false alarms much sooner.
- **Two challengers make two chances to look lucky.** That is one reason for conditions 2 and 3 (no episode lost,
  better on one side without being worse on the other) and for a separate pre-registration after.
- The 3-month VIX is published by Cboe (through FRED, licence "check" in the catalog, as for the VIX itself).
- The challengers' entries are public on the same page as v2.2's. They are labelled by `model_version`, and the app
  and the alerts never read them.
