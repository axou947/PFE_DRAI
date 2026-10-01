"""Calibration of P(stress): v2 (detector score) against calibrated versions, on simulated histories.

    python docs/experiments/calibration.py sources 1 2 3 4 5 6 7 8   (stack inputs: max | sources | sources_max)

Simulated data only (docs/CALIBRATION.md). For each seed: calibration scores of both versions
against the stress event, and detection if the alarm read each version at each threshold of the grid
(the adopted design keeps the alarm on the detector score; this grid is why). One process per seed
runs in parallel (OMP_NUM_THREADS=1); rows are printed as CSV for the summary tables.
"""

import sys

from pfe_drai.config import load_settings
from pfe_drai.models.combined import combine, combine_calibrated
from pfe_drai.pipeline import Pipeline
from pfe_drai.validation import evaluate
from pfe_drai.validation.calibration import calibration_report

THRESHOLDS = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]


def run(seed: int, inputs: str) -> list[dict]:
    transform, inputs = inputs.split(":")
    stack = {"transform": transform, "inputs": inputs}
    overrides = {"data": {"provider": "synthetic", "seed": seed}, "models": {"combined": {"stack": stack}}}
    settings = load_settings(overrides=overrides)
    p = Pipeline(settings)
    components = ["jump", *settings["models"]["combined"]["stress_sources"]]
    warm = settings["models"]["combined"]["stack"]["warmup_days"]
    parts = {name: p.probabilities(name, warm) for name in components}
    calibrated = combine_calibrated(parts, p.calibrated())
    start = calibrated.index[0]
    versions = {"max": combine(*(parts[n].loc[start:] for n in components)), f"{transform}:{inputs}": calibrated}
    rows = []
    for name, probs in versions.items():
        cal = calibration_report(probs["stress"], p.episodes, settings)
        for threshold in THRESHOLDS:
            s = {**settings, "validation": {**settings["validation"], "stress_probability_threshold": threshold}}
            r = evaluate(probs, p.prices["equity"], p.episodes, s)
            rows.append(
                {
                    "seed": seed,
                    "version": name,
                    "threshold": threshold,
                    "episodes": r["n_episodes"],
                    "detected": r["detected"],
                    "latency_all": r["median_latency_all"],
                    "fp_year": round(r["false_positives_per_year"], 3),
                    "alarm": round(r["false_alarm_share"], 4),
                    "switches": round(r["switches_per_year"], 2),
                    "brier": round(cal["brier"], 4),
                    "log_loss": round(cal["log_loss"], 4),
                    "ece": round(cal["ece"], 4),
                    "base_rate": round(cal["base_rate"], 4),
                    "mean_p": round(cal["mean_p"], 4),
                    "calibrated_share": round(float(p.calibrated().calibrated.mean()), 3),
                }
            )
    return rows


if __name__ == "__main__":
    import csv

    writer = None
    inputs, seeds = sys.argv[1], sys.argv[2:]
    for seed in map(int, seeds):
        for row in run(seed, inputs):
            if writer is None:
                writer = csv.DictWriter(sys.stdout, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
            sys.stdout.flush()
