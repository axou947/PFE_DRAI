# Regimes on three dimensions, and how the model's states get their names

**Status: adopted on 2026-10-01.** Chosen on simulated data; the pre-registered real-data
no-regression check (section 6, written before the run) passed the same day. Results at the bottom.

The 2026-09-30 re-audit asked for two things: regimes that rest on three dimensions (stress,
growth, inflation) rather than two axes, and an explanation of how an unsupervised model's states
are mapped to fixed regime names. This page answers both and records why the mapping changed.

## 1. Three dimensions

Twelve point-in-time indicators, each an expanding z-score (only the past is used, monthly
releases dated by their publication day, see `features/build.py`), are averaged into three
dimension scores. A high score means "more" of the dimension.

| Dimension | Indicators |
|---|---|
| Stress | VIX level, 21-day realised volatility, credit stress (HYG vs IEF, LQD before 2007), drawdown from the 1-year high |
| Growth | 6-month equity momentum, 10y-2y curve slope, industrial production (1 year), jobless claims (3 months, sign flipped) |
| Inflation | CPI (1 year), 10-year breakeven level, breakeven change (3 months), 2-year rate change (6 months) |

## 2. The rule that defines the four regimes

> **v2.2, adopted 2026-10-01 ([SLOWDOWN.md](SLOWDOWN.md)):** a real Slowdown regime. The growth
> score drops the curve slope, uses robust scaling and a 21-day average, and the Slowdown threshold
> becomes 0 (growth below its own median). The real-data run passed. The sections below were written for v2.1
> (growth threshold −0.25, four inputs with standard scaling); the results quoted are v2.1's.

`regimes.rule` in `config/settings.yaml`, applied in this order:

1. **Stress / crisis** if stress > 1.0, whatever growth and inflation do;
2. otherwise **Inflationary overheating** if inflation > 0.8 (with weak growth too: stagflation);
3. otherwise **Slowdown** if growth < 0 (v2.2; −0.25 until v2.1);
4. otherwise **Expansion**.

So each regime is a region of the three-dimensional space, not a quadrant of two axes. The rule
labels every day of history. Supervised models (gbm, onset) learn it directly. The app's
"What would flip the regime" panel shows how far each score is from its threshold.

## 3. How unsupervised states get a name

The jump model (the calm regimes of the default `combined` model) and k-means group days into
four states that have no name. `regimes.name_states` names them at every walk-forward refit,
using only the training window:

1. **Regime centres.** For each regime, the average position on (stress, growth, inflation) of the
   training days the rule puts in that regime. A regime with no training day has no centre.
2. **Nearest centre.** Each state takes the name of the regime whose centre is closest to the
   state's own centre (Euclidean distance; the three scores are on the same z-score scale).
3. **Evidence kept.** For each state: the distance, its number of training days and the share of
   those days the rule puts in each regime. The share of its own name is its *agreement with the
   rule*; under 50% it is a mixed state.

Two states can share a name (their probabilities add up), and a regime absent from the training
window cannot name any state. Nothing is set by hand: the names follow from the rule and the data.

Where to see it:

| Where | What |
|---|---|
| App, Dashboard, "How the regimes are defined" | the rule, the state table for the date shown, each state's split across regimes, a 3D view of history with the state centres |
| `python -m pfe_drai --provider fred states` | regime centres and states of the latest fit, then the names and agreement at every refit (`*` = mixed state) |
| API `GET /regime/states` | the state table of every refit |
| Daily track record (`track_record/*.json`, key `states`) | the state table behind each published regime |
| Committee note, section 6 | one sentence: the naming rule and the range of agreement |

## 4. What changed and why

Until this change, states were matched **one to one** to four **hand-set prototypes**
(`regimes.prototypes`, e.g. stress = (1.8, −0.5, −0.3)). Two problems:

- **The prototypes were typed in by hand**, close to the simulator's regimes. Nothing ties them to
  the real data, and nothing showed whether a named state really looked like its regime.
- **One to one forces every name onto a state.** Each name must be used exactly once, so when the
  data does not fit the prototypes, a state gets the name left over. On simulated data, seed 4,
  the first out-of-sample fit (2006-11) called "Slowdown" a state whose 484 training days were all
  overheating by the rule (inflation score +1.66), and a 2007-11 fit called "Expansion" another
  state of pure overheating days. Seed 5 called "Slowdown" a state with 89% of expansion days and
  8% of slowdown. The nearest-centre naming calls these Overheating, Overheating and Expansion.

The naming now comes from the rule. The `states` command and the app show the agreement of every
state, so a weak name is visible instead of hidden.

## 5. Methods compared on simulated data

13 simulated histories (seeds 1-12 and 42, 2000-2026, 229 stress episodes), every number out of
sample, combined model with the adopted v2 settings. *Agreement* = share of days where the
displayed regime equals the rule regime; *balanced* = average over the four regimes of the share of
each regime's days that are displayed as that regime (so the frequent Expansion does not dominate);
*truth* = accuracy against the simulator's hidden regimes.

| Naming method | Detected | FP / year | Alarm | Agreement | Balanced | Slowdown found | Truth |
|---|---|---|---|---|---|---|---|
| Hand-set prototypes, one to one (old) | 220 | 0.65 | 10.3% | 74.2% | 79.8% | 73.8% | 71.7% |
| **Nearest regime centre (new)** | 219 | 0.65 | 10.1% | 74.1% | 79.7% | 73.3% | 71.3% |
| Majority rule label of the state's days | 219 | 0.65 | 10.1% | 77.2% | 73.5% | 38.0% | 68.5% |
| Spread probabilities with each state's regime shares | 219 | 0.65 | 10.1% | 78.8% | 73.2% | 31.6% | 68.1% |
| Rule applied to the state's centre | | | | | 73.5% | 37.0% | |

