"""Displayed Slowdown v2.3 (docs/SLOWDOWN_V23.md): the calm displays, the pre-registered selection and
decision, and that nothing published changes until the decision passes."""

import numpy as np
import pandas as pd
import pytest

from pfe_drai.cli import main
from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.display import calm_display, confirmed, rule_calm
from pfe_drai.publish.snapshot import config_fingerprint
from pfe_drai.validation import Episode
from pfe_drai.validation.display_v23 import below_potential, decide_v23, display_scores, run_v23, select

US_CONFIG_SHA256 = "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"


def _calm(settings, mode):
    return _deep_merge(settings, {"models": {"combined": {"calm": mode}}})


def test_default_settings_keep_v22_and_its_fingerprint(pipeline):
    s = load_settings()
    assert "calm" not in s["models"]["combined"]  # v2.2: the jump model's split
    assert s["models"]["version"] == "v2.2"
    assert config_fingerprint(s) == US_CONFIG_SHA256
    probs = pipeline.probabilities("combined")
    assert calm_display(probs, pipeline.scores, None, _calm(pipeline.settings, "jump")) is probs


def test_rule_calm_is_the_rule_without_its_stress_step(settings):
    scores = pd.DataFrame(
        {"stress": [2.0, 0.0, 0.0, 0.0], "growth": [-1.0, -1.0, 1.0, -1.0], "inflation": [0.0, 0.0, 0.0, 2.0]},
        index=pd.bdate_range("2020-01-01", periods=4),
    )
    assert list(rule_calm(scores, settings)) == ["slowdown", "slowdown", "expansion", "overheating"]


def test_confirmed_label_changes_only_after_holding():
    label = pd.Series(list("aabbabbbcc"))
    assert list(confirmed(label, 3)) == list("aaaaaaabbb")
    assert list(confirmed(label, 1)) == list(label)


@pytest.mark.parametrize("mode", ["rule", "rule_named", "gbm"])
def test_every_display_keeps_p_stress_and_sums_to_one(pipeline, mode):
    probs = pipeline.probabilities("combined")
    gbm = pipeline.probabilities("gbm")
    out = calm_display(probs, pipeline.scores, gbm, _calm(pipeline.settings, mode))
    pd.testing.assert_series_equal(out["stress"], probs["stress"])
    assert list(out.columns) == list(probs.columns)
    assert np.allclose(out.sum(axis=1), 1.0)
    assert (out >= 0).all().all()


def test_rule_named_shows_stress_on_the_same_days_and_names_calm_by_the_rule(pipeline):
    probs = pipeline.probabilities("combined")
    s = _calm(pipeline.settings, "rule_named")
    out = calm_display(probs, pipeline.scores, None, s)
    before, after = probs.idxmax(axis=1), out.idxmax(axis=1)
    assert ((before == "stress") == (after == "stress")).all()
    label = confirmed(rule_calm(pipeline.scores.reindex(probs.index), s), s["validation"]["confirm_days"])
    calm = after != "stress"
    assert (after[calm] == label[calm]).all()


def test_pipeline_applies_the_setting_and_leaves_the_alarm_alone(pipeline):
    other = pipeline.with_settings(_calm(pipeline.settings, "rule"))
    pd.testing.assert_series_equal(other.probabilities("combined")["stress"], pipeline.probabilities("combined")["stress"])
    pd.testing.assert_series_equal(other.alarm_score("combined"), pipeline.alarm_score("combined"))
    a, b = other.evaluate("combined"), pipeline.evaluate("combined")
    assert (a["detected"], a["brier"], a["ece"]) == (b["detected"], b["brier"], b["ece"])


def test_display_scores():
    index = pd.bdate_range("2020-01-01", periods=6)
    shown = pd.Series(["slowdown", "slowdown", "expansion", "expansion", "slowdown", "stress"], index=index)
    slow = pd.Series([True, False, False, True, True, np.nan], index=index, dtype=object)
    r = display_scores(shown, slow)
    assert r["recall"] == pytest.approx(2 / 3) and r["precision"] == pytest.approx(2 / 3)
    assert r["base_rate"] == pytest.approx(3 / 5) and r["shown_share"] == pytest.approx(0.5)
    assert r["ba"] == pytest.approx((2 / 3 + 1 / 2) / 2)


