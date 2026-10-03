"""Inflation score, one vote per input against one vote per source, on simulated histories (docs/INFLATION.md).

    python docs/experiments/inflation.py 1 2 3 4 5 6 7 8 9 10 11 12 42

Simulated data only. For each seed: the scores `python -m pfe_drai overheating` prints (validation/overheating.py,
reference = the simulator's hidden overheating regime) and the stress detection and calibration numbers.
One row per seed and variant, then the sums and means per variant. One process per seed with
OMP_NUM_THREADS=1 runs in parallel.
"""

import sys

import pandas as pd

from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.pipeline import Pipeline
from pfe_drai.validation.overheating import overheating_report


def run(seed: int) -> list[dict]:
    base = load_settings(overrides={"data": {"seed": seed}})
    rows = []
    for name in ("before", "tested"):
        settings = _deep_merge(base, {"features": {"inflation": base["overheating"][name]["inflation"]}})
        p = Pipeline(settings)
        r = p.evaluate("combined")
        report = overheating_report(p, "combined")
        rows.append(
            {
                "seed": seed,
                "variant": name,
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
    seeds = [int(a) for a in sys.argv[1:]] or [42]
    frame = pd.DataFrame([row for seed in seeds for row in run(seed)])
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(frame.round(3).to_string(index=False))
    sums = frame.groupby("variant", sort=False)[["detected", "episodes"]].sum()
    means = frame.groupby("variant", sort=False).mean(numeric_only=True).drop(columns=["seed", "detected", "episodes"])
    print(sums.join(means).round(3).to_string())
