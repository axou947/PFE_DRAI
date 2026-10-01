# Daily timestamped regime snapshots (one JSON per day), committed by CI.

Each JSON holds the regime and its probabilities, the stress alarm (`alarm`: on or off, since
when, the detector score it reads and its threshold) and how reliable the stress probability has
been so far (`calibration`: Brier, log loss, ECE and the reliability table over the out-of-sample
days whose outcome was known that day, plus the calibrator in use). From the day
`calibration.combination` reads `calibrated`, `probabilities.stress` (and `p_regime` in
`index.csv` when the regime is stress) is the calibrated probability; before, it was the detector
score. See docs/CALIBRATION.md.

Also here, built by the same daily job (docs/TRACK_RECORD.md):
- `index.html` (English) and `fr.html` (French): the public track-record page, with every alarm and
  every detection delay, live record first, backtest apart. Served on GitHub Pages once an admin sets
  Settings > Pages > Source to "GitHub Actions".
- `backtest/<last day>.json` (+ `.ots`): the out-of-sample backtest of a configuration, written once
  the first time the job runs with it, never rewritten.
