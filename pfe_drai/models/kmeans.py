"""Baseline: k-means on the three dimension scores."""

import numpy as np
from sklearn.cluster import KMeans

from ..regimes import name_states
from .base import RegimeModel, register, softmax


@register
class KMeansModel(RegimeModel):
    name = "kmeans"

    def fit(self, features, scores, labels):
        cfg = self.settings["models"]["kmeans"]
        self.km = KMeans(n_clusters=len(self.regimes), n_init=cfg["n_init"], random_state=0)
        self.km.fit(scores.values)
        self.state_table = name_states(self.km.labels_, self.km.cluster_centers_, scores, labels, self.settings)
        self.state_names = list(self.state_table["name"])
        return self

    def predict_proba(self, features, scores):
        dist = self.km.transform(scores.values) ** 2
        probs = softmax(-dist / np.maximum(dist.mean(), 1e-9) * 4)
        return self._frame(probs, scores.index, self.state_names)
