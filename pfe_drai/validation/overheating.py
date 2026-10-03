"""Does the inflation score find Overheating better with one vote per source? (docs/INFLATION.md)

The inflation score averages four z-scores, two of which (the 10-year breakeven's level and its change
over a quarter) are read off the same series, so market expectations carry half of it. v2.3 gives each
source one vote (`features.inflation.weighting: sources`). Nothing in the model checks that the rule's
Overheating matches high inflation in the economy, so this module compares it with an outside reference:

- simulated data: the simulator's hidden regime (overheating);
- real data: core PCE inflation over 12 months (FRED `PCEPILFE`, the Fed's preferred measure, not a
  model input) above `overheating.reference.above` percent. Used as published today (revised): it is the
  answer, never an input. Each month's value applies to the days of that month.

Scores, on the model's out-of-sample days:
- inflation balanced accuracy: does "inflation score above its threshold" match high inflation?
- displayed Overheating: does the regime the model displays say Overheating on the reference's
  overheating days (high inflation outside any stress episode; simulated: the hidden overheating
  regime)? Balanced accuracy, recall and precision;
- persistence and named state, as for Slowdown (validation/slowdown.py), reported only.
"""

import os

import numpy as np
import pandas as pd

from .episodes import episode_mask
from .slowdown import balanced_accuracy, spells


def core_inflation(settings: dict, start, end) -> pd.Series | None:
    """12-month core PCE inflation in percent from FRED (monthly, latest vintage), None for other providers."""
    if settings["data"]["provider"] != "fred":
        return None
    from ..data.fred import fetch_fred

    key = os.environ.get(settings["data"]["fred_api_key_env"])
    if not key:
        return None
    series_id = settings["overheating"]["reference"]["fred"]
    level = fetch_fred(series_id, key, pd.Timestamp(start) - pd.DateOffset(months=14), end)
    return (level.pct_change(12, fill_method=None) * 100).dropna()


def high_inflation(inflation: pd.Series, index: pd.DatetimeIndex, settings: dict) -> pd.Series:
    """Each month's reading on the days of that month (it describes the month, whenever it came out)."""
    months = pd.Series(inflation.to_numpy(), index=inflation.index.to_period("M"))
    value = pd.Series(months.reindex(index.to_period("M")).to_numpy(), index=index)
    return (value > settings["overheating"]["reference"]["above"]).where(value.notna())


def reference_inflation(pipeline, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, str] | None:
    """(high inflation, overheating reference, source name) on `index`, None without a reference."""
    truth = pipeline.truth
    if truth is not None:
        hot = truth.reindex(index) == "overheating"
        return hot, hot, "simulated regimes"
    core = core_inflation(pipeline.settings, index[0], index[-1])
    if core is None:
        return None
    high = high_inflation(core, index, pipeline.settings)
    outside = ~episode_mask(index, pipeline.episodes)
    hot = (high.fillna(False).astype(bool) & outside).where(high.notna())
    ref = pipeline.settings["overheating"]["reference"]
    return high, hot, f"{ref['fred']} over 12 months > {ref['above']:g}%"


def overheating_report(pipeline, model: str | None = None) -> dict:
    """Every score above for `model`, on its out-of-sample days. Reference scores are NaN without one."""
    settings = pipeline.settings
    probs = pipeline.probabilities(model)
    index = probs.index
    rule = pipeline.labels.reindex(index)
    inflation = pipeline.scores["inflation"].reindex(index)
    high = inflation > settings["regimes"]["rule"]["inflation_threshold"]
    shown = probs.idxmax(axis=1)
    years = max((index[-1] - index[0]).days / 365.25, 1e-9)
    runs = spells(rule == "overheating")
    maps = pipeline.state_maps(model)
    named = [bool(((table["name"] == "overheating") & (table["purity"] >= 0.5)).any()) for _, table in maps]
    summary = {
        "overheating_share": float((rule == "overheating").mean()),
        "spells_per_year": float(len(runs) / years),
        "median_spell": float(runs.median()) if len(runs) else float("nan"),
        "shown_share": float((shown == "overheating").mean()),
        "state_share": float(np.mean(named)) if named else float("nan"),
        "inflation_ba": float("nan"),
        "shown_ba": float("nan"),
        "shown_recall": float("nan"),
        "shown_precision": float("nan"),
        "reference_share": float("nan"),
    }
    reference = reference_inflation(pipeline, index)
    source = None
    if reference is not None:
        above, hot, source = reference
        summary["inflation_ba"] = balanced_accuracy(high, above)
        known = hot.notna()
        is_shown = shown == "overheating"
        hot_days = hot[known].astype(bool)
        summary["shown_ba"] = balanced_accuracy(is_shown, hot)
        summary["shown_recall"] = float(is_shown[known][hot_days].mean()) if hot_days.any() else float("nan")
        summary["shown_precision"] = float(hot_days[is_shown[known]].mean()) if is_shown[known].any() else float("nan")
        summary["reference_share"] = float(above[above.notna()].astype(bool).mean())
    return {"summary": summary, "reference": source}


def decide(before: dict, after: dict, settings: dict) -> dict:
    """Pre-registered adoption rule (docs/INFLATION.md), one run, `before` and `after` on the same days.

    `before`/`after`: {"overheating": overheating_report summary, "detection": evaluate() of the model}.
    Adopt only if every condition holds: both Overheating matches better, detection within its targets
    with no episode lost, calibration not worse.
    """
    targets = settings["validation"]["targets"]
    tol = settings["overheating"]["calibration_tolerance"]
    gain = settings["overheating"]["min_gain"]["shown_ba"]
    b, a = before["overheating"], after["overheating"]
    db, da = before["detection"], after["detection"]
    checks = {
        "inflation score matches the reference better (balanced accuracy)": a["inflation_ba"] > b["inflation_ba"],
        f"displayed Overheating matches the reference better by at least {gain:g} (balanced accuracy)": a["shown_ba"]
        >= b["shown_ba"] + gain,
        "no stress episode lost": da["detected"] >= db["detected"],
        f"median latency <= {targets['max_median_latency_days']} days": da["median_latency"]
        <= targets["max_median_latency_days"],
        f"false positives <= {targets['max_false_positives_per_year']} a year": da["false_positives_per_year"]
        <= targets["max_false_positives_per_year"],
        f"false alarm <= {targets['max_false_alarm_share']:.0%} of calm days": da["false_alarm_share"]
        <= targets["max_false_alarm_share"],
        "Brier not higher (3 decimals)": round(da["brier"], 3) <= round(db["brier"], 3) + tol["brier"],
        f"ECE not higher by more than {tol['ece']:g}": round(da["ece"], 3) <= round(db["ece"], 3) + tol["ece"],
    }
    return {"checks": checks, "adopt": all(bool(v) for v in checks.values())}
