"""Historical stress scenarios and model funds, loaded from YAML (config/)."""

from dataclasses import dataclass

import yaml

from ..config import resolve


@dataclass
class Scenario:
    id: str
    name: dict[str, str]
    start: str
    end: str
    regime: str
    profile: list[float]
    shocks: dict[str, float]


@dataclass
class Fund:
    id: str
    name: dict[str, str]
    weights: dict[str, float]


def load_library(settings: dict) -> tuple[list[str], list[Scenario]]:
    raw = yaml.safe_load(resolve(settings["scenarios"]["library"]).read_text(encoding="utf-8"))
    return raw["asset_classes"], [Scenario(**s) for s in raw["scenarios"]]


def load_funds(settings: dict) -> list[Fund]:
    raw = yaml.safe_load(resolve(settings["scenarios"]["funds"]).read_text(encoding="utf-8"))
    return [Fund(**f) for f in raw["funds"]]
