# The live record and timestamping

## Why a live record

A backtest, however careful, is computed after the fact, and the stress episodes it is scored on have been seen. A track record that anyone can audit, written before the outcome is known, is the only evidence that cannot be produced after the event. The project therefore publishes one every business day and keeps it apart from the backtest everywhere.

## How it is produced

Every business day after the US close (22:30 UTC), a scheduled job runs on real data only and writes one JSON file in `track_record/`: the regime and its probabilities, the stress alarm (on or off, since when, the detector score it reads and its threshold), the model version and the settings fingerprint, and how reliable the stress probability has been so far. Simulated data is refused. Three mechanisms make the record tamper-evident:

- each file's SHA-256 is appended to `track_record/index.csv`, and each file carries the hash of the day before, forming a chain whose breaks the public page shows and the job fails on;
- the hash of the frozen episode rule is in every entry;
- an **OpenTimestamps** proof anchors each file in the Bitcoin blockchain, which a git commit date cannot do (a commit date is easy to change). A fresh proof holds only calendar promises and is completed by the next day's run.

Each model configuration also gets one backtest record, written the first time the job runs with it and never rewritten. A new model or threshold gets a new file and the earlier ones stay, so the history of versions is part of the record.

{{table:versions}}

## What the record holds today

At the time of this build the live record holds {{live.days}} published day(s), the first on {{live.first_day|date}} and the latest on {{live.last_day|date}}, of which {{live.anchored}} are anchored in Bitcoin and {{live.pending}} are pending. The hash chain is intact: {{live.chain_ok|yesno}}.

{{table:live}}

Each published day is scored as published, never recomputed: an episode is detected if the alarm published in the preceding evenings was on, a day without a publication counts as no alarm, and an alarm becomes a false alarm only once {{backtest.current.rules.lookback_days}} business days have passed with no episode starting. At the time of this build the record is far too short to say anything about detection, and the report claims nothing from it. It grows by one entry each business day, and these chapters will read it when the report is rebuilt.

The track record also shows what the two kinds of evidence cannot be confused with: the page labels the backtest as evidence and the live days as proof, and it lists every model version with its own backtest and the day on which the published model changed. Market prices are never published, only model outputs, episode dates and the drawdown of each episode.
