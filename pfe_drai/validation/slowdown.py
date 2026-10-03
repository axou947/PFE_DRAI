"""Is Slowdown a real regime? Checks against a growth reference the models never see (docs/SLOWDOWN.md).

The rule calls a day "Slowdown" when the growth score is below its threshold (and neither stress nor
overheating applies). Nothing in the model checks that this matches the economy, so this module
compares it with an outside reference of below-trend growth:

- simulated data: the simulator's hidden regime (slowdown or stress = growth below trend);
- real data: the Chicago Fed National Activity Index, 3-month average (FRED `CFNAIMA3`), below 0.
  It is a weighted average of 85 monthly activity indicators, built so that 0 means growth at its
  historical trend. It is used as published today (revised): it is the answer, never an input.
  Each month's value applies to the days of that month.

Scores, on the model's out-of-sample days:
- growth balanced accuracy: does "growth score below threshold" match below-trend growth?
  (average of the shares found on below-trend days and on the other days);
- persistence of the rule's Slowdown: spells a year and their median length (a regime that changes
  every few days cannot be a state of the economy);
- displayed Slowdown: does the regime the model displays say Slowdown on the reference's slowdown
  days (below trend, outside any stress episode; simulated: the hidden slowdown regime)? Balanced
  accuracy, plus the share of those days found (recall) and the share of the days displayed as
  Slowdown that are reference slowdown days (precision);
- named state: share of walk-forward refits where one of the jump model's states is named Slowdown
  and at least half of its training days are Slowdown by the rule.
"""

import os

import numpy as np
import pandas as pd

from .episodes import episode_mask


def reference_growth(pipeline, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series, str] | None:
    """(below-trend growth, slowdown reference, source name) on `index`, None without a reference."""
    truth = pipeline.truth
    if truth is not None:
        truth = truth.reindex(index)
        return truth.isin(["slowdown", "stress"]), truth == "slowdown", "simulated regimes"
    activity = activity_index(pipeline.settings, index[0], index[-1])
    if activity is None:
        return None
    below = below_trend(activity, index, pipeline.settings)
    outside = ~episode_mask(index, pipeline.episodes)
    cfg = pipeline.settings["validation"]["slowdown"]
    slow = (below.fillna(False).astype(bool) & outside).where(below.notna())
    return below, slow, f"{cfg['reference']['fred']} < {cfg['reference']['below']:g}"


def activity_index(settings: dict, start, end) -> pd.Series | None:
    """The reference activity index from FRED (monthly, latest vintage), None for other providers."""
    if settings["data"]["provider"] != "fred":
        return None
    from ..data.fred import fetch_fred

    key = os.environ.get(settings["data"]["fred_api_key_env"])
    if not key:
        return None
    series_id = settings["validation"]["slowdown"]["reference"]["fred"]
    return fetch_fred(series_id, key, pd.Timestamp(start) - pd.offsets.MonthBegin(2), end)


def below_trend(activity: pd.Series, index: pd.DatetimeIndex, settings: dict) -> pd.Series:
    """Each month's reading on the days of that month (it describes the month, whenever it came out)."""
    months = pd.Series(activity.to_numpy(), index=activity.index.to_period("M"))
    value = pd.Series(months.reindex(index.to_period("M")).to_numpy(), index=index)
    return (value < settings["validation"]["slowdown"]["reference"]["below"]).where(value.notna())


def balanced_accuracy(predicted: pd.Series, actual: pd.Series) -> float:
    known = actual.notna()
    predicted, actual = predicted[known].astype(bool), actual[known].astype(bool)
    if not actual.any() or actual.all():
        return float("nan")
    return float((predicted[actual].mean() + (~predicted[~actual]).mean()) / 2)


def spells(mask: pd.Series) -> pd.Series:
    """Length in days of each run of True."""
    mask = mask.astype(bool)
    run = (mask != mask.shift()).cumsum()[mask]
    return run.groupby(run).size()


