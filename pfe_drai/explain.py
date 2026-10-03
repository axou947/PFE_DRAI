"""Explain the regime: which inputs make today's scores, how far the rule is from changing, what moved the alarm.

Read-only. It reuses the pipeline's z-scores, scores and walk-forward fits and changes nothing that is
published or backtested (docs/EXPLAIN.md). Three parts:

1. Score decomposition. A dimension score is the plain average of its inputs' z-scores, so each input
   contributes z / n. The growth score is then averaged over `features.growth.smooth_days` days, so an
   input's contribution to it is the same average of its z / n. Contributions sum to the score exactly.
2. Flip conditions. Which step of the rule (regimes.rule_labels) gives today's label, how far each score is
   from the threshold that would change it, and per input how much its z-score would have to move alone.
   The score is linear in each z, so the needed move is (distance to the threshold) x n. For growth, the
   move is held over the averaging window. Moves beyond the z-score clip cannot happen and are hidden.
3. Alarm drivers. The highest stress source on the day and, for it, an occlusion: each input alone is put
   back to its value of a week earlier, the same fitted model is evaluated again, and the change in its
   probability is reported. This describes what moved the probability; it says nothing about causes.

`explain()` returns plain JSON data; `sentences()` turns it into FR/EN text from i18n templates.
"""

import numpy as np
import pandas as pd

from .features import DIMENSIONS, FEATURES
from .features.build import active_features, align, dimension_scores, growth_inputs, raw_features
from .features.market import INPUT_SETS
from .i18n import fmt_date, fmt_num, fmt_pct, t
from .models import get_model
from .regimes import rule_labels
from .validation import refit_cuts

WEEK, MONTH = 5, 21  # business days
# Displayed unit of each feature: factor from its own unit, and the i18n template (explain.raw.<key>).
# Log changes read as percentages ("about"); yields and breakevens are in percent, shown in basis points.
_UNITS = {
    "vix_level": 1.0,
    "realised_vol": 100.0,
    "credit_stress": 100.0,
    "drawdown": 100.0,
    "equity_momentum": 100.0,
    "curve_slope": 100.0,
    "industrial_production": 100.0,
    "jobless_claims": -100.0,  # the feature is minus the log change of claims: show the change of claims itself
    "cpi_inflation": 100.0,
    "breakeven_level": 100.0,
    "breakeven_change": 100.0,
    "short_rate_change": 100.0,
}
_MIN_CHANGE = 1e-3  # occlusion changes below 0.1 point are not listed


def dimension_inputs(settings: dict) -> dict[str, list[str]]:
    """The features averaged into each dimension score, as features/build.py averages them."""
    inputs = {dim: [f for f, d in active_features(settings).items() if d == dim] for dim in DIMENSIONS}
    inputs["growth"] = growth_inputs(settings)
    return inputs


def smooth_days(settings: dict) -> int:
    days = settings["features"].get("growth", {}).get("smooth_days", 0) or 0
    return int(days) if days > 1 else 1


def contributions(pipeline) -> dict[str, pd.DataFrame]:
    """Each input's contribution to each dimension score, on every day. Rows sum to the score."""
    z = pipeline.features
    out = {}
    for dim, inputs in dimension_inputs(pipeline.settings).items():
        part = z[inputs] / len(inputs)
        if dim == "growth":
            part = part.rolling(smooth_days(pipeline.settings), min_periods=1).mean()
        out[dim] = part
    return out


# ---------------------------------------------------------------- the rule
def rule_step(scores: pd.Series, settings: dict) -> tuple[str, str]:
    """(label, step) of the rule: the first threshold crossed in the order stress, inflation, growth."""
    label = _label(scores, settings)
    step = {"stress": "stress", "overheating": "inflation", "slowdown": "growth"}.get(label, "none")
    return label, step


def _label(scores: pd.Series, settings: dict) -> str:
    return str(rule_labels(pd.DataFrame([scores[DIMENSIONS]]), settings).iloc[0])


def _threshold(dim: str, settings: dict) -> float:
    return float(settings["regimes"]["rule"][f"{dim}_threshold"])


def _crossed(dim: str, value: float, threshold: float) -> bool:
    return value < threshold if dim == "growth" else value > threshold


