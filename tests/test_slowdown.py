"""A real Slowdown regime (docs/SLOWDOWN.md): the growth score settings, the outside reference,
the pre-registered holdout and decision rule, and the model version shown on the track record."""

import copy
import json

import numpy as np
import pandas as pd

from pfe_drai.cli import main
from pfe_drai.config import _deep_merge
from pfe_drai.features.build import (
    FEATURES,
    build,
    expanding_zscore,
    growth_score,
    robust_zscore,
    score_dimension,
)
from pfe_drai.pipeline import Pipeline
from pfe_drai.publish.page import render, version_changes
from pfe_drai.publish.record import list_backtests, read_live
from pfe_drai.validation.slowdown import (
    balanced_accuracy,
    below_trend,
    decide,
    growth_holdout,
    select_growth,
    slowdown_report,
    spells,
)
from tests.test_track_record import _publish_days, _record, _settings


def _growth(settings, **growth):
    return _deep_merge(settings, {"features": {"growth": growth}})


def test_one_extreme_stretch_squeezes_standard_zscores_but_not_robust_ones():
    """The 2020 collapse in industrial production and jump in claims inflate an expanding standard
    deviation for every later day; the median and quartiles barely move."""
    rng = np.random.default_rng(0)
    values = rng.standard_normal(3000)
    values[2000:2060] = -30  # one quarter of collapse
    frame = pd.DataFrame({"x": values}, index=pd.bdate_range("2000-01-03", periods=3000))
    after = frame.index[2500:]
    standard = expanding_zscore(frame, 252, 4.0).loc[after, "x"]
    robust = robust_zscore(frame, 252, 4.0).loc[after, "x"]
    assert standard.std() < 0.5  # squeezed towards 0
    assert 0.8 < robust.std() < 1.2  # still reads on its usual scale


def test_robust_zscores_are_point_in_time():
    frame = pd.DataFrame({"x": np.random.default_rng(1).standard_normal(800)}, index=pd.bdate_range("2010-01-01", periods=800))
    short = robust_zscore(frame.iloc[:500], 252, 4.0)
    full = robust_zscore(frame, 252, 4.0)
    pd.testing.assert_frame_equal(short, full.iloc[:500])


def test_growth_score_uses_the_configured_inputs_and_smoothing(settings):
    z = pd.DataFrame(
        np.random.default_rng(2).standard_normal((100, len(FEATURES))),
        columns=list(FEATURES),
        index=pd.bdate_range("2020-01-01", periods=100),
    )
    s = _growth(settings, inputs=["industrial_production", "jobless_claims"], smooth_days=21)
    expected = z[["industrial_production", "jobless_claims"]].mean(axis=1).rolling(21, min_periods=1).mean()
    pd.testing.assert_series_equal(growth_score(z, s), expected.rename("growth"))
    assert score_dimension("curve_slope", s) is None  # feeds the models, not the growth score
    assert score_dimension("industrial_production", s) == "growth"
    assert score_dimension("vix_level", s) == "stress"


def test_every_feature_still_reaches_the_models_and_the_scores_stay_point_in_time(pipeline, settings):
    s = _growth(settings, inputs=["equity_momentum", "industrial_production", "jobless_claims"], scaling="robust", smooth_days=21)
    _, z, scores = build(pipeline.raw, s, pipeline.provider.release_dated)
    assert list(z.columns) == list(FEATURES) and not scores.isna().any().any()
    cut = {k: v.loc[: scores.index[900]] for k, v in pipeline.raw.items()}
    _, _, short = build(cut, s, pipeline.provider.release_dated)
    common = short.index.intersection(scores.index)
    pd.testing.assert_frame_equal(short.loc[common], scores.loc[common], check_exact=False, atol=1e-9)


