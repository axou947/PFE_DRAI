"""Statistical Jump Model (Nystrup, Lindström & Madsen, 2020).

Clustering with a fixed penalty for every regime switch, which gives persistent regimes.
Fitting alternates between the best state sequence (dynamic programming) and centroids.
Prediction is causal: a forward pass only, so the state on day t uses data up to t.
"""

import numpy as np
from sklearn.cluster import KMeans

from ..regimes import match_states
from .base import RegimeModel, register, softmax


def _viterbi(loss: np.ndarray, penalty: float) -> np.ndarray:
    n, k = loss.shape
    value = loss[0].copy()
    back = np.zeros((n, k), dtype=int)
    switch = penalty * (1 - np.eye(k))
    for t in range(1, n):
        total = value[:, None] + switch  # from state i to state j
        back[t] = total.argmin(axis=0)
        value = total.min(axis=0) + loss[t]
    states = np.empty(n, dtype=int)
    states[-1] = value.argmin()
    for t in range(n - 1, 0, -1):
        states[t - 1] = back[t, states[t]]
    return states


def forward_values(loss: np.ndarray, penalty: float) -> np.ndarray:
    """Causal cost of ending in each state on each day."""
    n, k = loss.shape
    out = np.empty((n, k))
    value = loss[0].copy()
    out[0] = value
    for t in range(1, n):
        value = np.minimum(value, value.min() + penalty) + loss[t]
        value -= value.min()  # keep numbers small, differences are what matter
        out[t] = value
    return out


@register
class JumpModel(RegimeModel):
    name = "jump"

    def _loss(self, x: np.ndarray) -> np.ndarray:
        return ((x[:, None, :] - self.centroids[None, :, :]) ** 2).sum(axis=2)

    def fit(self, features, scores, labels):
        cfg = self.settings["models"]["jump"]
        x = scores.values
        k = len(self.regimes)
        self.centroids = KMeans(n_clusters=k, n_init=5, random_state=0).fit(x).cluster_centers_
        for _ in range(cfg["n_iter"]):
            states = _viterbi(self._loss(x), cfg["penalty"])
            new = np.array([x[states == j].mean(axis=0) if (states == j).any() else self.centroids[j] for j in range(k)])
            if np.allclose(new, self.centroids):
                break
            self.centroids = new
        self.state_names = match_states(self.centroids, self.settings)
        return self

    def predict_proba(self, features, scores):
        cfg = self.settings["models"]["jump"]
        values = forward_values(self._loss(scores.values), cfg["penalty"])
        probs = softmax(-values / cfg["temperature"])
        return self._frame(probs, scores.index, self.state_names)