def score_flips(scores: pd.Series, settings: dict) -> dict[str, dict | None]:
    """Per dimension, the score move that alone changes the rule label, and the label it gives.

    None when moving that score alone cannot change the label (a higher step of the rule decides).
    `score_change` is the exact distance to the threshold; the label changes once the move reaches it
    (leaving a crossed threshold) or just passes it (crossing one: the rule uses strict inequalities).
    """
    now = _label(scores, settings)
    out = {}
    for dim in DIMENSIONS:
        threshold = _threshold(dim, settings)
        moved = scores.copy()
        if _crossed(dim, scores[dim], threshold):
            moved[dim] = threshold  # on the threshold: no longer crossed
        else:
            moved[dim] = np.nextafter(threshold, -np.inf if dim == "growth" else np.inf)
        after = _label(moved, settings)
        out[dim] = None if after == now else {"score_change": float(threshold - scores[dim]), "to": after}
    return out


# ---------------------------------------------------------------- units
def _raw_scales(pipeline, date: pd.Timestamp) -> dict[str, float]:
    """Per feature, the size of one z-score unit in the feature's own unit on `date`.

    Recomputed from the raw series the way features/build.py scales them; a feature whose recomputed
    z-score does not match the pipeline's (the HYG proxy period, a clipped value) gets no unit.
    """
    memo = pipeline.__dict__.setdefault("_explain_raw", {})
    if "raw" not in memo:
        prices = align(pipeline.raw, pipeline.settings["data"].get("publication_lag_days", {}), pipeline.provider.release_dated)
        memo["raw"] = raw_features(prices)
        memo["spread"] = "credit_spread" in prices
    feats, cfg = memo["raw"], pipeline.settings["features"]
    robust = cfg.get("growth", {}).get("scaling", "standard") == "robust"
    scales = {}
    for f in pipeline.features.columns:
        x = feats[f].loc[:date].dropna()
        if len(x) < cfg["zscore_min_periods"] or x.index[-1] != date:
            continue
        if robust and FEATURES[f] == "growth":  # features/build.py scales every growth feature this way
            centre, scale = x.median(), (x.quantile(0.75) - x.quantile(0.25)) / 1.349
        else:
            centre, scale = x.mean(), x.std()
        if not scale > 0:
            continue
        z = (x.iloc[-1] - centre) / scale
        if abs(z) < cfg["zscore_clip"] and abs(z - pipeline.features.at[date, f]) < 1e-6:
            scales[f] = float(scale)
    return scales


def raw_unit_key(feature: str, pipeline) -> str:
    """i18n template for a move in the feature's own unit."""
    if feature == "credit_stress" and pipeline.__dict__.get("_explain_raw", {}).get("spread"):
        return "explain.raw.credit_spread"  # euro area: a spread change in percent, shown in basis points
    return f"explain.raw.{feature}"


# ---------------------------------------------------------------- what-ifs
def what_ifs(pipeline, date: pd.Timestamp, flips: dict[str, dict | None]) -> tuple[list[dict], list[dict]]:
    """Per input, the z-score move that alone flips the rule. Returns (possible, hidden)."""
    settings = pipeline.settings
    clip = float(settings["features"]["zscore_clip"])
    z = pipeline.features
    pos = z.index.get_loc(date)
    window = smooth_days(settings)
    scales = _raw_scales(pipeline, date)
    possible, hidden = [], []
    for dim, inputs in dimension_inputs(settings).items():
        flip = flips[dim]
        if flip is None:
            continue
        rows = z.iloc[max(0, pos - window + 1) : pos + 1] if dim == "growth" else z.iloc[pos : pos + 1]
        for f in inputs:
            dz = flip["score_change"] * len(inputs)
            after = rows[f] + dz
            item = {
                "feature": f,
                "dimension": dim,
                "z": float(z.at[date, f]),
                "z_change": float(dz),
                "to": flip["to"],
                "held_days": int(len(rows)) if dim == "growth" else 1,
            }
            if abs(dz) > clip or (after.abs() > clip).any():
                hidden.append(item)
                continue
            if f in scales:
                item["raw_change"] = float(dz * scales[f] * _UNITS[f])
                item["raw_unit"] = raw_unit_key(f, pipeline)
            possible.append(item)
    possible.sort(key=lambda w: abs(w["z_change"]))
    return possible, hidden


def apply_what_if(pipeline, date, feature: str, z_change: float) -> str:
    """The rule label on `date` once `feature` has moved by `z_change` (held over the growth window).

    Recomputes the scores with features/build.py's own functions: used to check the what-ifs.
    """
    settings = pipeline.settings
    z = pipeline.features
    pos = z.index.get_loc(pd.Timestamp(date))
    window = smooth_days(settings)
    part = z.iloc[max(0, pos - window + 1) : pos + 1].copy()
    if feature in dimension_inputs(settings)["growth"]:
        part[feature] += z_change
    else:
        part.iloc[-1, part.columns.get_loc(feature)] += z_change
    scores = dimension_scores(part, settings).iloc[-1]
    return _label(scores, settings)


