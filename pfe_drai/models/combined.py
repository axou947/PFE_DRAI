"""Combined signal: the jump model's regimes, with the stress probability from faster models.

The jump model is persistent and slow to switch; the stress sources react within days but
flicker. The highest stress probability of them all (the detector score) keeps the jump model's
calm regimes and catches a crisis as soon as any model sees it. The other regimes keep the jump
model's proportions and share what is left, so rows still sum to 1.

Stress sources are set in models.combined.stress_sources: [gbm] since PR #5 (docs/DETECTION.md);
[gbm, onset] is the pre-registered v2 (docs/DETECTION_V2.md). Both sources look one week
ahead, so P(stress) reads "stress now or within a week".

`stress_combination` sets the P(stress) shown and published:
- `max` (v1, v2): the detector score itself;
- `calibrated` (docs/CALIBRATION.md): the detector score turned into a probability by Platt scaling,
  refitted walk-forward on past days (models/calibrator.py). The stress alarm stays on the detector
  score either way (validation/metrics.py), so detection does not change.
"""

import pandas as pd

from .base import RegimeModel, get_model, register
from .calibrator import Calibrated, calibrate_walk_forward


def detector_score(*parts: pd.DataFrame) -> pd.Series:
    """Highest stress probability of the jump model and the stress sources: what the alarm reads."""
    return pd.concat([part["stress"] for part in parts], axis=1).dropna().max(axis=1).rename("stress")


def combine(jump: pd.DataFrame, *sources: pd.DataFrame, stress: pd.Series | None = None) -> pd.DataFrame:
    """Jump model regimes with P(stress) = the detector score, or `stress` when given (calibrated)."""
    stress = detector_score(jump, *sources) if stress is None else stress
    idx = jump.index.intersection(stress.index)
    jump, stress = jump.loc[idx], stress.loc[idx]
    others = jump.drop(columns="stress")
    total = others.sum(axis=1)
    # When the jump model puts everything on stress, the rest goes to its other regimes evenly.
    others = others.div(total.where(total > 0), axis=0).fillna(1 / others.shape[1])
    out = others.mul(1 - stress, axis=0)
    out["stress"] = stress
    return out[jump.columns]


def combination(settings: dict) -> str:
    """P(stress) shown and published: "max" (v1, v2) or "calibrated" (docs/CALIBRATION.md)."""
    return settings["models"].get("combined", {}).get("stress_combination", "max")


def calibrate(parts: dict[str, pd.DataFrame], event: pd.Series, settings: dict, start: pd.Timestamp) -> Calibrated:
    """Calibrated P(stress) from the components' out-of-sample probabilities (they start before `start`).

    `stack.inputs`: "max" = Platt scaling of the detector score (one weight); "sources" = one
    weight per source; "sources_max" = both.
    """
    sources = {name: part["stress"] for name, part in parts.items()}
    score = detector_score(*parts.values())
    inputs = settings["models"]["combined"]["stack"].get("inputs", "max")
    chosen = {"max": {"max": score}, "sources": sources, "sources_max": {**sources, "max": score}}[inputs]
    return calibrate_walk_forward(chosen, event, settings, start)


def combine_calibrated(parts: dict[str, pd.DataFrame], calibrated: Calibrated) -> pd.DataFrame:
    """Jump model regimes from the calibrated period on, with the calibrated P(stress)."""
    return combine(parts["jump"], stress=calibrated.stress)


@register
class CombinedModel(RegimeModel):
    name = "combined"

    @property
    def components(self) -> tuple[str, ...]:
        """Walk-forward runs each component on its own inputs and refit schedule, then combines."""
        sources = self.settings["models"].get("combined", {}).get("stress_sources", ["gbm"])
        return ("jump", *sources)

    @property
    def warmup(self) -> int | None:
        """First training-window end of the components: earlier than the backtest when calibrated."""
        if combination(self.settings) != "calibrated":
            return None
        return self.settings["models"]["combined"]["stack"]["warmup_days"]

    def fit(self, features, scores, labels):
        """Direct fit, for components trained on z-scores and rule labels (walk-forward handles the others)."""
        if combination(self.settings) == "calibrated":
            raise NotImplementedError("The calibrator learns from out-of-sample predictions: use walk_forward")
        self.models = {name: get_model(name, self.settings) for name in self.components}
        if any(getattr(m, "inputs", "scores") != "scores" for m in self.models.values()):
            raise NotImplementedError("Fit a combined model with market-input components through walk_forward")
        self.models = {name: m.fit(features, scores, labels) for name, m in self.models.items()}
        return self

    def predict_proba(self, features, scores):
        return combine(*(m.predict_proba(features, scores) for m in self.models.values()))