def test_gdp_below_potential_by_quarter_outside_episodes():
    quarters = pd.to_datetime(["2019-10-01", "2020-01-01", "2020-04-01", "2020-07-01"])
    actual = pd.Series([100.0, 100.2, 101.0, 101.1], index=quarters)  # +0.2%, +0.8%, +0.1%
    potential = pd.Series([100.0, 100.5, 101.0, 101.5], index=quarters)  # +0.5% a quarter
    index = pd.bdate_range("2020-01-01", "2020-12-31")
    episodes = [Episode(pd.Timestamp("2020-08-03"), pd.Timestamp("2020-08-31"), "drawdown", -0.2)]
    slow = below_potential(actual, potential, index, episodes)
    assert slow.loc["2020-02-03"] and not slow.loc["2020-05-01"] and slow.loc["2020-07-15"]
    assert not slow.loc["2020-08-10"]  # below potential, but a stress episode
    assert np.isnan(slow.loc["2020-11-02"])  # quarter not published


def _row(ba, switches=3.0, spell=30.0, recall=0.5, precision=0.6, base=0.5):
    return {
        "ba": ba,
        "switches_per_year": switches,
        "median_spell": spell,
        "recall": recall,
        "precision": precision,
        "base_rate": base,
    }


def test_selection_rule(settings):
    cfg = settings["slowdown_v23"]
    table = {("jump", "selection"): _row(0.50), ("rule", "selection"): _row(0.60), ("rule_named", "selection"): _row(0.605)}
    table[("gbm", "selection")] = _row(0.70, switches=8.0)  # outside the guards
    assert select(table, cfg) == "rule"  # tie within 0.01 goes to the earlier candidate
    table[("rule", "selection")] = _row(0.60, spell=10)
    assert select(table, cfg) == "rule_named"
    table[("rule_named", "selection")] = _row(0.51)
    table[("rule", "selection")] = _row(0.51)
    assert select(table, cfg) is None  # does not beat v2.2 by 0.02


def test_decision_needs_every_condition(settings):
    cfg = settings["slowdown_v23"]
    table = {
        ("jump", "decision"): _row(0.50, recall=0.12),
        ("rule", "decision"): _row(0.60, recall=0.40),
        ("rule", "whole"): _row(0.58),
        ("jump", "second"): _row(0.50),
        ("rule", "second"): _row(0.56),
    }
    assert decide_v23(table, "rule", cfg, True, True)["adopt"]
    assert not decide_v23(table, None, cfg, True, True)["adopt"]
    assert not decide_v23(table, "rule", cfg, True, False)["adopt"]  # P(stress) moved
    for key, bad in [
        (("rule", "decision"), _row(0.54, recall=0.40)),
        (("rule", "decision"), _row(0.60, recall=0.10)),
        (("rule", "decision"), _row(0.60, recall=0.40, precision=0.4)),
        (("rule", "second"), _row(0.51)),
        (("rule", "whole"), _row(0.58, switches=4.5)),
        (("rule", "whole"), _row(0.58, spell=10)),
    ]:
        assert not decide_v23({**table, key: bad}, "rule", cfg, True, True)["adopt"], key
    no_second = {k: v for k, v in table.items() if k[1] != "second"}
    assert not decide_v23(no_second, "rule", cfg, True, True)["adopt"]  # real data needs the second reference
    assert decide_v23(no_second, "rule", cfg, False, True)["adopt"]  # simulated data has none


def test_run_v23_on_simulated_data(pipeline):
    res = run_v23(pipeline, "combined")
    assert res["same_stress"] and res["names"] == ["jump", "rule", "rule_named", "gbm"]
    assert {part for _, part in res["table"]} == {"selection", "decision", "whole"}
    assert "decision" in res and isinstance(res["decision"]["adopt"], bool)


def test_cli_slowdown_v23(capsys, tmp_path):
    import yaml

    s = load_settings(overrides={"data": {"start": "2004-01-01", "end": "2020-12-31", "cache_dir": str(tmp_path)}})
    config = tmp_path / "settings.yaml"
    config.write_text(yaml.safe_dump(s))
    main(["--config", str(config), "slowdown", "--v23"])
    out = capsys.readouterr().out
    assert "P(stress) identical in every display: yes" in out and "Decision:" in out and "first part (selection)" in out
