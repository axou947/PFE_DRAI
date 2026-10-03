"""Learn pages (docs/LEARN.md): content completeness, the Fed lenses and a headless run of both tabs."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from pfe_drai.config import load_settings
from pfe_drai.learn import cards as learn_cards
from pfe_drai.learn import data as learn_data
from pfe_drai.learn import fed, today
from pfe_drai.publish.snapshot import config_fingerprint

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "streamlit_app.py"


@pytest.fixture(scope="module")
def learn_settings():
    return load_settings()


@pytest.fixture(scope="module")
def economy(learn_settings):
    data, live, errors = learn_data.fetch(learn_settings, "synthetic")
    assert not live and not errors
    indicators = learn_data.load_indicators(learn_settings)
    return data, indicators, learn_data.compute_all(indicators, data)


def _locale(lang):
    return json.loads((ROOT / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- content
def test_every_card_is_complete_at_both_levels_and_in_both_languages(learn_settings):
    cards = learn_cards.load_cards(learn_settings)
    ids = {c.id for c in cards}
    indicators = learn_data.load_indicators(learn_settings)
    assert sorted(ids) == sorted(learn_cards.ORDER)
    for card in cards:
        assert card.theme in learn_cards.THEMES, card.id
        for lang in learn_cards.LANGS:
            assert card.title[lang] and card.facts[lang], card.id
            # A French " : " left unquoted turns a key point into a YAML mapping (it broke search).
            assert all(isinstance(f, str) for f in card.facts[lang]), (card.id, lang)
            for level in learn_cards.LEVELS:
                text = card.text(level, lang)
                for section in learn_cards.SECTIONS:
                    assert str(text.get(section, "")).strip(), (card.id, level, lang, section)
                if level == "pro":
                    for extra in learn_cards.PRO_EXTRAS:
                        assert str(text.get(extra, "")).strip(), (card.id, lang, extra)
                for item in card.quiz.get(level, []):
                    q = item[lang]
                    assert len(q["options"]) == 3 and all(isinstance(o, str) for o in q["options"]), (card.id, level, lang)
                    assert 0 <= q["answer"] < 3 and q["why"], (card.id, level, lang)
        for edge in card.leads_to:
            assert edge["card"] in ids and edge["en"] and edge["fr"], (card.id, edge)
        for name in (*card.indicators, *card.chart):
            assert name in indicators, (card.id, name)
    for level in learn_cards.LEVELS:
        assert learn_cards.quiz(cards, level, "en") and len(learn_cards.quiz(cards, level, "en")) == len(
            learn_cards.quiz(cards, level, "fr")
        )
    assert set(learn_cards.REGIME_CARD.values()) <= ids


def test_glossary_and_history_lessons_are_complete(learn_settings):
    ids = set(learn_cards.cards_by_id(learn_settings))
    for term in learn_cards.load_glossary(learn_settings):
        for part in ("term", "beginner", "pro"):
            assert term[part]["en"] and term[part]["fr"], term
        assert term.get("card") is None or term["card"] in ids
    for ep in learn_cards.load_episodes(learn_settings):
        assert pd.Timestamp(ep["start"]) < pd.Timestamp(ep["end"])
        assert set(ep["cards"]) <= ids
        for level in learn_cards.LEVELS:
            for lang in learn_cards.LANGS:
                assert all(ep[level][lang][k] for k in ("happened", "fed", "lesson")), (ep["id"], level, lang)


def test_search_finds_a_card_by_a_word_of_its_text(learn_settings):
    cards = learn_cards.load_cards(learn_settings)
    assert "inflation" in {c.id for c in learn_cards.search(cards, "inflation", "beginner", "en")}
    for level in learn_cards.LEVELS:
        for lang in learn_cards.LANGS:
            assert "fed_policy" in {c.id for c in learn_cards.search(cards, "Fed", level, lang)}
    assert learn_cards.search(cards, "", "pro", "fr") == cards


def test_every_learn_text_key_exists_in_both_languages(learn_settings):
    en, fr = _locale("en"), _locale("fr")
    keys = {k for k in en if k.startswith(("learn.", "tab.learn"))}
    assert keys == {k for k in fr if k.startswith(("learn.", "tab.learn"))}
    dynamic = [f"learn.ind.{name}" for name in learn_data.load_indicators(learn_settings)]
    dynamic += [f"learn.section.{s}" for s in ("today", "concepts", "map", "history", "lab", "glossary", "quiz", "ask")]
    dynamic += [f"learn.theme.{x}" for x in learn_cards.THEMES]
    dynamic += [f"learn.fed.{o}" for o in fed.OUTCOMES] + [f"learn.fed.headline.{o}" for o in fed.OUTCOMES]
    dynamic += [f"learn.fed.taylor_says.{o}" for o in fed.OUTCOMES]
    dynamic += [f"learn.fed.rule.{r}" for r in ("taylor_1993", "balanced", "inertial")]
    dynamic += [f"learn.trend.{x}" for x in ("rising", "falling", "stable")]
    dynamic += [f"learn.check.{x}" for x in ("sahm", "curve", "claims", "payrolls", "gdp", "alarm")]
    for level in learn_cards.LEVELS:
        dynamic += [f"learn.intro.{level}", f"learn.map.help.{level}", f"learn.quiz.help.{level}"]
        dynamic += [f"learn.lab.taylor_help.{level}", f"learn.lab.fisher_help.{level}"]
        dynamic += [f"learn.ask.help.{level}", f"learn.ask.example.{level}"]
        dynamic += [f"learn.ask.sample{i}.{level}" for i in (1, 2, 3)]
        dynamic += [f"learn.check.{x}.{level}" for x in ("sahm", "curve", "claims", "payrolls", "gdp", "alarm")]
    missing = [k for k in dynamic if k not in en]
    assert not missing, missing


def test_learn_settings_do_not_change_the_model_fingerprint(learn_settings):
    without = {k: v for k, v in learn_settings.items() if k != "learn"}
    without["learn"] = {"anything": 1}
    assert config_fingerprint(without) == config_fingerprint(learn_settings)


# ---------------------------------------------------------------- data and lenses
def test_simulated_indicators_compute_and_read(economy, learn_settings):
    data, indicators, values = economy
    empty = [name for name, s in values.items() if s is None or s.dropna().empty]
    assert not empty, empty
    date = values["unrate"].index[-1]
    r = today.reading(values["unrate"], indicators["unrate"], date)
    assert 0 <= r["percentile"] <= 1 and r["trend"] in ("rising", "falling", "stable")
    lights = today.checklist(values, date, learn_settings, alarm_on=False)
    assert {x["id"] for x in lights} == {"sahm", "curve", "claims", "payrolls", "gdp", "alarm"}
    assert all(x["status"] in ("green", "amber", "red", None) for x in lights)


def test_fed_odds_are_probabilities_and_meetings_extend_both_ways(economy, learn_settings):
    data, _, values = economy
    for date in ("2007-06-29", "2015-11-30", "2024-03-29"):
        out = fed.outlook(data, values, date, learn_settings)
        assert out["next_meeting"]["days"] > 0
        assert out["bills"]["horizons"]
        for h in out["bills"]["horizons"]:
            p = h["probabilities"]
            assert abs(sum(p.values()) - 1) < 1e-9 and all(0 <= v <= 1 for v in p.values())
        hp = out["history"]["probabilities"]
        assert hp and abs(sum(hp.values()) - 1) < 1e-9
    # A date before the FOMC calendar still has meetings (counted back at the usual spacing).
    assert fed.meetings_ahead(learn_settings, "2008-01-15", 120)
    assert fed._probabilities(0.4) == pytest.approx({"cut": 0.0, "hold": 0.6, "hike": 0.4})
    assert fed._probabilities(-1.6) == pytest.approx({"cut": 1.0, "hold": 0.0, "hike": 0.0})


def test_bill_implied_reads_a_priced_hike():
    # Flat funds rate at 4%, no basis; the 3-month bill prices the average rate over its life.
    settings = load_settings()
    settings["learn"]["fed"]["basis_min_days"] = 10**6  # use the default basis, set to zero below
    settings["learn"]["fed"]["default_basis_pct"] = {"DGS3MO": 0.0, "DGS6MO": 0.0}
    date = pd.Timestamp("2026-04-30")
    days = pd.bdate_range("2025-01-01", date)
    meetings = fed.meetings_ahead(settings, date, 91)
    weights = sum(1 - (m - date).days / 91 for m in meetings)
    bill = 4.0 + 0.25 * weights  # one 25 bp hike at every meeting in the window
    data = {"DFF": pd.Series(4.0, days), "DGS3MO": pd.Series(bill, days), "DFEDTARU": pd.Series(4.0, days)}
    h = fed.bill_implied(data, date, settings)["horizons"][0]
    assert h["change_pct"] == pytest.approx(0.25 * len(meetings))
    assert h["probabilities"]["hike"] == pytest.approx(1.0)


def test_taylor_rule_known_value(learn_settings):
    inputs = {"inflation": 3.0, "unemployment": 4.0, "natural_unemployment": 4.5, "policy_rate": 4.0}
    rules = fed.taylor_rules(inputs, learn_settings, r_star=1.0)
    # gap = 2 x (4.5 - 4.0) = 1; Taylor 1993 = 1 + 3 + 0.5 x (3 - 2) + 0.5 x 1; balanced = 1 + 3 + 0.5 + 1 x 1.
    assert rules["taylor_1993"] == pytest.approx(5.0)
    assert rules["balanced"] == pytest.approx(5.5)
    assert rules["inertial"] == pytest.approx(0.85 * 4.0 + 0.15 * 5.5)


def test_base_rates_never_use_an_outcome_after_the_day(economy, learn_settings):
    data, _, values = economy
    end = pd.Timestamp("2015-11-30")
    frame = fed.monthly_conditions(data, values, learn_settings, end)
    horizon = learn_settings["learn"]["fed"]["base_rates"]["horizon_months"]
    recent = frame.index[frame.index + pd.DateOffset(months=horizon) > end]
    assert len(recent) and frame.loc[recent, "outcome"].isna().all()
    assert frame["outcome"].dropna().isin(fed.OUTCOMES).all()
    assert not np.isnan(frame["change"].dropna()).any()


# ---------------------------------------------------------------- the two tabs, headless
def test_both_learn_tabs_render_every_section_and_the_ai_tutor_is_coming_soon():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception
    for level in learn_cards.LEVELS:
        for section in ("today", "concepts", "map", "history", "lab", "glossary", "quiz", "ask"):
            at.session_state[f"learn_{level}_section"] = section
            at.run()
            assert not at.exception, (level, section)
            assert not at.error, (level, section, [e.value for e in at.error])
    at.session_state["learn_beginner_section"] = "ask"
    at.run()
    assert not any("GAMA is coming soon" in i.value for i in at.info)
    next(b for b in at.button if b.key == "learn_beginner_ask_send").click().run()
    assert any("GAMA is coming soon" in i.value for i in at.info)