def slowdown_report(pipeline, model: str | None = None) -> dict:
    """Every score above for `model`, on its out-of-sample days. Reference scores are NaN without one."""
    settings = pipeline.settings
    probs = pipeline.probabilities(model)
    index = probs.index
    rule = pipeline.labels.reindex(index)
    growth = pipeline.scores["growth"].reindex(index)
    low = growth < settings["regimes"]["rule"]["growth_threshold"]
    shown = probs.idxmax(axis=1)
    years = max((index[-1] - index[0]).days / 365.25, 1e-9)
    runs = spells(rule == "slowdown")
    maps = pipeline.state_maps(model)
    named = [bool(((table["name"] == "slowdown") & (table["purity"] >= 0.5)).any()) for _, table in maps]
    summary = {
        "slowdown_share": float((rule == "slowdown").mean()),
        "spells_per_year": float(len(runs) / years),
        "median_spell": float(runs.median()) if len(runs) else float("nan"),
        "shown_share": float((shown == "slowdown").mean()),
        "state_share": float(np.mean(named)) if named else float("nan"),
        "growth_ba": float("nan"),
        "shown_ba": float("nan"),
        "shown_recall": float("nan"),
        "shown_precision": float("nan"),
        "reference_share": float("nan"),
    }
    reference = reference_growth(pipeline, index)
    source = None
    if reference is not None:
        below, slow, source = reference
        summary["growth_ba"] = balanced_accuracy(low, below)
        known = slow.notna()
        is_shown = shown == "slowdown"
        slow_days = slow[known].astype(bool)
        summary["shown_ba"] = balanced_accuracy(is_shown, slow)
        summary["shown_recall"] = float(is_shown[known][slow_days].mean()) if slow_days.any() else float("nan")
        summary["shown_precision"] = float(slow_days[is_shown[known]].mean()) if is_shown[known].any() else float("nan")
        summary["reference_share"] = float(below[below.notna()].astype(bool).mean())
    states = pd.DataFrame(
        [
            {
                "first_day": day,
                "slowdown_states": int((table["name"] == "slowdown").sum()),
                "best_agreement": float(table.loc[table["name"] == "slowdown", "purity"].max())
                if (table["name"] == "slowdown").any()
                else float("nan"),
                "named": ok,
            }
            for (day, table), ok in zip(maps, named, strict=True)
        ]
    )
    return {"summary": summary, "reference": source, "states": states}


# ---------------------------------------------------------------- holdout (1999-2009, real data)
GROWTH_SERIES = ["equity", "us10y", "us2y", "indpro", "claims"]


def growth_holdout(settings: dict, candidates: list[dict] | None = None, extra: dict | None = None) -> dict:
    """Pre-registered holdout of the growth score candidates (docs/SLOWDOWN.md).

    US data before the real out-of-sample period (validation.holdout: SPY from 1993 to 2009-04-02),
    the growth score of each candidate in `validation.slowdown.holdout.candidates`, compared with the
    activity index from `evaluate_from` on. Only the growth score is involved: no model is fitted, and
    the stress and inflation series mostly start in 2002-2003.

    `candidates` (default: the slowdown holdout's) and `extra` ({series name: publication lag in days},
    series of the TESTED catalog) let another pre-registered test reuse it (docs/SAHM_HY.md); then the
    v2.1 comparison row and the slowdown selection rule are left out.
    """
    from ..config import _deep_merge
    from ..data import get_provider
    from ..features.build import align, growth_features, growth_score, growth_zscores

    window = settings["validation"]["holdout"]
    cfg = settings["validation"]["slowdown"]["holdout"]
    start, end = pd.Timestamp(window["start"]), pd.Timestamp(window["end"])
    provider = get_provider(settings)
    names = GROWTH_SERIES + list(extra or {})
    raw = provider.fetch_subset(names, start, end)
    missing = [name for name in names if name not in raw or raw[name].empty]
    if missing:
        raise ValueError(f"The growth holdout needs {', '.join(missing)} from provider '{provider.name}'")
    raw = {name: series.loc[:end] for name, series in raw.items()}
    lags = {**settings["data"].get("publication_lag_days", {}), **(extra or {})}
    prices = align(raw, lags, provider.release_dated)
    feats = growth_features(prices)
    index = prices.index[prices.index >= pd.Timestamp(cfg["evaluate_from"])]
    truth = provider.truth()
    if truth is not None:
        below = truth.reindex(index).isin(["slowdown", "stress"])
        source = "simulated regimes"
    else:
        activity = activity_index(settings, index[0], index[-1])
        if activity is None:
            raise ValueError("The growth holdout needs the activity index: run it with --provider fred")
        below = below_trend(activity, index, settings)
        ref = settings["validation"]["slowdown"]["reference"]
        source = f"{ref['fred']} < {ref['below']:g}"
    years = (index[-1] - index[0]).days / 365.25
    rows = []
    # The growth score until v2.1 is shown for comparison; it is not a candidate.
    before = {"name": "until v2.1 (comparison only)", **settings["validation"]["slowdown"]["before"]}
    listed = [*enumerate(candidates)] if candidates is not None else [(None, before), *enumerate(cfg["candidates"])]
    for i, candidate in listed:
        s = _deep_merge(settings, {"features": {"growth": candidate["growth"]}, "regimes": {"rule": candidate["rule"]}})
        growth = growth_score(growth_zscores(feats, s), s).reindex(index)
        low = (growth < s["regimes"]["rule"]["growth_threshold"]).where(growth.notna())
        runs = spells(low.fillna(False))
        rows.append(
            {
                "candidate": candidate["name"],
                "order": i,
                "days": int(growth.notna().sum()),
                "balanced_accuracy": balanced_accuracy(low.dropna().astype(bool), below.reindex(low.dropna().index)),
                "below_share": float(low.dropna().astype(bool).mean()),
                "spells_per_year": float(len(runs) / years),
                "median_spell": float(runs.median()) if len(runs) else float("nan"),
            }
        )
    table = pd.DataFrame(rows)
    return {
        "provider": provider.name,
        "is_live": provider.is_live,
        "first_day": index[0],
        "last_day": index[-1],
        "reference": source,
        "reference_share": float(below.dropna().astype(bool).mean()),
        "rows": table,
        "chosen": select_growth(table, settings) if candidates is None else None,
    }


