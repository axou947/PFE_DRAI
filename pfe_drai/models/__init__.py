"""Regime models: k-means baseline, Statistical Jump Model, gradient boosting, stress-onset detector, combined.

Add a model = one RegimeModel subclass decorated with @register.
"""

from . import combined, gbm, jump, kmeans, onset  # noqa: F401  (registers models)
from .base import RegimeModel, available_models, get_model

__all__ = ["RegimeModel", "available_models", "get_model"]
