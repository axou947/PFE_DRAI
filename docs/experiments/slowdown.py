"""Growth score candidates for a real Slowdown regime, on simulated histories (docs/SLOWDOWN.md).

    python docs/experiments/slowdown.py 1 2 3 4 5 6 7 8        # development seeds
    python docs/experiments/slowdown.py 9 10 11 12 42          # confirmation seeds

Simulated data only. For each seed and candidate: how well the growth score's "below threshold"
matches the simulator's hidden below-trend growth (slowdown or stress), how persistent the rule's
Slowdown is, whether the displayed regime and the jump model's states find Slowdown, and the
stress detection and calibration numbers that must not get worse. One row per seed and candidate,
then the sums and means per candidate. One process per seed with OMP_NUM_THREADS=1 runs in parallel.
"""

import sys

import pandas as pd

from pfe_drai.config import load_settings
from pfe_drai.pipeline import Pipeline
from pfe_drai.validation.slowdown import slowdown_report

ALL4 = ["equity_momentum", "curve_slope", "industrial_production", "jobless_claims"]
NO_SLOPE = ["equity_momentum", "industrial_production", "jobless_claims"]
MACRO = ["industrial_production", "jobless_claims"]


def candidate(inputs, scaling="standard", smooth=0, threshold=-0.25) -> dict:
    return {
        "features": {"growth": {"inputs": inputs, "scaling": scaling, "smooth_days": smooth}},
        "regimes": {"rule": {"growth_threshold": threshold}},
    }


CANDIDATES = {
    "current": candidate(ALL4),
    "threshold 0": candidate(ALL4, threshold=0.0),
    "+ smooth 21": candidate(ALL4, smooth=21, threshold=0.0),
    "+ no slope": candidate(NO_SLOPE, smooth=21, threshold=0.0),
    "+ robust": candidate(NO_SLOPE, "robust", 21, 0.0),
    "macro only": candidate(MACRO, smooth=21, threshold=0.0),
    "macro, robust": candidate(MACRO, "robust", 21, 0.0),
}


def run(seed: int, names: list[str]) -> list[dict]:
    rows = []
    for name in names:
        overrides = {**CANDIDATES[name], "data": {"seed": seed}}
        p = Pipeline(load_settings(overrides=overrides))
        r = p.evaluate("combined")
        report = slowdown_report(p, "combined")
        rows.append(
            {
                "seed": seed,
                "candidate": name,
                "detected": r["detected"],
                "episodes": r["n_episodes"],
                "lat_all": r["median_latency_all"],
                "fp_yr": r["false_positives_per_year"],
                "alarm": r["false_alarm_share"],
                "brier": r["brier"],
                "ece": r["ece"],
                "switch_yr": r["switches_per_year"],
                **report["summary"],
            }
        )
    return rows


if __name__ == "__main__":
    args = sys.argv[1:] or ["42"]
    names = [a for a in args if a in CANDIDATES] or list(CANDIDATES)
    seeds = [int(a) for a in args if a not in CANDIDATES]
    frame = pd.DataFrame([row for seed in seeds for row in run(seed, names)])
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(frame.round(3).to_string(index=False))
    sums = frame.groupby("candidate", sort=False)[["detected", "episodes"]].sum()
    means = frame.groupby("candidate", sort=False).mean(numeric_only=True).drop(columns=["seed", "detected", "episodes"])
    print(sums.join(means).round(3).to_string())
