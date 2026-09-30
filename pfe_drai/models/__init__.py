"""Regime models: k-means baseline, Statistical Jump Model, gradient boosting.

Add a model = one RegimeModel subclass decorated with @register.
"""

from . import gbm, jump, kmeans  # noqa: F401  (registers models)
from .base import RegimeModel, available_models, get_model

__all__ = ["RegimeModel", "available_models", "get_model"]
