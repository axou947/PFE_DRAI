"""Common interface for every data source."""

from abc import ABC, abstractmethod

import pandas as pd

from .catalog import CATALOG

_REGISTRY: dict[str, type["DataProvider"]] = {}


class DataProvider(ABC):
    """Returns one DataFrame indexed by date, one column per catalog series.

    Monthly and weekly series are returned at their own dates; the pipeline
    aligns them on business days and applies publication lags.
    """

    name: str = "base"
    #: True when values come from a real source (shown in the app and reports).
    is_live: bool = True

    def __init__(self, settings: dict):
        self.settings = settings
        #: Series already indexed by their release date (point-in-time): no publication lag.
        self.release_dated: set[str] = set()

    @abstractmethod
    def fetch(self, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.Series]:
        """Return {series name: pd.Series indexed by date}."""

    def truth(self) -> pd.Series | None:
        """True regime per day, known only for simulated data."""
        return None

    def check(self, data: dict[str, pd.Series]) -> None:
        missing = [name for name in CATALOG if name not in data]
        if missing:
            raise ValueError(f"Provider '{self.name}' is missing series: {', '.join(missing)}")


def register(cls: type[DataProvider]) -> type[DataProvider]:
    """Class decorator: makes a provider selectable with data.provider in the settings."""
    _REGISTRY[cls.name] = cls
    return cls


def get_provider(settings: dict) -> DataProvider:
    name = settings["data"]["provider"]
    if name not in _REGISTRY:
        raise ValueError(f"Unknown data provider '{name}'. Available: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[name](settings)


def available_providers() -> list[str]:
    return sorted(_REGISTRY)
