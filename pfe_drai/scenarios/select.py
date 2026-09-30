"""Pick the historical scenarios closest to today's regime, and measure their impact on a fund.

Similarity = distance between today's (stress, growth, inflation) scores and each
scenario profile, with a bonus for scenarios tagged with a likely regime.
"""

import numpy as np
import pandas as pd

from .library import Fund, Scenario


def rank_scenarios(scenarios: list[Scenario], current_scores: pd.Series, regime_probs: pd.Series) -> pd.DataFrame:
    x = current_scores[["stress", "growth", "inflation"]].values.astype(float)
    rows = []
    for sc in scenarios:
        distance = float(np.linalg.norm(x - np.array(sc.profile)))
        prob = float(regime_probs.get(sc.regime, 0.0))
        score = np.exp(-distance / 1.5) * (0.5 + prob)
        rows.append({"id": sc.id, "regime": sc.regime, "distance": distance, "regime_probability": prob, "relevance": score})
    frame = pd.DataFrame(rows).sort_values("relevance", ascending=False)
    frame["relevance"] = frame["relevance"] / frame["relevance"].max()
    return frame.reset_index(drop=True)


def fund_impact(fund_weights: dict[str, float], scenario: Scenario) -> dict:
    contributions = {a: w * scenario.shocks.get(a, 0.0) for a, w in fund_weights.items()}
    return {"total": float(sum(contributions.values())), "by_asset": contributions}


def impact_table(fund: Fund | dict, scenarios: list[Scenario], ids: list[str]) -> pd.DataFrame:
    weights = fund.weights if isinstance(fund, Fund) else fund
    by_id = {s.id: s for s in scenarios}
    rows = []
    for sid in ids:
        impact = fund_impact(weights, by_id[sid])
        rows.append({"id": sid, "total": impact["total"], **impact["by_asset"]})
    return pd.DataFrame(rows)
