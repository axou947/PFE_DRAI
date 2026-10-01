import json
import re
from pathlib import Path

from pfe_drai.i18n import LOCALES_DIR, fmt_pct, t

ROOT = Path(__file__).resolve().parents[1]


def _load(lang):
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def test_locales_have_same_keys():
    assert _load("fr").keys() == _load("en").keys()


def test_placeholders_match():
    fr, en = _load("fr"), _load("en")
    for key in fr:
        assert set(re.findall(r"{(\w+)}", fr[key])) == set(re.findall(r"{(\w+)}", en[key])), key


def test_translation_and_fallback():
    assert t("screen.dashboard", "en") == "Dashboard"
    assert t("screen.dashboard", "fr") == "Tableau de bord"
    assert t("screen.dashboard", "de") == "Tableau de bord"
    assert t("missing.key", "en") == "missing.key"
    assert t("alert.msg.stress_probability", "en", value="72%") == "Detector score at 72%"


def test_every_static_key_used_in_code_exists():
    keys = _load("fr").keys()
    pattern = re.compile(r"""\bt\(\s*["']([a-z_.]+)["']""")
    for path in list((ROOT / "pfe_drai").rglob("*.py")) + list((ROOT / "app").rglob("*.py")) + [ROOT / "api" / "main.py"]:
        for key in pattern.findall(path.read_text(encoding="utf-8")):
            assert key in keys, f"{key} used in {path.name}"


def test_number_formats():
    assert fmt_pct(0.725, "fr", 1) == "72,5 %"
    assert fmt_pct(0.725, "en", 1) == "72.5%"
