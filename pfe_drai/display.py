"""Which calm regime the combined model displays (docs/SLOWDOWN_V23.md).

The combined model's P(stress) is the calibrated detector score; what is left (1 - P(stress)) is shared
between the calm regimes, Expansion, Overheating and Slowdown. `models.combined.calm` sets how:

- `jump` (v2.2, the default): in the jump model's proportions (models/combined.py);
- `rule`: all of it to the rule's calm regime of that day (overheating if inflation is above its
  threshold, else slowdown if growth is below its threshold, else expansion: the rule of regimes.py
  without its stress step), once that regime has held `validation.confirm_days` days in a row;
- `gbm`: in the proportions of gbm's calm regimes (gbm learns the rule's regimes, one week ahead).

P(stress) is never touched, so the stress alarm, its episodes and the calibration are the same day for
day whatever the setting. Only the label and the calm bars change.
"""

import pandas as pd

CALM = ("expansion", "overheating", "slowdown")


def calm_mode(settings: dict) -> str:
    return settings["models"].get("combined", {}).get("calm", "jump")


def rule_calm(scores: pd.DataFrame, settings: dict) -> pd.Series:
    """The rule's regime without its stress step: what the economy looks like apart from markets."""
    rule = settings["regimes"]["rule"]
    label = pd.Series("expansion", index=scores.index)
    label[scores["growth"] < rule["growth_threshold"]] = "slowdown"
    label[scores["inflation"] > rule["inflation_threshold"]] = "overheating"
    return label


def confirmed(label: pd.Series, days: int) -> pd.Series:
    """`label`, changing only once a new value has held `days` days in a row (the first value stands at once)."""
    out, current, run, last = [], None, 0, None
    for value in label:
        run = run + 1 if value == last else 1
        last = value
        if current is None or run >= days:
            current = value
        out.append(current)
    return pd.Series(out, index=label.index)


def _named_row(values, name: str) -> list[float]:
    order = sorted(range(len(CALM)), key=lambda i: -values[i])
    top = values[order[0]]
    rest = [values[i] for i in range(len(CALM)) if i != order[0]]
    return [top if regime == name else rest.pop(0) for regime in CALM]


def calm_display(probs: pd.DataFrame, scores: pd.DataFrame, gbm: pd.DataFrame | None, settings: dict) -> pd.DataFrame:
    """`probs` with its calm share split as `models.combined.calm` says; P(stress) unchanged."""
    mode = calm_mode(settings)
    if mode == "jump":
        return probs
    calm_mass = 1 - probs["stress"]
    if mode == "rule":
        label = confirmed(rule_calm(scores.reindex(probs.index), settings), settings["validation"]["confirm_days"])
        share = pd.DataFrame({r: (label == r).astype(float) for r in CALM}, index=probs.index)
    elif mode == "rule_named":
        label = confirmed(rule_calm(scores.reindex(probs.index), settings), settings["validation"]["confirm_days"])
        jump = probs[list(CALM)]
        # The calm shares stay the jump model's, sorted: the rule's calm regime takes the largest one,
        # the two others the rest in the jump model's order. Stress is shown on the same days as before.
        ranked = pd.DataFrame(
            [_named_row(row, name) for row, name in zip(jump.to_numpy(), label, strict=True)],
            index=probs.index,
            columns=list(CALM),
        )
        out = ranked.copy()
        out["stress"] = probs["stress"]
        return out[probs.columns]
    elif mode == "gbm":
        if gbm is None:
            raise ValueError("models.combined.calm: gbm needs gbm's probabilities")
        part = gbm.reindex(probs.index)[list(CALM)]
        total = part.sum(axis=1)
        # Where gbm has nothing to say (all on stress, or no prediction yet), keep the jump model's split.
        jump = probs[list(CALM)].div((1 - probs["stress"]).where(lambda s: s > 0), axis=0).fillna(1 / len(CALM))
        share = part.div(total.where(total > 0), axis=0).fillna(jump)
    else:
        raise ValueError(f"models.combined.calm must be jump, rule or gbm, not '{mode}'")
    out = share.mul(calm_mass, axis=0)
    out["stress"] = probs["stress"]
    return out[probs.columns]
