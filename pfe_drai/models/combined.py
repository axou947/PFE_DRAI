"""Combined signal: the jump model's regimes, with the stress probability raised by gradient boosting.

P(stress) = max(jump, gbm). The jump model is persistent and slow to switch; gradient boosting
reacts within days but flickers between regimes. Taking the higher stress probability keeps the
jump model's calm regimes and catches a crisis as soon as either model sees it. The other
regimes keep the jump model's proportions and share what is left, so rows still sum to 1.
Because gbm looks one week ahead, the combined P(stress) reads "stress now or within a week".
"""

import numpy as np
import pandas as pd

from .base import RegimeModel, get_model, register


def combine(jump: pd.DataFrame, gbm: pd.DataFrame) -> pd.DataFrame:
    idx = jump.index.intersection(gbm.index)
    jump, gbm = jump.loc[idx], gbm.loc[idx]
    stress = np.maximum(jump["stress"], gbm["stress"])
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
    #: Walk-forward runs each component on its own refit schedule, then combines.
    components = ("jump", "gbm")

    def fit(self, features, scores, labels):
        self.models = {name: get_model(name, self.settings).fit(features, scores, labels) for name in self.components}
        return self

    def predict_proba(self, features, scores):
        probs = {name: m.predict_proba(features, scores) for name, m in self.models.items()}
        return combine(probs["jump"], probs["gbm"])
