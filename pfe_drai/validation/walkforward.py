"""Expanding-window walk-forward: every prediction is made by a model fitted on the past only."""

import pandas as pd

from ..models import get_model


def walk_forward(
    model_name: str, features: pd.DataFrame, scores: pd.DataFrame, labels: pd.Series, settings: dict
) -> pd.DataFrame:
    components = getattr(get_model(model_name, settings), "components", None)
    if components:
        # Each component keeps its own refit schedule; the combination is applied afterwards.
        from ..models.combined import combine

        parts = [walk_forward(name, features, scores, labels, settings) for name in components]
        return combine(*parts)
    cfg = settings["validation"]
    start = cfg["min_train_days"]
    step = settings["models"].get(model_name, {}).get("refit_every_days", cfg["refit_every_days"])
    n = len(scores)
    if n <= start:
        raise ValueError(f"Need more than {start} days of data for walk-forward, got {n}")
    blocks = []
    for cut in range(start, n, step):
        model = get_model(model_name, settings)
        model.fit(features.iloc[:cut], scores.iloc[:cut], labels.iloc[:cut])
        end = min(cut + step, n)
        # Causal models (jump) need the full past to carry their state into the block.
        probs = model.predict_proba(features.iloc[:end], scores.iloc[:end]).iloc[cut:end]
        blocks.append(probs)
    return pd.concat(blocks)
