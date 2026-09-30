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


def t(key: str, lang: str = DEFAULT, **params) -> str:
    """Return the string for `key` in `lang`, falling back to the default language, then the key.

    Named placeholders are filled from `params`: t("alert.msg.stress_probability", "en", value="72%").
    """
    if lang not in SUPPORTED:
        lang = DEFAULT
    text = _load(lang).get(key) or _load(DEFAULT).get(key, key)
    return text.format(**params) if params else text


def fmt_pct(value: float, lang: str = DEFAULT, digits: int = 0) -> str:
    text = f"{value * 100:.{digits}f}"
    return f"{text.replace('.', ',')} %" if lang == "fr" else f"{text}%"


def fmt_num(value: float, lang: str = DEFAULT, digits: int = 2) -> str:
    text = f"{value:+.{digits}f}"
    return text.replace(".", ",") if lang == "fr" else text


def fmt_date(value, lang: str = DEFAULT) -> str:
    import pandas as pd

    d = pd.Timestamp(value)
    return d.strftime("%d/%m/%Y") if lang == "fr" else d.strftime("%Y-%m-%d")
