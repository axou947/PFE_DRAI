"""Stress-onset detector: P(a stress episode is under way now or within a week), from fast market inputs.

The other models learn the transparent rule label (stress score above 1), which is a different
event from the episodes the track record is scored on: a 10% fall or a volatility spike can
happen while the slow stress score stays below 1, and then no model trained on that label can
see it. This one learns the episodes themselves (frozen rule, validation/episodes.py), from
daily market inputs in their own units (features/market.py). Pre-registered in docs/DETECTION_V2.md.

It gives no view on the calm regimes: they share 1 - P(stress) evenly. It is meant to be one of
the stress sources of the `combined` model, not a regime model on its own.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..features.market import INPUT_SETS
from .base import RegimeModel, register


@register
class OnsetModel(RegimeModel):
    name = "onset"
    forward_looking = True
    #: Trained on market inputs and the episode target instead of z-scores and rule labels.
    inputs = "market"

    @property
    def cfg(self) -> dict:
        return self.settings["models"]["onset"]

    def _x(self, market: pd.DataFrame) -> pd.DataFrame:
        return market[INPUT_SETS[self.cfg["inputs"]]]

    def fit(self, features, scores, labels):
        """`features` = market inputs, `labels` = onset target (validation.onset_target).

        The target of the last `horizon_days` days of the window depends on days after it:
        they are dropped (purging), as gbm does.
        """
        x = self._x(features)
        known = labels.iloc[: len(labels) - self.cfg["horizon_days"]].dropna()
        x, y = x.loc[known.index], known.astype(int)
        self.single_class = None if y.nunique() > 1 else int(y.iloc[0])
        if self.single_class is not None:  # no episode in the training window yet
            return self
        if self.cfg["learner"] == "logistic":
            # Missing inputs (credit before 2002, warm-up days) read as "no information".
            self.fill = x.median()
            self.clf = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
            self.clf.fit(x.fillna(self.fill).fillna(0.0), y)
        else:
            self.clf = HistGradientBoostingClassifier(
                max_iter=self.cfg["max_iter"], learning_rate=self.cfg["learning_rate"], random_state=0
            )
            self.clf.fit(x, y)
        return self

    def p_stress(self, market: pd.DataFrame) -> pd.Series:
        x = self._x(market)
        if self.single_class is not None:
            return pd.Series(float(self.single_class), index=x.index)
        if self.cfg["learner"] == "logistic":
            x = x.fillna(self.fill).fillna(0.0)
        return pd.Series(self.clf.predict_proba(x)[:, 1], index=x.index)

    def predict_proba(self, features, scores):
        p = self.p_stress(features)
        # Minimum time on: a probability holds for `hold_days` days, so the signal does not
        # flicker on and off around 0.5 during a fall (each flicker would be a regime switch).
        hold = self.cfg.get("hold_days", 1)
        p = p.rolling(hold, min_periods=1).max().to_numpy()
        calm = [r for r in self.regimes if r != "stress"]
        probs = np.column_stack([np.repeat(((1 - p) / len(calm))[:, None], len(calm), axis=1), p])
        return self._frame(probs, features.index, calm + ["stress"])