# ---------------------------------------------------------------- alarm drivers
def _sources(pipeline, model: str) -> list[str]:
    components = getattr(get_model(model, pipeline.settings), "components", None)
    return list(components) if components else [model]


def _fit_at(pipeline, name: str, pos: int):
    """The walk-forward fit of `name` that predicted day `pos` (same window, same seed: same model),
    and the end of the block of days it predicted in one batch."""
    cuts = refit_cuts(len(pipeline.scores), pipeline.settings, name)
    earlier = [c for c in cuts if c <= pos]
    if not earlier:
        return None, None
    end = min(earlier[-1] + cuts.step, len(pipeline.scores))
    cuts = earlier
    memo = pipeline.__dict__.setdefault("_explain_fits", {})
    key = (name, cuts[-1])
    if key not in memo:
        model = get_model(name, pipeline.settings)
        cut = cuts[-1]
        if model.inputs == "market":
            model.fit(pipeline.market.iloc[:cut], pipeline.scores.iloc[:cut], pipeline.onset.iloc[:cut])
        else:
            model.fit(pipeline.features.iloc[:cut], pipeline.scores.iloc[:cut], pipeline.labels.iloc[:cut])
        memo[key] = model
    return memo[key], end


def _p_stress_scores(model, pipeline, last: pd.Series, pos: int, end: int) -> float:
    """P(stress) on day `pos` of a score-input model when that day's z-scores are `last`.

    Only that day's scores are recomputed (features/build.py's own averages); other days keep theirs.
    The rows passed are those walk-forward passed: the jump model is causal (its state runs from the
    start), k-means scales its distances on the whole batch [0, end), gbm reads 5-day score changes.
    """
    settings = pipeline.settings
    start, stop = {"jump": (0, pos + 1), "kmeans": (0, end)}.get(model.name, (max(0, pos - WEEK), pos + 1))
    features = pipeline.features.iloc[start:stop].copy()
    window = pipeline.features.iloc[max(0, pos - smooth_days(settings) + 1) : pos + 1].copy()
    window.iloc[-1] = last
    scores = pipeline.scores.iloc[start:stop].copy()
    row = pos - start
    features.iloc[row] = last
    scores.iloc[row] = dimension_scores(window, settings).iloc[-1][scores.columns]
    return float(model.predict_proba(features, scores)["stress"].iloc[row])


def alarm_drivers(pipeline, model: str, date: pd.Timestamp, top: int = 5) -> dict:
    """Highest stress source on `date` and the inputs that moved its probability since a week earlier."""
    sources = _sources(pipeline, model)
    values, week = {}, {}
    for name in sources:
        p = pipeline.probabilities(name)["stress"]
        if date in p.index:
            values[name] = float(p.loc[date])
            prior = p.loc[:date]
            week[name] = float(prior.iloc[-1 - WEEK]) if len(prior) > WEEK else None
    out = {"sources": values, "sources_week_ago": week, "highest": None, "drivers": {"available": False}}
    if not values:
        return out
    highest = max(values, key=values.get)
    out["highest"] = highest
    try:
        out["drivers"] = _occlusion(pipeline, highest, date, values[highest], top)
    except Exception as exc:  # noqa: BLE001 - a model that cannot be re-evaluated is reported, not guessed
        out["drivers"] = {"available": False, "reason": type(exc).__name__}
    return out


def _occlusion(pipeline, name: str, date: pd.Timestamp, published: float, top: int) -> dict:
    idx = pipeline.scores.index
    pos = idx.get_loc(date)
    if pos < WEEK:
        return {"available": False, "reason": "history"}
    fitted, end = _fit_at(pipeline, name, pos)
    if fitted is None:
        return {"available": False, "reason": "history"}
    week_day = idx[pos - WEEK]
    if fitted.inputs == "market":
        hold = int(fitted.cfg.get("hold_days", 1))  # the probability holds `hold_days`: re-evaluate them all
        frame = pipeline.market.iloc[max(0, pos - hold + 1) : pos + 1]
        columns = [c for c in INPUT_SETS[fitted.cfg["inputs"]] if c in getattr(fitted, "columns", [])]

        def evaluate(last):
            f = frame.copy()
            f.iloc[-1] = last
            return float(fitted.predict_proba(f, None)["stress"].iloc[-1])

        kind, today, before = "market", pipeline.market.loc[date], pipeline.market.loc[week_day]
    else:

        def evaluate(last):
            return _p_stress_scores(fitted, pipeline, last, pos, end)

        kind, today, before = "feature", pipeline.features.loc[date], pipeline.features.loc[week_day]
        columns = list(today.index)
    base = evaluate(today)
    rows = []
    for c in columns:
        now, then = today[c], before[c]
        if not (now == now and then == then) or now == then:
            continue
        occluded = today.copy()
        occluded[c] = then
        change = base - evaluate(occluded)
        if abs(change) >= _MIN_CHANGE:
            rows.append({"input": c, "kind": kind, "value": float(now), "week_ago": float(then), "change": float(change)})
    rows.sort(key=lambda r: -abs(r["change"]))
    return {
        "available": True,
        "source": name,
        "probability": base,
        "reproduced": bool(abs(base - published) < 1e-9),
        "week_ago_date": week_day.date().isoformat(),
        "inputs": rows[:top],
    }


