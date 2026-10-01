"""Compare two ways of naming the jump model's states, on simulated histories (docs/REGIMES.md).

old: one-to-one matching of state centres to hand-set prototypes (until 2026-10-01).
new: each state takes the name of the closest regime centre, measured on its training days.

    python docs/experiments/state_naming.py 1 2 3 4 5 6 7 8 9 10 11 12 42

Simulated data only. Prints one row per seed and method, then the means. Runs in parallel
across seeds with OMP_NUM_THREADS=1 if you start one process per seed.
"""

import sys

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from pfe_drai.config import load_settings
from pfe_drai.models import jump
from pfe_drai.models.combined import combine
from pfe_drai.pipeline import Pipeline
from pfe_drai.regimes import name_states
from pfe_drai.validation import evaluate, refit_cuts, walk_forward

ORDER = ["expansion", "overheating", "slowdown", "stress"]
# The prototypes removed from config/settings.yaml, position on (stress, growth, inflation).
PROTOTYPES = np.array([[-0.5, 0.5, 0.0], [0.0, -0.2, 1.2], [0.4, -0.5, -0.2], [1.8, -0.5, -0.3]])


def old_names(states, centroids, scores, labels, settings):
    table = name_states(states, centroids, scores, labels, settings)
    cost = ((centroids[:, None, :] - PROTOTYPES[None, :, :]) ** 2).sum(axis=2)
    rows, cols = linear_sum_assignment(cost)
    table["name"] = [ORDER[c] for _, c in sorted(zip(rows, cols, strict=True))]
    table["purity"] = [table.loc[i, f"share_{n}"] for i, n in table["name"].items()]
    return table


def run(seed: int) -> list[dict]:
    settings = load_settings(overrides={"data": {"seed": seed}})
    p = Pipeline(settings)
    gbm, onset = p.probabilities("gbm"), p.probabilities("onset")
    rows = []
    for method, namer in [("old", old_names), ("new", name_states)]:
        jump.name_states = namer
        jp = walk_forward("jump", p.features, p.scores, p.labels, settings)
        # Purity of the states the old method named after a regime the window's days hardly show.
        weak = 0
        for cut in refit_cuts(len(p.scores), settings, "jump"):
            table = jump.JumpModel(settings).fit(p.features.iloc[:cut], p.scores.iloc[:cut], p.labels.iloc[:cut]).state_table
            weak += int((table["purity"] < 0.25).sum())
        for model, probs in [("jump", jp), ("combined", combine(jp, gbm, onset))]:
            r = evaluate(probs, p.prices["equity"], p.episodes, settings, truth=p.truth, rule=p.labels)
            pred = probs.idxmax(axis=1)
            rule, truth = p.labels.reindex(pred.index), p.truth.reindex(pred.index)
            rows.append(
                {
                    "seed": seed,
                    "method": method,
                    "model": model,
                    "detected": r["detected"],
                    "episodes": r["n_episodes"],
                    "fp_per_year": r["false_positives_per_year"],
                    "false_alarm": r["false_alarm_share"],
                    "switches_per_year": r["switches_per_year"],
                    "agree_rule": r["agreement_rule"],
                    "balanced_rule": float(np.mean([(pred[rule == x] == x).mean() for x in ORDER])),
                    "accuracy_truth": r["accuracy_truth"],
                    "balanced_truth": float(np.mean([(pred[truth == x] == x).mean() for x in ORDER])),
                    "states_under_25pct": weak,
                }
            )
    return rows


if __name__ == "__main__":
    frame = pd.DataFrame([row for seed in sys.argv[1:] or ["42"] for row in run(int(seed))])
    pd.set_option("display.width", 200)
    print(frame.round(3).to_string(index=False))
    sums = frame.groupby(["model", "method"])[["detected", "episodes", "states_under_25pct"]].sum()
    means = (
        frame.groupby(["model", "method"])
        .mean(numeric_only=True)
        .drop(columns=["seed", "detected", "episodes", "states_under_25pct"])
    )
    print(sums.join(means).round(3).to_string())
