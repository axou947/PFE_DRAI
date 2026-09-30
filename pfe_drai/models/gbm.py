"""Supervised model: gradient boosting that predicts the regime one week ahead.

Target = the transparent rule label `horizon_days` later. The last `horizon_days`
rows of each training window have no known target yet and are dropped (purging).
"""

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from .base import RegimeModel, register


@register
class GBMModel(RegimeModel):
    name = "gbm"
    forward_looking = True

    def _inputs(self, features: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
        x = features.join(scores)
        x = x.join(scores.diff(5).add_suffix("_chg5"))
        return x.fillna(0.0)

    def fit(self, features, scores, labels):
        cfg = self.settings["models"]["gbm"]
        h = cfg["horizon_days"]
        target = labels.shift(-h).iloc[:-h]
        x = self._inputs(features, scores).loc[target.index]
        self.clf = HistGradientBoostingClassifier(max_iter=cfg["max_iter"], learning_rate=cfg["learning_rate"], random_state=0)
        self.clf.fit(x, target)
        return self

    def predict_proba(self, features, scores):
        x = self._inputs(features, scores)
        probs = self.clf.predict_proba(x)
        return self._frame(probs, x.index, list(self.clf.classes_))