# ---------------------------------------------------------------- everything
def explain(pipeline, model: str | None = None, date=None) -> dict:
    """Why the regime on `date` (default: latest) is what it is. JSON-serialisable."""
    settings = pipeline.settings
    state = pipeline.state(model, date)
    date, model = state.date, state.model
    scores = pipeline.scores
    pos = scores.index.get_loc(date)
    days = {"today": date, "week_ago": scores.index[max(0, pos - WEEK)], "month_ago": scores.index[max(0, pos - MONTH)]}
    parts = contributions(pipeline)
    inputs = dimension_inputs(settings)

    dimensions = {}
    for dim in DIMENSIONS:
        part = parts[dim]
        rows = []
        for f in inputs[dim]:
            c = {k: float(part.at[d, f]) for k, d in days.items()}
            rows.append(
                {
                    "feature": f,
                    "z": float(pipeline.features.at[date, f]),
                    "contribution": c["today"],
                    "week_ago": c["week_ago"],
                    "month_ago": c["month_ago"],
                    "change_week": c["today"] - c["week_ago"],
                    "change_month": c["today"] - c["month_ago"],
                }
            )
        rows.sort(key=lambda r: -abs(r["contribution"]))
        s = {k: float(scores.at[d, dim]) for k, d in days.items()}
        entry = {
            "score": s["today"],
            "threshold": _threshold(dim, settings),
            "crossed": _crossed(dim, s["today"], _threshold(dim, settings)),
            "week_ago": s["week_ago"],
            "month_ago": s["month_ago"],
            "change_week": s["today"] - s["week_ago"],
            "change_month": s["today"] - s["month_ago"],
            "n_inputs": len(inputs[dim]),
            "smooth_days": smooth_days(settings) if dim == "growth" else 1,
            "contributions": rows,
        }
        if dim == "growth":
            entry["same_day_average"] = float(pipeline.features.loc[date, inputs[dim]].mean())
        dimensions[dim] = entry

    label, step = rule_step(scores.loc[date], settings)
    flips = score_flips(scores.loc[date], settings)
    reachable = {d: f for d, f in flips.items() if f is not None}
    nearest = min(reachable, key=lambda d: abs(reachable[d]["score_change"])) if reachable else None
    possible, hidden = what_ifs(pipeline, date, flips)
    alarm = dict(state.alarm)
    alarm.update(alarm_drivers(pipeline, model, date))
    return {
        "date": date.date().isoformat(),
        "model": model,
        "regime": state.regime,
        "dates": {k: d.date().isoformat() for k, d in days.items()},
        "rule": {"label": label, "step": step, "agrees_with_model": label == state.regime},
        "dimensions": dimensions,
        "flip": {
            "nearest": {"dimension": nearest, **reachable[nearest]} if nearest else None,
            "dimensions": flips,
            "what_if": possible,
            "hidden": [{"feature": h["feature"], "z_change": h["z_change"], "to": h["to"]} for h in hidden],
            "clip": float(settings["features"]["zscore_clip"]),
        },
        "alarm": alarm,
    }


# ---------------------------------------------------------------- words
def _num(value: float, lang: str, digits: int = 2) -> str:
    return fmt_num(value, lang, digits).replace("-", "−")


def _plain(value: float, lang: str, digits: int = 2) -> str:
    return _num(value, lang, digits).lstrip("+")


def _pts(value: float, lang: str) -> str:
    return t("explain.pts", lang, value=_num(value * 100, lang, 1))


def input_label(name: str, kind: str, lang: str) -> str:
    return t(f"{'market' if kind == 'market' else 'feature'}.{name}", lang)


