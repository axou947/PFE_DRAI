"""Settings loader. All tunable values live in config/settings.yaml."""

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "config" / "settings.yaml"
REGIONS_DIR = ROOT / "config" / "regions"
DEFAULT_REGION = "us"


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


def available_regions() -> list[str]:
    return [DEFAULT_REGION] + sorted(p.stem for p in REGIONS_DIR.glob("*.yaml"))


def load_settings(path: str | Path | None = None, overrides: dict | None = None, region: str | None = None) -> dict[str, Any]:
    """Load settings from YAML, then a region overlay, then optional overrides (nested dict).

    The default region (us) is the base file untouched: no overlay, no `region` key, so the US
    model, its settings fingerprint and its published files stay exactly as they were. Another
    region is config/regions/<region>.yaml deep-merged over the base (docs/EURO.md).
    """
    path = Path(path or os.environ.get("PFE_DRAI_CONFIG", DEFAULT_PATH))
    settings = copy.deepcopy(_read(str(path)))
    if region and region != DEFAULT_REGION:
        overlay = REGIONS_DIR / f"{region}.yaml"
        if not overlay.exists():
            raise ValueError(f"Unknown region '{region}'. Available: {', '.join(available_regions())}")
        settings = _deep_merge(settings, _read(str(overlay)))
        settings["region"] = region
    if overrides:
        settings = _deep_merge(settings, overrides)
    return settings


def resolve(path: str | Path) -> Path:
    """Resolve a path from the settings relative to the repository root."""
    path = Path(path)
    return path if path.is_absolute() else ROOT / path