def sahm_holdout(settings: dict) -> dict:
    """Step 1 of the Sahm rule test (docs/SAHM_HY.md): v2.2's growth score against v2.2 + the Sahm gap, same window
    and reference as the growth holdout. Passes when the Sahm candidate changes at most `max_spells_per_year` times a
    year and its balanced accuracy beats v2.2's by at least `min_gain`."""
    cfg = settings["sahm"]
    res = growth_holdout(settings, cfg["holdout"]["candidates"], {cfg["series"]: cfg["publication_lag_days"]})
    rows = res["rows"]
    base, sahm = rows.iloc[0], rows.iloc[1]
    gain = float(sahm["balanced_accuracy"] - base["balanced_accuracy"])
    limit = settings["validation"]["slowdown"]["holdout"]["max_spells_per_year"]
    res["checks"] = {
        f"balanced accuracy at least {cfg['min_gain']['balanced_accuracy']:g} above v2.2's (gain {gain:+.3f})": gain
        >= cfg["min_gain"]["balanced_accuracy"] - 1e-12,
        f"Slowdown changes at most {limit:g} times a year": bool(sahm["spells_per_year"] <= limit),
    }
    res["passed"] = all(res["checks"].values())
    return res


def select_growth(rows: pd.DataFrame, settings: dict):
    """Pre-registered rule (docs/SLOWDOWN.md): candidates whose rule Slowdown changes at most
    `max_spells_per_year` times a year; among them the highest balanced accuracy, a candidate within
    `tie` of the best counting as tied; ties go to the earlier candidate in the list."""
    cfg = settings["validation"]["slowdown"]["holdout"]
    ok = rows[rows["order"].notna() & (rows["spells_per_year"] <= cfg["max_spells_per_year"]) & rows["balanced_accuracy"].notna()]
    if ok.empty:
        return None
    best = ok["balanced_accuracy"].max()
    return ok[ok["balanced_accuracy"] >= best - cfg["tie"]].sort_values("order").index[0]


# ---------------------------------------------------------------- decision on real data
def decide(before: dict, after: dict, settings: dict) -> dict:
    """Pre-registered adoption rule (docs/SLOWDOWN.md), one run, `before` and `after` on the same days.

    `before`/`after`: {"slowdown": slowdown_report summary, "detection": evaluate() of the model}.
    Returns each condition with its result and the decision (adopt only if every condition holds).
    """
    targets = settings["validation"]["targets"]
    tol = settings["validation"]["slowdown"]["calibration_tolerance"]
    b, a = before["slowdown"], after["slowdown"]
    db, da = before["detection"], after["detection"]
    checks = {
        "growth score matches the reference better (balanced accuracy)": a["growth_ba"] > b["growth_ba"],
        "a state is named Slowdown (agreement >= 50%) in at least half the refits": a["state_share"] >= 0.5,
        "displayed Slowdown matches the reference better (balanced accuracy)": a["shown_ba"] > b["shown_ba"],
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
