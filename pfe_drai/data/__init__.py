"""Data sources. Pick one with data.provider in config/settings.yaml.

Adding a real API = one class that subclasses DataProvider, decorated with @register,
and returns the series listed in catalog.py. Nothing else in the code changes.
"""

from . import csv_provider, euro, fred, synthetic, tiingo, yahoo  # noqa: F401  (registers providers)
from .base import DataProvider, available_providers, get_provider, register
from .catalog import CATALOG

__all__ = ["CATALOG", "DataProvider", "available_providers", "get_provider", "register"]
