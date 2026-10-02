# Operations: the daily job and its health

The track record promises one entry per market day, nothing missing and nothing rewritten. On the
public page a day without an entry counts as **no alarm**, so a silent failure of the daily job
quietly damages the proof. This page says how the job is watched, what each warning means, who
fixes what, and how to recover without breaking the promise.

## What watches what

| Piece | Runs | Needs | Does |
|---|---|---|---|
| `publish.yml` (Publish regime) | Mon-Fri 22:30 UTC, often hours late | FRED and Tiingo keys | publishes the day, then checks the data it used and writes `track_record/health/<day>.json` |
| `health.yml` (Daily job health) | Tue-Sat 06:30 UTC and by hand | nothing (no key) | checks `track_record/` itself and keeps one issue "Daily job health" |
| The public page | in the reader's browser | nothing | says "late" when the latest entry is behind the last market day, even if the job is dead |
| `python -m pfe_drai health` | by hand | keys only with `--provider fred` | the same checks, for a person |

`health.yml` is independent of `publish.yml` on purpose: a broken publication cannot hide its own
failure. It is **read-only** on the repository (it never writes to `track_record/`, never pushes)
and it never sees a data key. The source checks reach it through the records the publication job
committed.

Exit code of `health`: **0** ok, **1** warning, **2** failure. In `health.yml` a warning opens or
updates the issue; a failure also turns the run red. The issue is opened once, updated while the
problem lasts (a comment says when its severity changes) and closed when the check is green again.

Settings are in the `health:` block of `config/settings.yaml`. They sit outside `features`,
`regimes`, `models` and `validation`, so changing them never changes the settings fingerprint and
never opens a new backtest record.

## Reading the checks

An entry for a market day is **due** 9 hours after the US close (06:00 UTC the next morning,
`health.due_after_close_hours`): the cron often starts late (01:46 UTC on 2026-10-01). Before that
the report says "not out yet", after it, the day is missing. Market days come from a built-in NYSE
calendar (`pfe_drai/nyse.py`): holidays, a Good Friday, a long weekend are not misses, and the
report says which closure explains the absence.

| Check | Warning or failure means | Who fixes what |
|---|---|---|
| `record.integrity` | **Failure.** A file no longer matches its hash in `index.csv`, or a `previous_sha256` link is broken. Nothing is repaired: the check only reports. | Find the commit that changed the file (`git log -- track_record/<day>.json`). Never edit the record to make the check pass; explain the incident in the repository instead. |
| `record.latest` | **Failure.** One or more market days have no entry after their due time. The message lists the dates, and what the publication job found if it ran (stale source). | See "A day was missed" below. |
| `record.gaps` | **Warning.** A market day between the first and the latest entry has no entry (a past miss), or an entry is dated on a closed day (calendar or data problem). | A past miss never goes away. Once it is understood, list it in `health.acknowledged_gaps` with the reason: it stays listed, and the issue closes. |
| `record.ots` | **Warning.** An entry older than `ots_upgrade_days` (3) has no Bitcoin attestation yet. | The next daily run does `ots upgrade`. If it persists, run `ots upgrade track_record/<day>.json.ots` by hand and commit the result. A missing `.ots` file cannot be recreated afterwards for the original time: say so in the repository. |
| `record.timeliness` | **Warning.** The latest entry was published after the next market open: late, and labelled as such (its `published_at` is untouched). | Look at why the run was late (GitHub queue, outage). Nothing to repair. |
| `record.data` | The data behind the latest entry was degraded (see the source checks). | See below. |
| `sources.freshness` | A series is older than its threshold: **warning** or **failure**, named with its last date and its age. Daily series are counted in market days behind the last close (FRED posts a day late, so 1 is normal), jobless claims and monthly series in days since their release, so CPI is not "late" between two releases. | The source stopped updating: wait for it, or check the series on FRED / Tiingo. The entry was still published, labelled "data warning" on the page. |
| `sources.path` | A series was not read the intended way: partly simulated data (failure), or a revised series not read as ALFRED first releases (warning: not point-in-time). | Check the keys and `data.point_in_time`. |
| `run.entry` | **Failure** if the run published nothing on a market day: a stale source looks exactly like a holiday to `publish`. | Same as a missed day. |

A failed publication (HTTP error, expired key, series missing) writes the error class, the HTTP
status and the failing series name to the job summary and as an error annotation. Exception text
is scrubbed of keys, and the reports hold dates and series names only, never prices.

A degraded but published day is **labelled, never silently normal**: its health record sits next to
the entry, the page marks the day "data warning" and says which series was stale, and the run
ends red. The entry itself, its hash, the settings fingerprint (`config_sha256`) and every
published number are unchanged by any of this.

## A day was missed: the policy

**A day that was not published stays missing.** The job must not back-publish it later: the entry
would be stamped after the fact, which breaks "published the evening it was true". On the page the
day counts as no alarm, visibly, and is not hidden.

1. Find the cause from the issue, the run list it links, and the job summary of the failed run.
2. Fix the cause (renew an expired key in Settings > Secrets and variables > Actions, wait for the
   outage to end, re-enable a disabled workflow).
3. Do **not** run "Publish regime" by hand to catch up for a past day: it would publish the latest
   data under today's date, stamped today. Running it by hand is right only for a day that is still
   current (before the next market open), for example the evening's run that did not start. The
   next scheduled run then publishes the next day as usual.
4. Write down what happened (an issue or a note) and list the date in `health.acknowledged_gaps`
   with the reason. A late catch-up is allowed only as a clearly labelled supplementary file
   outside `index.csv`, or not at all. The default is not at all.

## Trying it

    python -m pfe_drai health --offline                    # record and calendar only, no keys
    python -m pfe_drai --provider fred health              # also the freshness of every series (keys needed)
    python -m pfe_drai health --offline --now 2026-10-03T07:00   # what-if: the check as of another moment

`health.yml` can be run from the Actions tab (Run workflow). On a healthy day it opens nothing.

## Limits

- `health.yml` cannot warn about itself: if GitHub disables scheduled workflows after 60 days
  without repository activity, or the workflow is deleted, nobody is told. The daily publication
  commits keep the repository active; the page's browser check still shows "late" if the job dies.
- The NYSE calendar is built into the code from the exchange's published rules, with the
  exceptional closures since 2000 listed by hand. A new exceptional closure (a day of mourning)
  would show up as a "missing day" on the next check until `EXCEPTIONAL_CLOSURES` is updated.
- The public page checks the calendar in the browser from the closures embedded when the page was
  built (to two years after the latest entry).
