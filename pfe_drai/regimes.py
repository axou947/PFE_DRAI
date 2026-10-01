"""Regime definitions: names, colors, the transparent labelling rule and how model states get a name.

Regimes live on three dimensions (stress, growth, inflation):
- stress:      stress score above its threshold, whatever the other dimensions;
- overheating: inflation above its threshold (even with weak growth: stagflation);
- slowdown:    growth below its threshold;
- expansion:   everything else.

Unsupervised models (k-means, jump model) find states that have no name. `name_states` gives
each state the name of the regime whose centre is closest to the state's centre, where a regime's
centre is the average position, on the three dimensions, of the training days the rule puts in
that regime (docs/REGIMES.md). Nothing is set by hand: the names follow from the rule and the
data. Two states can share a name, and a regime with no training day cannot name any state.
"""

import numpy as np
import pandas as pd

from .features import DIMENSIONS


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


def regime_centres(scores: pd.DataFrame, labels: pd.Series, settings: dict) -> pd.DataFrame:
    """Average position of the days the rule puts in each regime, and their number.

    Regimes without any day in `labels` are left out.
    """
    labels = pd.Series(np.asarray(labels), index=scores.index)
    centres = scores[DIMENSIONS].groupby(labels).mean()
    centres["days"] = labels.value_counts()
    return centres.reindex([r for r in regime_order(settings) if r in centres.index])


def name_states(
    states: np.ndarray, centroids: np.ndarray, scores: pd.DataFrame, labels: pd.Series, settings: dict
) -> pd.DataFrame:
    """Name each state after the closest regime centre, and keep the evidence.

    `states` holds the state of each training day; `scores` and `labels` are the dimension scores
    and rule labels of the same days. Returns one row per state: its name, its distance to that
    regime's centre, its number of training days, the share of those days the rule puts in each
    regime (the share of its own name is its purity) and its centre on the three dimensions.
    """
    order = regime_order(settings)
    centres = regime_centres(scores, labels, settings)
    distance = ((centroids[:, None, :] - centres[DIMENSIONS].to_numpy()[None, :, :]) ** 2).sum(axis=2)
    labels = np.asarray(labels)
    rows = []
    for j, centroid in enumerate(centroids):
        days = labels[states == j]
        share = pd.Series(days, dtype=object).value_counts(normalize=True).reindex(order, fill_value=0.0)
        nearest = int(distance[j].argmin())
        name = str(centres.index[nearest])
        rows.append(
            {
                "state": j,
                "name": name,
                "distance": float(np.sqrt(distance[j, nearest])),
                "days": int(len(days)),
                "purity": float(share[name]),
                **{f"share_{r}": float(share[r]) for r in order},
                **{dim: float(v) for dim, v in zip(DIMENSIONS, centroid, strict=True)},
            }
        )
    return pd.DataFrame(rows).set_index("state")


def flip_distances(current: pd.Series, settings: dict) -> dict[str, float]:
    """How far each dimension is from the threshold that would change the rule label."""
    rule = settings["regimes"]["rule"]
    return {
        "stress": rule["stress_threshold"] - current["stress"],
        "growth": current["growth"] - rule["growth_threshold"],
        "inflation": rule["inflation_threshold"] - current["inflation"],
    }
