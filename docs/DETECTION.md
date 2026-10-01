# Stress detection: how the default model was chosen

> Superseded by v2 (a stress-onset detector added to `combined`), adopted on 2026-10-01 after a
> pre-registered test: 11/11 real episodes, median latency −3 days, 1.26 false positives a year.
> See [DETECTION_V2.md](DETECTION_V2.md). This page is v1 and stays as it was published.

Item 3 of the improvement list: the jump model caught too few stress episodes, too late.
This page records what was tried, on which data, and what was kept. Every choice below was made
on **simulated data only**, before running these settings on real data, so the real-data latencies
of the 12 frozen episodes (2008–2025) are an out-of-sample result, not a target we tuned to.

## Protocol

- Episodes are dated by the frozen rule (`validation.episodes.frozen`, unchanged).
- Scoring is unchanged: P(stress) above 0.5 for 3 days, detection window from 20 days before to
  60 days after the start, false positives = signal onsets outside the (widened) episodes.
- Development: synthetic seeds 1–8 (137 episodes). Confirmation: seeds 9–12 and 42 (92 episodes),
  never used while choosing.
- In the simulator, about half of the 10% drawdowns happen without any stress regime (random
  falls in calm periods). On seeds 1–8, 68 of the 137 episodes overlap a true stress period; a
  regime model is not expected to call the other ones "stress".

## What was tried (seeds 1–8)

| variant                                   | detected | of true stress | median latency | FP / yr | switches / yr |
|-------------------------------------------|---------:|---------------:|---------------:|--------:|--------------:|
| jump, penalty 12 (old default)            |  66/137  |   56/68        |   7.0          |  0.16   |  2.0          |
| gbm                                       |  76/137  |   66/68        |  −4.5          |  0.20   |  8.1          |
| jump + fast stress inputs, penalty 12     |  68/137  |   58/68        |   4.0          |  0.15   |  1.9          |
| jump + fast stress inputs, penalty 6      |  66/137  |   57/68        |   2.5          |  0.16   |  2.1          |
| **max(jump penalty 6, gbm)** (kept)       |  80/137  |   66/68        |  −5.0          |  0.17   |  2.4          |
| max(jump + fast inputs, gbm)              |  81/137  |   66/68        |  −5.0          |  0.17   |  2.1          |

Also tried: averaging jump and gbm instead of the max (fewer detections), and a softmax
temperature of 1 instead of 3 (no change in detections). A negative latency means the signal was
already on before the episode's dated start (up to 20 days early counts).

- **Faster stress inputs** (10-day realised vol, 5-day change in log VIX, added to the stress
  score) cut the jump model's latency, but adding them to the stress score also changes the rule
  labels that gbm learns, which doubled gbm's false positives (0.18 → 0.39 / yr), and they add
  nothing once gbm is combined. **Not kept.**
- **Switch penalty 12 → 6**: same detections, latency 6.5 → 4 days for the jump model alone,
  slightly more switches. **Kept.**
- **Combined signal**: the jump model gives persistent regimes, gbm reacts within days (it
  predicts one week ahead). The `combined` model keeps the jump model's regimes and takes
  P(stress) = max(jump, gbm); the other regimes share the rest in the jump model's proportions.
  It catches 66 of the 68 episodes with true stress. **Kept, and now the default model.**

## Confirmation on seeds it was not chosen on (9–12, 42)

| model                     | detected | median latency | FP / yr | switches / yr | accuracy vs truth |
|---------------------------|---------:|---------------:|--------:|--------------:|------------------:|
| jump, penalty 12 (before) |  36/92   |  10.5          |  0.18   |  2.0          |  0.73             |
| jump, penalty 6           |  36/92   |   8.0          |  0.16   |  2.2          |  0.75             |
| gbm                       |  42/92   |  −3.5          |  0.35   |  8.6          |  0.72             |
| **combined (after)**      |  44/92   |  −3.0          |  0.24   |  3.5          |  0.76             |

Both audit targets hold on simulated data: median latency ≤ 5 days and ≤ 1.5 false positives a year.
The cost is more regime switches than the jump model alone (3.5 against 2.0 a year), because gbm
can push P(stress) above the other regimes for a few days.

## Real data (run once, 2026-10-01)

`python -m pfe_drai --provider fred backtest`, run by Henry on 2026-10-01 after the choice above was
pushed. Out-of-sample from 2009-04, so 11 of the 12 frozen episodes are scored (2008 is in training).

| model                | detected | median latency | FP / yr | Brier |
|----------------------|---------:|---------------:|--------:|------:|
| **combined** (new)   |   5/11   |  11.0          |  0.17   | 0.097 |
| gbm                  |   5/11   |  11.0          |  0.17   | 0.099 |
| jump (penalty 6)     |   1/11   |  10.0          |  0.00   | 0.106 |
| kmeans               |   1/11   |   9.0          |  0.00   | 0.107 |

Latency of every episode (combined, business days):

| start      | max drawdown | latency |
|------------|-------------:|--------:|
| 2010-05-20 | −15.7%       | missed  |
| 2011-08-04 | −18.6%       | +11     |
| 2011-12-19 | −10.4%       | missed  |
| 2015-08-24 | −11.9%       | missed  |
| 2016-01-13 | −13.0%       | +18     |
| 2018-02-08 | −10.1%       | missed  |
| 2018-12-14 | −19.3%       | +6      |
| 2020-02-27 | −33.7%      | +5      |
| 2022-02-22 | −12.9%       | missed  |
| 2022-05-05 | −24.5%       | missed  |
| 2025-03-13 | −18.8%       | +18     |

- The false-positive target is met (0.17 / yr ≤ 1.5); the latency target is **not** (11 days > 5).
- On real data the stress signal comes from gbm alone: the jump model flags only 1 episode.
  Simulated data overstated the jump model, so the simulator is too easy on it.
- These numbers are published as they are. They were not used to choose anything on this page.
  Any later change is a new version of this page, chosen on data that excludes these 11 episodes
  or with a reason fixed before looking at them.
