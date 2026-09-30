"""Regime definitions: names, colors, prototypes and the transparent labelling rule.

Regimes live on three dimensions (stress, growth, inflation):
- stress:      stress score above its threshold, whatever the other dimensions;
- overheating: inflation above its threshold (even with weak growth: stagflation);
- slowdown:    growth below its threshold;
- expansion:   everything else.
"""

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment


def regime_order(settings: dict) -> list[str]:
    return list(settings["regimes"]["order"])


def colors(settings: dict) -> dict[str, str]:
    return dict(settings["regimes"]["colors"])


def rule_labels(scores: pd.DataFrame, settings: dict) -> pd.Series:
    rule = settings["regimes"]["rule"]
    label = pd.Series("expansion", index=scores.index)
    label[scores["growth"] < rule["growth_threshold"]] = "slowdown"
    label[scores["inflation"] > rule["inflation_threshold"]] = "overheating"
    label[scores["stress"] > rule["stress_threshold"]] = "stress"
    return label.rename("rule")


def match_states(centroids: np.ndarray, settings: dict) -> list[str]:
    """Name unsupervised states by matching centroids to regime prototypes (one to one)."""
    names = regime_order(settings)
    protos = np.array([settings["regimes"]["prototypes"][n] for n in names])
    cost = ((centroids[:, None, :] - protos[None, :, :]) ** 2).sum(axis=2)
    rows, cols = linear_sum_assignment(cost)
    mapping = dict(zip(rows, cols, strict=True))
    return [names[mapping[i]] for i in range(len(centroids))]


def flip_distances(current: pd.Series, settings: dict) -> dict[str, float]:
    """How far each dimension is from the threshold that would change the rule label."""
    rule = settings["regimes"]["rule"]
    return {
        "stress": rule["stress_threshold"] - current["stress"],
        "growth": current["growth"] - rule["growth_threshold"],
        "inflation": rule["inflation_threshold"] - current["inflation"],
    }
