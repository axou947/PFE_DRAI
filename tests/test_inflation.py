"""Inflation score, one vote per source (docs/INFLATION.md): the weighting, the explanation that follows it,
the outside reference and the pre-registered decision. The published model (v2.2) is unchanged."""

import copy

import numpy as np
import pandas as pd
import pytest

from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.explain import apply_what_if, contributions, input_weights, score_flips, what_ifs
from pfe_drai.features.build import inflation_groups, inflation_score, inflation_weights
from pfe_drai.publish.snapshot import config_fingerprint
from pfe_drai.validation.overheating import decide, high_inflation, overheating_report

INFLATION = ["cpi_inflation", "breakeven_level", "breakeven_change", "short_rate_change"]


def _sources(settings):
    return _deep_merge(settings, {"features": {"inflation": settings["overheating"]["tested"]["inflation"]}})


@pytest.fixture(scope="module")
def by_source(pipeline):
    return pipeline.with_settings(_sources(pipeline.settings))


def test_published_score_is_still_one_vote_per_input(pipeline):
    weights = inflation_weights(pipeline.settings)
    assert weights == {f: 0.25 for f in INFLATION}
    plain = pipeline.features[INFLATION].mean(axis=1)
    assert (pipeline.scores["inflation"] - plain).abs().max() < 1e-12


def test_the_check_does_not_change_the_published_fingerprint():
    # US settings fingerprint on main (test_euro.py): the `overheating` block is outside it.
    assert config_fingerprint(load_settings()) == "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"


def test_one_vote_per_source(settings, pipeline, by_source):
    s = _sources(settings)
    assert inflation_groups(s) == [["cpi_inflation"], ["breakeven_level", "breakeven_change"], ["short_rate_change"]]
    w = inflation_weights(s)
    assert w["cpi_inflation"] == w["short_rate_change"] == pytest.approx(1 / 3)
    assert w["breakeven_level"] == w["breakeven_change"] == pytest.approx(1 / 6)
    assert sum(w.values()) == pytest.approx(1)
    z = pipeline.features
    expected = (z["cpi_inflation"] + (z["breakeven_level"] + z["breakeven_change"]) / 2 + z["short_rate_change"]) / 3
    assert (inflation_score(z, s) - expected).abs().max() < 1e-12
    assert (by_source.scores["inflation"] - expected.loc[by_source.scores.index]).abs().max() < 1e-12
    # Stress and growth do not move.
    for dim in ("stress", "growth"):
        assert by_source.scores[dim].equals(pipeline.scores[dim])


def test_a_region_without_breakevens_gets_the_same_score_either_way():
    euro = load_settings(region="euro")
    assert inflation_weights(_sources(euro)) == inflation_weights(euro) == {"cpi_inflation": 0.5, "short_rate_change": 0.5}


def test_explanation_follows_the_weights(by_source):
    assert input_weights(by_source.settings)["inflation"] == inflation_weights(by_source.settings)
    parts = contributions(by_source)
    for dim, part in parts.items():
        assert (part.sum(axis=1) - by_source.scores[dim]).abs().max() < 1e-9, dim
    checked = 0
    for date in by_source.scores.index[300::400]:
        flips = score_flips(by_source.scores.loc[date], by_source.settings)
        possible, _ = what_ifs(by_source, date, flips)
        for w in possible:
            if w["dimension"] != "inflation":
                continue
            dz, now = w["z_change"], by_source.labels.loc[date]
            assert apply_what_if(by_source, date, w["feature"], dz * (1 + 1e-9) + np.sign(dz) * 1e-9) == w["to"] != now
            assert apply_what_if(by_source, date, w["feature"], dz * 0.99) == now
            checked += 1
    assert checked > 5


def test_reference_reads_each_month_on_its_days(settings):
    core = pd.Series([2.0, 3.1, np.nan], index=pd.to_datetime(["2022-01-01", "2022-02-01", "2022-03-01"]))
    days = pd.bdate_range("2022-01-28", "2022-04-04")
    high = high_inflation(core.dropna(), days, settings)
    assert not high.loc["2022-01-31"] and high.loc["2022-02-15"]
    assert high.loc["2022-03-15":].isna().all()


def test_report_on_simulated_data(pipeline):
    report = overheating_report(pipeline, "combined")
    s = report["summary"]
    assert report["reference"] == "simulated regimes"
    for key in ("overheating_share", "shown_share", "state_share", "inflation_ba", "shown_ba", "shown_recall"):
        assert 0 <= s[key] <= 1, key


def _decision_inputs():
    det = {
        "detected": 11,
        "median_latency": -3.0,
        "false_positives_per_year": 1.14,
        "false_alarm_share": 0.052,
        "brier": 0.090,
        "ece": 0.039,
    }
    return {"overheating": {"inflation_ba": 0.6, "shown_ba": 0.55}, "detection": det}


def test_decision_needs_every_condition(settings):
    before = _decision_inputs()
    after = _deep_merge(copy.deepcopy(before), {"overheating": {"inflation_ba": 0.7, "shown_ba": 0.6}})
    assert decide(before, after, settings)["adopt"]
    for change in [
        {"overheating": {"inflation_ba": 0.6}},  # no better than before
        {"overheating": {"shown_ba": 0.5}},  # what the app shows got worse
        {"overheating": {"shown_ba": 0.565}},  # better, but by less than the margin
        {"detection": {"detected": 10}},
        {"detection": {"median_latency": 6.0}},
        {"detection": {"false_positives_per_year": 1.6}},
        {"detection": {"false_alarm_share": 0.11}},
        {"detection": {"brier": 0.091}},
        {"detection": {"ece": 0.045}},
    ]:
        assert not decide(before, _deep_merge(after, change), settings)["adopt"], change
    assert decide(before, _deep_merge(after, {"detection": {"ece": 0.044}}), settings)["adopt"]  # within 0.005
