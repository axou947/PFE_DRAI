"""Where does the displayed Slowdown lose its match, and which display fixes it? Simulated data only (docs/SLOWDOWN_V23.md).

    python docs/experiments/slowdown_v23.py 1 2 3 4 5 6 7 8            # development seeds
    python docs/experiments/slowdown_v23.py 9 10 11 12 42              # confirmation seeds
    python docs/experiments/slowdown_v23.py quiet 1 2 3 4 5 6 7 8      # "quiet slowdown" world

Also prints, per seed, what the pre-registered procedure (validation/display_v23.py) would decide.

Two simulated worlds:
- standard: the simulator as it is. Its slowdowns come with stressed markets (equity volatility 21%,
  high-yield spread 5.5%), so they are easy to see on the stress dimension too;
- quiet: the same paths, but a slowdown's markets look like an expansion's (volatility 14%, spread 4%),
  only production and claims are weak. This is the shape of most below-trend months since 2009 (calm
  markets, weak activity), where the jump model fails on real data (docs/SLOWDOWN.md).

For each seed the model is run once (v2.2 settings), then every display is computed from the same
out-of-sample probabilities. Every display keeps P(stress) exactly as published, so the stress alarm and
calibration cannot change. Scored on the out-of-sample days against the hidden slowdown regime:
- the diagnosis: rule label (growth, then inflation, then stress) and the growth score alone, against the
  same reference, to locate the loss (growth score, rule, or the jump model's naming);
- the candidate displays (docs/SLOWDOWN_V23.md), with their switches a year and median Slowdown spell.
"""

import sys

import numpy as np
import pandas as pd

from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.data import synthetic
from pfe_drai.pipeline import Pipeline
from pfe_drai.validation.display_v23 import run_v23
from pfe_drai.validation.slowdown import balanced_accuracy, spells

QUIET_SLOWDOWN = (0.10, 0.14, 1.00, 4.0, 1.9, -1.0, 300_000, -0.004)
DISPLAYS = ["jump", "rule", "rule_named", "gbm"]


def scores_for(shown: pd.Series, slow: pd.Series, years: float) -> dict:
    is_slow = shown == "slowdown"
    runs = spells(is_slow)
    return {
        "ba": balanced_accuracy(is_slow, slow),
        "recall": float(is_slow[slow].mean()),
        "precision": float(slow[is_slow].mean()) if is_slow.any() else float("nan"),
        "shown": float(is_slow.mean()),
        "switch_yr": float((shown != shown.shift()).iloc[1:].sum() / years),
        "spell": float(runs.median()) if len(runs) else float("nan"),
    }


def run(seed: int, world: str) -> list[dict]:
    if world == "quiet":
        synthetic.PARAMS["slowdown"] = QUIET_SLOWDOWN
    p = Pipeline(load_settings(overrides={"data": {"seed": seed}}))
    probs = p.probabilities("combined")
    index = probs.index
    slow = p.truth.reindex(index) == "slowdown"
    years = (index[-1] - index[0]).days / 365.25
    rows = []
    # Diagnosis: the rule's own Slowdown and "growth below threshold", against the same reference.
    rule = p.labels.reindex(index)
    low = p.scores["growth"].reindex(index) < p.settings["regimes"]["rule"]["growth_threshold"]
    rows.append({"seed": seed, "world": world, "display": "(rule label)", **scores_for(rule, slow, years)})
    rows.append(
        {
            "seed": seed,
            "world": world,
            "display": "(growth low)",
            **scores_for(low.map({True: "slowdown", False: "x"}), slow, years),
        }
    )
    for name in DISPLAYS:
        q = p.with_settings(_deep_merge(p.settings, {"models": {"combined": {"calm": name}}}))
        shown_probs = q.probabilities("combined")
        assert np.allclose(shown_probs["stress"], probs["stress"])  # P(stress) is never touched
        shown = shown_probs.idxmax(axis=1)
        rows.append({"seed": seed, "world": world, "display": name, **scores_for(shown, slow, years)})
    # The pre-registered procedure itself (selection on the first part, decision on the second).
    res = run_v23(p, "combined")
    failed = [label for label, ok in res["decision"]["checks"].items() if not ok]
    print(f"PROTOCOL seed={seed} world={world} chosen={res['chosen']} adopt={res['decision']['adopt']} failed={failed}")
    return rows


if __name__ == "__main__":
    args = sys.argv[1:] or ["42"]
    world = "quiet" if "quiet" in args else "standard"
    seeds = [int(a) for a in args if a != "quiet"]
    frame = pd.DataFrame([row for seed in seeds for row in run(seed, world)])
    pd.set_option("display.width", 200)
    print(frame.round(3).to_string(index=False))
    print(frame.groupby("display", sort=False).mean(numeric_only=True).drop(columns="seed").round(3).to_string())
    wide = frame.pivot(index="seed", columns="display", values="ba")
    for name in DISPLAYS[1:]:
        print(f"{name}: better than jump in {(wide[name] > wide['jump']).sum()}/{len(wide)} seeds")