def test_reference_months_cover_their_own_days(settings):
    activity = pd.Series([0.3, -0.2, np.nan], index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    index = pd.bdate_range("2020-01-30", "2020-03-03")
    below = below_trend(activity, index, settings)
    assert not below.loc["2020-01-31"] and below.loc["2020-02-03"] and below.loc["2020-02-28"]
    assert below.loc["2020-03-02":].isna().all()  # no reading yet: unknown, not "no slowdown"


def test_balanced_accuracy_and_spells():
    actual = pd.Series([True, True, False, False, False, False])
    assert balanced_accuracy(pd.Series([True, False, False, False, False, True]), actual) == (0.5 + 0.75) / 2
    assert list(spells(pd.Series([True, True, False, True, False, True, True, True]))) == [2, 1, 3]


def test_slowdown_report_on_simulated_data(pipeline):
    report = slowdown_report(pipeline, "combined")
    s = report["summary"]
    assert report["reference"] == "simulated regimes"
    for key in ("slowdown_share", "shown_share", "state_share", "growth_ba", "shown_ba", "shown_recall", "reference_share"):
        assert 0 <= s[key] <= 1, key
    assert len(report["states"]) == len(pipeline.state_maps("combined"))


def _decision_inputs():
    slow = {"growth_ba": 0.6, "state_share": 0.0, "shown_ba": 0.55}
    det = {
        "detected": 11,
        "median_latency": -3.0,
        "false_positives_per_year": 1.26,
        "false_alarm_share": 0.049,
        "brier": 0.091,
        "ece": 0.042,
    }
    return {"slowdown": slow, "detection": det}


def test_decision_needs_every_condition(settings):
    before = _decision_inputs()
    after = copy.deepcopy(before)
    after["slowdown"].update(growth_ba=0.7, state_share=0.6, shown_ba=0.6)
    assert decide(before, after, settings)["adopt"]
    for change in [
        {"slowdown": {"growth_ba": 0.6}},  # no better than before
        {"slowdown": {"state_share": 0.4}},  # Slowdown still not a state of the model
        {"detection": {"detected": 10}},  # an episode lost
        {"detection": {"false_alarm_share": 0.11}},
        {"detection": {"brier": 0.093}},
        {"detection": {"ece": 0.048}},
    ]:
        worse = _deep_merge(after, change)
        assert not decide(before, worse, settings)["adopt"], change
    assert decide(before, _deep_merge(after, {"detection": {"ece": 0.046}}), settings)["adopt"]  # within 0.005


def test_holdout_selection_rule(settings):
    rows = pd.DataFrame(
        {
            "order": [0, 1, 2, 3, None],
            "balanced_accuracy": [0.62, 0.70, 0.705, 0.80, 0.9],
            "spells_per_year": [1.0, 1.0, 1.0, 9.0, 0.5],  # the best flickers; the last is the old score
        }
    )
    assert select_growth(rows, settings) == 1  # 0.705 - 0.70 is within the tie margin: earlier one
    assert select_growth(rows.assign(spells_per_year=9.0), settings) is None


def test_growth_holdout_runs_on_simulated_data(settings):
    s = _deep_merge(settings, {"validation": {"holdout": {"start": "2000-01-03", "end": "2009-04-02"}}})
    s["validation"]["slowdown"]["holdout"]["evaluate_from"] = "2003-01-02"
    res = growth_holdout(s)
    assert res["reference"] == "simulated regimes" and not res["is_live"]
    assert len(res["rows"]) == 1 + len(s["validation"]["slowdown"]["holdout"]["candidates"])  # + the old score
    assert res["rows"]["balanced_accuracy"].between(0, 1).all()


def test_cli_slowdown_runs_without_a_reference(capsys, tmp_path):
    config = tmp_path / "settings.yaml"
    import yaml

    from pfe_drai.config import load_settings

    s = load_settings(overrides={"data": {"start": "2004-01-01", "end": "2016-12-30", "cache_dir": str(tmp_path)}})
    config.write_text(yaml.safe_dump(s))
    main(["--config", str(config), "slowdown", "--tested", "--model", "jump"])
    out = capsys.readouterr().out
    assert "before" in out and "refits with a state named Slowdown" in out and "simulated regimes" in out


# ---------------------------------------------------------------- track record: model versions
def test_each_published_day_says_which_model_made_it(settings, tmp_path):
    s = _settings(settings)
    _publish_days(s, tmp_path, pd.bdate_range("2026-10-01", periods=2))
    changed = _deep_merge(s, {"models": {"version": "next"}, "regimes": {"rule": {"growth_threshold": 0.0}}})
    _publish_days(changed, tmp_path, pd.bdate_range("2026-10-05", periods=2))
    live = read_live(tmp_path)
    assert live.chain_ok
    assert [e["model_version"] for e in live.entries] == [s["models"]["version"]] * 2 + ["next"] * 2
    assert version_changes(live) == [
        {"date": "2026-10-05", "from": s["models"]["version"], "to": "next", "config_sha256": live.entries[2]["config_sha256"]}
    ]
    page = render(live, {}, None, {}, s, "en")
    assert "The published model changed on" in page


def test_page_lists_every_backtest_record_and_marks_the_current_one(settings, tmp_path):
    folder = tmp_path / "backtest"
    folder.mkdir()
    old, new = _record(), _record()
    for record in (old, new):
        record["alarms"][0].update({"false_alarm": False, "open": False})
        record["alarms"][1].update({"false_alarm": True, "open": False})
    old.update(model_version="v2.1", generated_at="2026-10-01T22:40:00+00:00", config_sha256="a" * 64)
    new.update(model_version="v2.2", generated_at="2026-10-02T22:40:00+00:00", config_sha256="b" * 64)
    (folder / "2026-09-30.json").write_text(json.dumps(old))
    (folder / "2026-10-01.json").write_text(json.dumps(new))
    versions = list_backtests(tmp_path)
    assert [v["model_version"] for v in versions] == ["v2.1", "v2.2"]
    page = render(read_live(tmp_path), {}, new, {"file": "backtest/2026-10-01.json"}, settings, "fr", versions=versions)
    assert "Versions du modèle" in page and "v2.1" in page and "actuel" in page
    table = page[page.index("Versions du modèle") :]
    assert table.index("v2.1") < table.index("v2.2")


def test_a_pipeline_with_other_growth_settings_reads_the_same_data(pipeline, settings):
    before = settings["validation"]["slowdown"]["tested"]
    other = pipeline.with_settings(
        _deep_merge(settings, {"features": {"growth": before["growth"]}, "regimes": {"rule": before["rule"]}})
    )
    assert other.raw is pipeline.raw
    assert not other.scores["growth"].equals(pipeline.scores["growth"].reindex(other.scores.index))
    assert isinstance(other, Pipeline)


def test_real_reference_leaves_stress_episodes_and_unknown_months_out(settings, monkeypatch):
    from types import SimpleNamespace

    from pfe_drai.validation import Episode, slowdown

    index = pd.bdate_range("2020-01-01", "2020-04-30")
    activity = pd.Series([-0.5, -0.4, -1.0], index=pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01"]))
    monkeypatch.setattr(slowdown, "activity_index", lambda *a, **k: activity)
    fake = SimpleNamespace(
        truth=None,
        settings=_deep_merge(settings, {"data": {"provider": "fred"}}),
        episodes=[Episode(pd.Timestamp("2020-03-02"), pd.Timestamp("2020-03-31"), "drawdown", -0.3)],
    )
    below, slow, source = slowdown.reference_growth(fake, index)
    assert source.startswith("CFNAIMA3")
    assert below.loc["2020-01-02"] and slow.loc["2020-01-02"]
    assert below.loc["2020-03-10"] and not slow.loc["2020-03-10"]  # below trend, but a stress episode
    assert np.isnan(below.loc["2020-04-15"]) and np.isnan(slow.loc["2020-04-15"])  # no reading yet
