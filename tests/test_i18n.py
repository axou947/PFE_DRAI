import json

from pfe_drai.i18n import LOCALES_DIR, t


def test_locales_have_same_keys():
    fr = json.loads((LOCALES_DIR / "fr.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    assert fr.keys() == en.keys()


def test_translation_and_fallback():
    assert t("screen.dashboard", "en") == "Dashboard"
    assert t("screen.dashboard", "fr") == "Tableau de bord"
    assert t("screen.dashboard", "de") == "Tableau de bord"
    assert t("missing.key", "en") == "missing.key"
