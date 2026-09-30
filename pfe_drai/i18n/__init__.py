"""Translations. Every user-facing string lives in locales/{fr,en}.json."""

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
SUPPORTED = ("fr", "en")
DEFAULT = "fr"


@lru_cache
def _load(lang: str) -> dict[str, str]:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def t(key: str, lang: str = DEFAULT) -> str:
    """Return the string for `key` in `lang`, falling back to the default language, then the key."""
    if lang not in SUPPORTED:
        lang = DEFAULT
    return _load(lang).get(key) or _load(DEFAULT).get(key, key)
