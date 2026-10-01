"""Expanding-window walk-forward: every prediction is made by a model fitted on the past only."""

import pandas as pd

from ..models import get_model


def refit_cuts(n: int, settings: dict, model_name: str) -> range:
    """Training-window ends of the walk-forward: the model fitted on [:cut] predicts from cut on."""
    cfg = settings["validation"]
    step = settings["models"].get(model_name, {}).get("refit_every_days", cfg["refit_every_days"])
    return range(cfg["min_train_days"], n, step)


def walk_forward(
    model_name: str,
    features: pd.DataFrame,
    scores: pd.DataFrame,
    labels: pd.Series,
    settings: dict,
    market: pd.DataFrame | None = None,
    onset: pd.Series | None = None,
) -> pd.DataFrame:
    """`market` and `onset` (inputs and target of market-input models) are needed only by those models."""
    model = get_model(model_name, settings)
    components = getattr(model, "components", None)
    if components:
        # Each component keeps its own inputs and refit schedule; the combination is applied afterwards.
        from ..models.combined import combine

        parts = [walk_forward(name, features, scores, labels, settings, market, onset) for name in components]
        return combine(*parts)
    if model.inputs == "market":
        if market is None or onset is None:
            raise ValueError(f"Model '{model_name}' needs market inputs and the onset target")
        features, labels = market.loc[scores.index], onset.loc[scores.index]
    n = len(scores)
    cuts = refit_cuts(n, settings, model_name)
    if not cuts:
        raise ValueError(f"Need more than {cuts.start} days of data for walk-forward, got {n}")
    blocks = []
    for cut in cuts:
        model = get_model(model_name, settings)
        model.fit(features.iloc[:cut], scores.iloc[:cut], labels.iloc[:cut])
        end = min(cut + cuts.step, n)
        # Causal models (jump) need the full past to carry their state into the block.
        probs = model.predict_proba(features.iloc[:end], scores.iloc[:end]).iloc[cut:end]
        blocks.append(probs)
    return pd.concat(blocks)
