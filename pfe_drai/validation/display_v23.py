"""Displayed Slowdown v2.3: the pre-registered selection and decision, in one run (docs/SLOWDOWN_V23.md).

The model is run once (v2.2 settings). Every candidate display is computed from the same out-of-sample
probabilities (display.calm_display); P(stress) is the same in all of them, which the run checks.

- Selection on the first part of the out-of-sample period (before `split`), against the activity index
  reference (CFNAIMA3 < 0, outside stress episodes; simulated: the hidden slowdown regime).
- Decision on the second part (from `split`), never used to choose, and on the whole period against a
  second reference no version of the model was ever scored against: real GDP growing slower than the
  Congressional Budget Office's potential GDP that quarter (FRED GDPC1 and GDPPOT).
"""

import os

import numpy as np
import pandas as pd

from ..config import _deep_merge
from ..display import calm_display
from .episodes import episode_mask
from .slowdown import balanced_accuracy, reference_growth, spells


def display_scores(shown: pd.Series, slow: pd.Series) -> dict:
    """Displayed Slowdown against a slowdown reference on the same days (reference NaN = unknown day)."""
    years = max((shown.index[-1] - shown.index[0]).days / 365.25, 1e-9)
    is_slow = shown == "slowdown"
    runs = spells(is_slow)
    known = slow.notna()
    ref = slow[known].astype(bool)
    hit = is_slow[known]
    return {
        "ba": balanced_accuracy(is_slow, slow),
        "recall": float(hit[ref].mean()) if ref.any() else float("nan"),
        "precision": float(ref[hit].mean()) if hit.any() else float("nan"),
        "base_rate": float(ref.mean()) if len(ref) else float("nan"),
        "shown_share": float(is_slow.mean()),
        "switches_per_year": float((shown != shown.shift()).iloc[1:].sum() / years),
        "median_spell": float(runs.median()) if len(runs) else float("nan"),
    }


def gdp_reference(pipeline, index: pd.DatetimeIndex) -> pd.Series | None:
    """Slowdown by the second reference on `index`: real GDP growth below potential GDP growth that quarter,
    outside stress episodes. Latest vintages (evaluation only). None without FRED or a key."""
    settings = pipeline.settings
    if settings["data"]["provider"] != "fred":
        return None
    key = os.environ.get(settings["data"]["fred_api_key_env"])
    if not key:
        return None
    from ..data.fred import fetch_fred

    cfg = settings["slowdown_v23"]["second_reference"]
    start = pd.Timestamp(index[0]) - pd.offsets.QuarterBegin(3, startingMonth=1)
    actual = fetch_fred(cfg["actual"], key, start, index[-1])
    potential = fetch_fred(cfg["potential"], key, start, index[-1])
    return below_potential(actual, potential, index, pipeline.episodes)


def below_potential(actual: pd.Series, potential: pd.Series, index: pd.DatetimeIndex, episodes) -> pd.Series:
    """Each quarter's "actual grew slower than potential" on the days of that quarter, outside stress episodes."""
    frame = pd.concat({"a": actual, "p": potential}, axis=1).dropna()
    growth = np.log(frame).diff().dropna()
    below = pd.Series((growth["a"] < growth["p"]).to_numpy(), index=growth.index.to_period("Q"))
    value = pd.Series(below.reindex(index.to_period("Q")).to_numpy(), index=index)
    outside = ~episode_mask(index, episodes)
    return (value.fillna(False).astype(bool) & outside).where(value.notna())


