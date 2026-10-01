"""Common interface for regime models."""

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

_REGISTRY: dict[str, type["RegimeModel"]] = {}


class RegimeModel(ABC):
    """fit() on past data, then predict_proba() returns one column per regime (rows sum to 1)."""

    name: str = "base"
    #: True when the model predicts the regime `horizon` days ahead instead of today.
    forward_looking: bool = False
    #: "scores": fitted on feature z-scores and rule labels. "market": on fast market inputs and
    #: the episode target (models/onset.py). Walk-forward passes each model its own inputs.
    inputs: str = "scores"

    def __init__(self, settings: dict):
        self.settings = settings
        self.regimes: list[str] = list(settings["regimes"]["order"])

    @abstractmethod
    def fit(self, features: pd.DataFrame, scores: pd.DataFrame, labels: pd.Series) -> "RegimeModel": ...

    @abstractmethod
    def predict_proba(self, features: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame: ...

    def _frame(self, probs: np.ndarray, index: pd.Index, names: list[str]) -> pd.DataFrame:
        frame = pd.DataFrame(probs, index=index, columns=names)
        frame = frame.T.groupby(level=0).sum().T  # merge states that share a regime
        return frame.reindex(columns=self.regimes, fill_value=0.0)


def register(cls):
    _REGISTRY[cls.name] = cls
    return cls


def get_model(name: str, settings: dict) -> RegimeModel:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown model '{name}'. Available: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[name](settings)


def available_models() -> list[str]:
    return list(_REGISTRY)


def softmax(x: np.ndarray, axis: int = 1) -> np.ndarray:
    x = x - x.max(axis=axis, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)
