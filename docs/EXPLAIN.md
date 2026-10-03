# Explain the regime

A risk manager who reads "Regime: Slowdown, stress alarm off" asks why, and how close it is to changing.
`pfe_drai/explain.py` answers from the numbers the model already uses, in plain sentences built from
FR/EN templates (`explain.*` in `locales/`), never from generated text. It is descriptive: it says what
the scores and the models read, not what to do, and it identifies no cause.

Where to see it:

- **Dashboard**, "Why this regime" block: one sentence per dimension, the contribution bars (today, with
  a mark for a week ago), what would flip the rule, and what drives the stress alarm.
- **API**: `GET /regime/explain?model=&date=&lang=` returns the full explanation and its sentences (`text`).
- **Committee note**: a "What drives this reading" paragraph of 4 to 6 lines.
- **Command line**: `python -m pfe_drai --provider fred explain --date 2020-03-16` (`--json` for everything).

Nothing here changes a model, a setting, the published daily JSON or a backtest number
(`tests/test_explain.py` compares them with a fixture computed before this module existed).

## 1. Score decomposition

Each dimension score is the plain average of its inputs' z-scores (`features/build.py`), so an input
contributes its z-score divided by the number of inputs. The growth score is then averaged over the last
`features.growth.smooth_days` (21) days, so an input's contribution to it is the 21-day average of its
z-score divided by 4. The sentence for growth also gives today's reading alone (the same-day average of
the four inputs), so a reader sees where the 21-day average is heading.

Contributions are given today, a week ago (5 business days) and a month ago (21), with their changes, and
they add up to the score exactly (to 1e-9, tested on every day of a synthetic run).

## 2. What would flip the rule

The rule (`regimes.rule_labels`) checks stress first (above 1.0), then inflation (above 0.8), then growth
(below 0), and calls everything else Expansion. The explanation says which step decides, and for each
dimension the move of its score that alone would change the label and the label it would give. A move
that cannot change the label (a higher step decides) is not listed. The nearest change is the smallest.

Per input, the move it would need alone, all other inputs unchanged: the score is linear in each z-score,
so the needed z-score move is the score's distance to the threshold times the number of inputs. For a
growth input the move is held over the 21-day window, because a single day moves the 21-day average 21
times less. When the z-score scale can be inverted cheaply (its expanding mean and standard deviation, or
median and interquartile range for growth), the move is also given in the input's own unit ("about VIX
+8 points", "claims +12% over 3 months"); otherwise it stays in z units. A z-score is clipped at ±4, so a
move that would take it beyond ±4, or a move larger than 4, cannot happen: it is hidden and counted.

Each what-if is checked by applying it to the real z-scores and recomputing the scores with
`features/build.py`'s own functions: the rule changes just past the stated move and not before it.

The rule is the transparent definition the models learn from; the regime shown is the model's. When they
disagree on a day, the explanation says so.

## 3. What drives the stress alarm

The alarm reads the highest stress source: for the default `combined` model, the highest of the jump
model, gradient boosting and the onset detector (uncalibrated: calibration does not change the alarm). The
explanation names it and gives its value today and a week ago.

For that source, an **occlusion**: each input alone is put back to its value of 5 business days earlier,
the same model is evaluated again, and the change in its probability is reported (top 5, at least 0.1
point). The model is the walk-forward fit that made the day's prediction, refitted on the same window with
the same seed; the explanation checks that it reproduces the published probability (`reproduced`). Inputs
are the 12 indicator z-scores for jump, gradient boosting and k-means (the day's dimension scores are
recomputed from them), and the fast market inputs for the onset detector (whose 5-day hold is kept). No
new dependency (no SHAP). It answers "what moved this probability since last week", not "what caused it":
inputs move together, and putting one back alone can give a combination never seen in the data. A source
that cannot be re-evaluated says "not available for this model".

## Limits

- The decomposition explains the rule's scores. The regime shown comes from a model that learns from
  them; it can differ from the rule on a given day, and the explanation says so rather than hiding it.
- What-ifs move one input at a time. Real moves are joint, so they describe the distance, not a scenario.
- Raw-unit conversions are approximate ("about"): log changes are read as percentages, and the scale of a
  growth input held over 21 days is today's.