def run_v23(pipeline, model: str | None = None) -> dict:
    """Every candidate display on both parts and the whole period, the selection and the decision."""
    settings = pipeline.settings
    cfg = settings["slowdown_v23"]
    model = model or settings["models"]["default"]
    probs = pipeline.probabilities(model)
    index = probs.index
    gbm = pipeline.probabilities("gbm") if "gbm" in cfg["candidates"] else None
    displays = {cfg["baseline"]: probs}
    for name in cfg["candidates"]:
        s = _deep_merge(settings, {"models": {"combined": {"calm": name}}})
        displays[name] = calm_display(probs, pipeline.scores, gbm, s)
    same_stress = all(np.allclose(d["stress"], probs["stress"]) for d in displays.values())
    shown = {name: d.idxmax(axis=1) for name, d in displays.items()}

    reference = reference_growth(pipeline, index)
    slow = reference[1] if reference is not None else None
    second = gdp_reference(pipeline, index) if pipeline.truth is None else None
    split = pd.Timestamp(cfg["split"])
    parts = {"selection": index < split, "decision": index >= split, "whole": np.ones(len(index), bool)}
    table = {}
    for name, label in shown.items():
        for part, mask in parts.items():
            ref = slow[mask] if slow is not None else pd.Series(np.nan, index=index[mask])
            table[(name, part)] = display_scores(label[mask], ref)
        if second is not None:
            table[(name, "second")] = display_scores(label, second)
    result = {
        "first_day": index[0],
        "last_day": index[-1],
        "split": split,
        "reference": reference[2] if reference is not None else None,
        "second_reference": second is not None,
        "same_stress": same_stress,
        "table": table,
        "names": list(shown),
    }
    if slow is None:
        return result
    result["chosen"] = select(table, cfg)
    # The second reference exists on real data only; simulated data has its hidden regimes instead.
    result["decision"] = decide_v23(table, result["chosen"], cfg, pipeline.truth is None, same_stress)
    return result


def select(table: dict, cfg: dict) -> str | None:
    """Pre-registered selection on the first part: candidates within the guards, highest balanced accuracy
    (within `tie` of the best counts as tied, ties to the earlier candidate), and only if it beats the
    baseline's by `min_gain`."""
    g, sel = cfg["guards"], cfg["select"]
    rows = {name: table[(name, "selection")] for name in cfg["candidates"]}

    def within(r):
        return r["switches_per_year"] <= g["max_switches_per_year"] and r["median_spell"] >= g["min_median_spell"]

    ok = {name: r for name, r in rows.items() if within(r) and r["ba"] == r["ba"]}
    if not ok:
        return None
    best = max(r["ba"] for r in ok.values())
    chosen = next(name for name in cfg["candidates"] if name in ok and ok[name]["ba"] >= best - sel["tie"])
    base = table[(cfg["baseline"], "selection")]["ba"]
    return chosen if ok[chosen]["ba"] >= base + sel["min_gain"] - 1e-12 else None


def decide_v23(table: dict, chosen: str | None, cfg: dict, needs_second: bool, same_stress: bool) -> dict:
    """Pre-registered decision (docs/SLOWDOWN_V23.md): every condition must hold."""
    if chosen is None:
        return {"checks": {"a candidate is selected on the first part": False}, "adopt": False}
    d, g, base = cfg["decide"], cfg["guards"], cfg["baseline"]
    new, old = table[(chosen, "decision")], table[(base, "decision")]
    whole = table[(chosen, "whole")]
    checks = {
        "a candidate is selected on the first part": True,
        f"second part: displayed Slowdown balanced accuracy >= {d['min_ba']:g}": new["ba"] >= d["min_ba"],
        f"second part: at least {d['min_gain']:g} above v2.2's": new["ba"] >= old["ba"] + d["min_gain"] - 1e-12,
        "second part: finds at least as many reference slowdown days as v2.2": new["recall"] >= old["recall"],
        "second part: shown Slowdown days are reference slowdown more often than an average day": new["precision"]
        > new["base_rate"],
    }
    if (chosen, "second") in table:
        sec_new, sec_old = table[(chosen, "second")], table[(base, "second")]
        checks[f"GDP below potential (never used before): above 0.5 and at least {d['min_gain']:g} above v2.2's"] = (
            sec_new["ba"] > 0.5 and sec_new["ba"] >= sec_old["ba"] + d["min_gain"] - 1e-12
        )
    elif needs_second:
        checks["GDP below potential (never used before): reference available"] = False
    checks[f"whole period: regime switches <= {g['max_switches_per_year']:g} a year"] = (
        whole["switches_per_year"] <= g["max_switches_per_year"]
    )
    checks[f"whole period: median displayed Slowdown spell >= {g['min_median_spell']:g} days"] = (
        whole["median_spell"] >= g["min_median_spell"]
    )
    checks["P(stress) identical on every day (alarm, episodes, Brier, ECE unchanged)"] = same_stress
    return {"checks": checks, "adopt": all(bool(v) for v in checks.values())}
