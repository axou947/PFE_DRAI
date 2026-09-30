"""Settings loader. All tunable values live in config/settings.yaml."""

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "settings.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache
def _read(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_settings(path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    """Load settings from YAML, then apply optional overrides (nested dict)."""
    path = Path(path or os.environ.get("PFE_DRAI_CONFIG", DEFAULT_PATH))
    settings = copy.deepcopy(_read(str(path)))
    if overrides:
        settings = _deep_merge(settings, overrides)
    return settings


def resolve(path: str | Path) -> Path:
    """Resolve a path from the settings relative to the repository root."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path