The two methods that count days (majority, shares) agree more often with the rule only because they
display Expansion more: Slowdown states mix slowdown and expansion days, so those methods show
Slowdown on about a third of the rule's slowdown days, against three quarters for the nearest
centre. Spreading probabilities with the shares gives the best-calibrated probabilities (Brier
against the rule 0.31 vs 0.40) and was tried with 4, 5, 6 and 8 states; it never recovered Slowdown
(at most 43%). The rule applied to a state's centre flips the name when the centre sits near a
threshold. The nearest centre keeps what the prototypes did well without their hand-set numbers or
the forced one-to-one match.

Old vs new, per model (sums over the 13 seeds for counts, means otherwise):

| Model | Method | Detected | FP / year | Alarm | Switches / year | Agreement | Balanced | Truth | States under 25% agreement |
|---|---|---|---|---|---|---|---|---|---|
| combined | old | 220 / 229 | 0.647 | 10.3% | 5.23 | 74.2% | 79.8% | 71.7% | 61 |
| combined | new | 219 / 229 | 0.651 | 10.1% | 5.23 | 74.1% | 79.7% | 71.3% | 47 |
| jump | old | 102 / 229 | 0.167 | 6.8% | 2.17 | 76.9% | 81.1% | 74.0% | 61 |
| jump | new | 100 / 229 | 0.170 | 6.6% | 2.18 | 76.8% | 80.7% | 73.2% | 47 |

Same results in 8 of 13 seeds; in the other 5 the differences go both ways, up to 4 points on one
seed. The names differ only in some fits, most of them early ones (2006-2008) with a short
history, which are the cases section 4 describes. Stress detection is unchanged in practice
(one episode fewer out of 229): the combined stress probability takes the highest of the jump
model, gbm and onset, and the naming only touches the jump model's part. Reproduce with
`python docs/experiments/state_naming.py 1 2 3 4 5 6 7 8 9 10 11 12 42`.

## 6. Real-data check (pre-registered, before any real run of this change)

The change was chosen on simulated data only. On real data, Henry runs once:

```powershell
python -m pfe_drai --provider fred states
python -m pfe_drai --provider fred backtest --model combined
```

`states` is new information (how the real states are named); it decides nothing. `backtest`
checks that detection v2 still meets its adopted targets with the new naming:
**false positives ≤ 1.5 a year and false alarm ≤ 10% of calm days** (`validation.targets`). If both
hold, the new naming stays. If either fails, the old prototype matching comes back and this page
says so. The real 11 episodes were already scored (DETECTION_V2.md), so this run is a no-regression
check, not a new test: nothing will be tuned on it. Results go below, as they come out.

## Limits

- Slowdown is the weakest regime: its states mix slowdown and expansion days (agreement around
  50-65% on simulated data). The rule's growth threshold (−0.25) is set by hand; changing it would
  change gbm's target and so the adopted detection, which needs its own pre-registration.
- The displayed probabilities are not calibrated against the rule (Brier 0.40 for the regime as
  a whole); calibration is a separate improvement.

## Results

### Real data, 2026-10-01 (Henry, run once on branch `claude/three-dimension-regimes-xh2h72`)

**No-regression check: passed.** `backtest --model combined` with the new naming:

| | Episodes | Detected | Median latency | FP / year | Alarm | Switches / year |
|---|---|---|---|---|---|---|
| combined (v2), new naming | 11 | 11 | −3 days | 1.26 | 4.9% | 5.4 |
| combined (v2), as adopted (DETECTION_V2.md) | 11 | 11 | −3 days | 1.26 | 4.9% | 5.6 |

Every episode latency is the same as at adoption. Both targets hold (FP ≤ 1.5, alarm ≤ 10%), so the
new naming stays. Only the calm regimes move a little (5.4 regime switches a year instead of 5.6).

**What `states` shows on real data** (35 refits, training from 2004-04; this decides nothing,
it describes):

- Regime centres of the latest fit (to 2026-04-15): expansion 3,903 days, overheating 740,
  slowdown 527, stress 374. The rule puts 9.5% of days in Slowdown, and its centre
  (−0.13, −0.47, +0.04) is close to Expansion's (−0.39, +0.27, −0.04).
- **Stress is clean.** One state is named Stress at every refit, with 96-100% of stress days.
- **Overheating follows history.** No state is named Overheating in most refits from 2016-10 to
  2021-10, when inflation was low, and again from 2022-10 (80-82% agreement), after the 2021-22
  surge. The old one-to-one match would have called some state "Overheating" through 2016-2021.
- **Slowdown is not a distinct state on real data.** Until 2023-04 the state named Slowdown has
  only 13-26% slowdown days: mostly expansion days, on the slowdown side of the space. From
  2023-10 no state is named Slowdown, and two states are named Expansion (the latest fit's
  state 2 is 75% expansion, 13% slowdown, 12% stress: a "calm but tense" state).
- Median agreement 82%, lowest 13% (that Slowdown state).

**What follows.** The jump model's four states, on 2004-2026 US data, are best read as calm,
calm-but-tense, stress and (some years) overheating. Its Slowdown label is weak. That regime's
probability mostly comes from gbm, which learns the rule directly. Making Slowdown a real
regime would mean revisiting the rule's growth threshold or the growth indicators. Both change
gbm's target and so the adopted detection, which would need its own pre-registration. Nothing
is tuned here.
