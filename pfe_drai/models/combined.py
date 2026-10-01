"""Combined signal: the jump model's regimes, with the stress probability raised by faster models.

P(stress) = max(jump, each stress source). The jump model is persistent and slow to switch;
the stress sources react within days but flicker. Taking the highest stress probability keeps
the jump model's calm regimes and catches a crisis as soon as any model sees it. The other
regimes keep the jump model's proportions and share what is left, so rows still sum to 1.

Stress sources are set in models.combined.stress_sources: [gbm] since PR #5 (docs/DETECTION.md);
[gbm, onset] is the pre-registered v2 (docs/DETECTION_V2.md). Both sources look one week
ahead, so the combined P(stress) reads "stress now or within a week".
"""

import numpy as np
import pandas as pd

from .base import RegimeModel, get_model, register


def combine(jump: pd.DataFrame, *sources: pd.DataFrame) -> pd.DataFrame:
    idx = jump.index
    for source in sources:
        idx = idx.intersection(source.index)
    jump = jump.loc[idx]
    stress = jump["stress"]
    for source in sources:
        stress = np.maximum(stress, source.loc[idx, "stress"])
    others = jump.drop(columns="stress")
    total = others.sum(axis=1)
    # When the jump model puts everything on stress, the rest goes to its other regimes evenly.
    others = others.div(total.where(total > 0), axis=0).fillna(1 / others.shape[1])
    out = others.mul(1 - stress, axis=0)
    out["stress"] = stress
    return out[jump.columns]


@register
class CombinedModel(RegimeModel):
    name = "combined"

    @property
    def components(self) -> tuple[str, ...]:
        """Walk-forward runs each component on its own inputs and refit schedule, then combines."""
        sources = self.settings["models"].get("combined", {}).get("stress_sources", ["gbm"])
        return ("jump", *sources)

    def fit(self, features, scores, labels):
        """Direct fit, for components trained on z-scores and rule labels (walk-forward handles the others)."""
        self.models = {name: get_model(name, self.settings) for name in self.components}
        if any(getattr(m, "inputs", "scores") != "scores" for m in self.models.values()):
            raise NotImplementedError("Fit a combined model with market-input components through walk_forward")
        self.models = {name: m.fit(features, scores, labels) for name, m in self.models.items()}
        return self

    def predict_proba(self, features, scores):
        return combine(*(m.predict_proba(features, scores) for m in self.models.values()))
