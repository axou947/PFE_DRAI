# Public track record and latency page

One page, in English (`track_record/index.html`) and French (`track_record/fr.html`), that shows
every stress alarm and every detection delay: the proof the re-audit asks for ("publish every
latency"; a track record externally timestamped, not dated by git). It is built by the daily
"Publish regime" job, committed next to the records it reads, and the same page is the
**Track record** tab of the app.

## What it shows, and what it keeps apart

**Live record**: what was published each evening, read back from `track_record/` and never
recomputed.

- the latest day (regime, calibrated P(stress), alarm on or off and since when), the number of
  days published, how many are anchored in Bitcoin, and whether the hash chain is intact;
- every stress episode dated by the frozen rule since the first publication, with the delay
  measured against the alarm **as it was published that evening**. A day without a publication
  counts as no alarm. An episode whose 60-day window is still open is "window still open", not
  missed;
- every alarm since the first publication, with the episode it belongs to, or "false alarm" once
  20 business days have passed with no episode starting ("too early to tell" until then);
- every published day with its SHA-256, OpenTimestamps state and links to its files, and the two
  commands anyone can run to check a day.

**Backtest record**: the out-of-sample (walk-forward) backtest of the current configuration,
written once and then frozen (`track_record/backtest/<last day>.json`, stamped too).

- the summary metrics against their targets (detected, median delay over detected and over all
  episodes, false alarms a year, share of calm days in false alarm, Brier and ECE of P(stress));
- P(stress), the detector score and the alarm day by day since 2009, with the episodes;
- the delay of every episode (chart and table) and every alarm, false ones included;
- the reliability table of P(stress), and where the numbers come from (code version, settings
  and episode-rule fingerprints, file hash, timestamp).

The backtest is labelled as such everywhere: it is out-of-sample, but it was computed after the
fact and the detector was chosen in October 2026 with these episodes known
([DETECTION_V2.md](DETECTION_V2.md)). It is evidence; the live record is the proof.

Not published: market prices (data licences, see the re-audit). The page only carries the model's
outputs, episode dates and the drawdown of each episode.

## How it is produced

`python -m pfe_drai --provider fred track-record`, run by `.github/workflows/publish.yml` right
after `publish`:

1. **Backtest record, once per configuration.** If no file in `track_record/backtest/` has the
   current settings fingerprint (`config_sha256`: features, regimes, models, validation and the
   data settings that change results; not the provider or the end date), the backtest is computed
   on real data, written, and stamped with OpenTimestamps. An existing record is never rewritten:
   a new model or threshold gets a new file, and the earlier ones stay in the repository.
   Simulated data is refused, as for `publish`.
2. **Live record.** Every row of `index.csv` is checked: the file's SHA-256 against the index,
   and its `previous_sha256` against the day before. A broken chain is shown on the page and
   makes the job fail.
3. **Pages.** `index.html` and `fr.html` are self-contained (no external script, font or style;
   inline SVG charts, readable without JavaScript). They hold no build time, so rebuilding from
   the same records gives the same files and a holiday run commits nothing.

The page step cannot cost a day of the record: the entry is published and committed first, and a
page failure only turns the run red afterwards.

**OpenTimestamps.** `publish` stamps each day (`ots stamp`, PR #3). A fresh proof only holds
calendar promises; the job runs `ots upgrade` on every `.ots` file (backtest included) at the
start of the next run, which adds the Bitcoin attestation. The page reads each proof and shows
"anchored in Bitcoin", "pending" or "none". Nothing had been published before this page was
added: the first stamped day is the first scheduled run.

## Preview without touching the record

    python -m pfe_drai --provider fred track-record --out preview

writes the pages (and, if needed, a backtest record) into `preview/` and leaves `track_record/`
untouched. On simulated data (`python -m pfe_drai track-record --out preview`) the page is marked
"SIMULATED DATA" and live days are not scored.

## Making it public (GitHub Pages)

The repository is public, so the files are already readable on GitHub, but GitHub shows HTML as
source. To serve the page as a website, an **admin of the repository** sets once:

**Settings > Pages > Build and deployment > Source: GitHub Actions.**

The `pages` job of the same workflow then deploys `track_record/` after each daily run (or run
"Publish regime" by hand from the Actions tab). Address: https://axou947.github.io/PFE_DRAI/
(French: `fr.html`). Until it is switched on, the job prints a notice and does nothing.