def dimension_sentence(info: dict, dim: str, lang: str) -> str:
    """One plain sentence per dimension, from the i18n template explain.why.<dim>."""
    above = info["score"] > info["threshold"]
    top = [c for c in info["contributions"] if abs(c["contribution"]) >= 0.005][:2]
    tops = ", ".join(f"{input_label(c['feature'], 'feature', lang)} ({_num(c['contribution'], lang)})" for c in top)
    return t(
        f"explain.why.{dim}",
        lang,
        score=_num(info["score"], lang),
        side=t("explain.above" if above else "explain.below", lang),
        threshold=_plain(info["threshold"], lang),
        top=tops or t("explain.none", lang),
        change=_num(info["change_week"], lang),
        days=info["smooth_days"],
        raw=_num(info.get("same_day_average", info["score"]), lang),
    )


def what_if_line(w: dict, lang: str) -> str:
    raw = ""
    if "raw_change" in w:
        raw = t("explain.about", lang, value=t(w["raw_unit"], lang, value=_num(w["raw_change"], lang, 1)))
    return t(
        "explain.what_if",
        lang,
        feature=t(f"feature.{w['feature']}", lang),
        move=_num(w["z_change"], lang),
        raw=raw,
        regime=t(f"regime.{w['to']}", lang),
    )


def sentences(exp: dict, lang: str = "fr") -> dict:
    """The explanation as text: templates only, no generated wording. Descriptive, never advice."""
    reg = lambda r: t(f"regime.{r}", lang)  # noqa: E731
    rule = exp["rule"]
    model = t(f"model.{exp['model']}", lang)
    differs = t("explain.model_differs", lang, model=model, regime=reg(exp["regime"]), rule=reg(rule["label"]))
    lines = {
        "rule": t(f"explain.rule.{rule['step']}", lang, regime=reg(rule["label"])),
        "model": "" if rule["agrees_with_model"] else differs,
        "dimensions": {d: dimension_sentence(exp["dimensions"][d], d, lang) for d in DIMENSIONS},
    }
    flip = exp["flip"]
    nearest = flip["nearest"]
    lines["nearest"] = (
        t(
            "explain.nearest",
            lang,
            dimension=t(f"dimension.{nearest['dimension']}", lang).lower(),
            move=_num(nearest["score_change"], lang),
            regime=reg(nearest["to"]),
        )
        if nearest
        else t("explain.no_flip", lang)
    )
    lines["what_if"] = [what_if_line(w, lang) for w in flip["what_if"]]
    hidden = t("explain.hidden", lang, n=len(flip["hidden"]), clip=_plain(flip["clip"], lang, 0))
    lines["hidden"] = hidden if flip["hidden"] else ""
    held = {w["held_days"] for w in flip["what_if"] if w["dimension"] == "growth"}
    lines["held"] = t("explain.held", lang, days=max(held)) if held and max(held) > 1 else ""

    alarm = exp["alarm"]
    if alarm.get("highest"):
        source = alarm["highest"]
        week = alarm["sources_week_ago"].get(source)
        lines["alarm"] = t(
            "explain.alarm_on" if alarm["on"] else "explain.alarm_off",
            lang,
            source=t(f"model.{source}", lang),
            value=fmt_pct(alarm["sources"][source], lang),
            week=fmt_pct(week, lang) if week is not None else "n/a",
            threshold=fmt_pct(alarm["threshold"], lang),
        )
    else:
        lines["alarm"] = ""
    drivers = alarm.get("drivers", {})
    if drivers.get("available"):
        lines["occlusion"] = t("explain.occlusion", lang, date=fmt_date(pd.Timestamp(drivers["week_ago_date"]), lang))
        lines["occlusion_items"] = [
            t("explain.occlusion_item", lang, input=input_label(r["input"], r["kind"], lang), change=_pts(r["change"], lang))
            for r in drivers["inputs"]
        ] or [t("explain.occlusion_none", lang)]
    else:
        lines["occlusion"] = t("explain.occlusion_na", lang)
        lines["occlusion_items"] = []
    return lines


def note_lines(exp: dict, lang: str = "fr") -> list[str]:
    """4 to 6 lines for the committee note."""
    text = sentences(exp, lang)
    lines = [text["rule"] + (" " + text["model"] if text["model"] else "")]
    lines += [text["dimensions"][d] for d in DIMENSIONS]
    lines.append(text["nearest"])
    if text["alarm"]:
        top = exp["alarm"]["drivers"].get("inputs", [])[:3] if exp["alarm"]["drivers"].get("available") else []
        moved = "; ".join(text["occlusion_items"][: len(top)]) if top else ""
        lines.append(text["alarm"] + (" " + t("explain.note_moved", lang, items=moved) if moved else ""))
    return lines[:6]
