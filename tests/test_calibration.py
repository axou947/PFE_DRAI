import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from pfe_drai.config import _deep_merge
from pfe_drai.models.calibrator import calibrate_walk_forward, fit_logistic
from pfe_drai.models.combined import calibrate, combine, detector_score
from pfe_drai.validation import Episode, evaluate, find_episodes, refit_cuts
from pfe_drai.validation.calibration import calibration_report, calibration_scores, stress_event


def test_scores_of_a_calibrated_forecast():
    rng = np.random.default_rng(0)
    p = pd.Series(rng.uniform(0, 1, 200_000))
    y = pd.Series(rng.uniform(0, 1, len(p)) < p)
    good = calibration_scores(p, y)
    assert good["ece"] < 0.01
    assert good["brier"] == pytest.approx(((p - y) ** 2).mean())
    assert good["reliability"]["count"].sum() == len(p)
    # Saying 0% or 100% (the shape of a detector score) is badly calibrated against the same outcomes.
    bad = calibration_scores((p > 0.5).astype(float), y)
    assert bad["ece"] > 0.2 and bad["log_loss"] > good["log_loss"] and bad["brier"] > good["brier"]


def test_scores_skip_days_whose_outcome_is_unknown():
    p = pd.Series([0.2, 0.8, 0.5])
    y = pd.Series([0.0, 1.0, np.nan])
    assert calibration_scores(p, y)["n_days"] == 2
    assert calibration_scores(p.iloc[:0], y.iloc[:0])["n_days"] == 0


def test_stress_event_is_the_episode_or_its_coming_start(settings):
    index = pd.bdate_range("2020-01-01", periods=60)
    event = stress_event(index, [Episode(index[30], index[40], "drawdown", -0.2)], settings)
    assert event.iloc[24] == 0 and event.iloc[25] == 1  # 5 business days before the start
    assert event.iloc[40] == 1 and event.iloc[41] == 0  # the whole episode, then nothing
    assert event.iloc[-5:].isna().all()  # not known yet


def test_report_on_a_past_date_only_uses_what_was_known(pipeline, settings):
    p = pipeline.probabilities("kmeans")["stress"]
    day = p.index[1500]
    report = calibration_report(p, pipeline.episodes, settings, until=day)
    # Same as recomputing everything with the history that ended on that day.
    equity = pipeline.prices["equity"].loc[:day]
    alone = calibration_report(p.loc[:day], find_episodes(equity, settings), settings)
    assert report["n_days"] == alone["n_days"] == len(p.loc[:day]) - settings["validation"]["calibration"]["target_horizon_days"]
    assert report["brier"] == pytest.approx(alone["brier"])


def test_fit_logistic_recovers_a_platt_curve_and_keeps_weights_positive():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 2, (20_000, 2))
    y = (rng.uniform(size=len(x)) < expit(-1.0 + 0.8 * x[:, 0])).astype(float)
    b, w = fit_logistic(x[:, :1], y, l2=1.0)
    assert b == pytest.approx(-1.0, abs=0.1) and w[0] == pytest.approx(0.8, abs=0.05)
    # An input that lowers the odds gets weight 0: a higher reading can never lower the probability.
    y = (rng.uniform(size=len(x)) < expit(-1.0 + 0.8 * x[:, 0] - 0.5 * x[:, 1])).astype(float)
    _, w = fit_logistic(x, y, l2=1.0)
    assert w[0] > 0.5 and w[1] == 0.0


def test_warmup_keeps_the_backtest_refit_dates(settings):
    n, start = 6000, settings["validation"]["min_train_days"]
    for model in ("jump", "gbm", "onset"):
        usual = refit_cuts(n, settings, model)
        warm = refit_cuts(n, settings, model, warmup=504)
        assert warm.start <= 504 + warm.step and warm.start >= 504
        assert [c for c in warm if c >= start] == list(usual)


def test_warmup_predictions_match_the_backtest(pipeline):
    usual = pipeline.probabilities("jump", None)
    warm = pipeline.probabilities("jump", 504)
    assert warm.index[0] < usual.index[0]
    pd.testing.assert_frame_equal(warm.loc[usual.index[0] :], usual)


def test_calibrator_does_not_see_the_future(pipeline, settings):
    parts = {name: pipeline.probabilities(name, 504) for name in ("jump", "gbm", "onset")}
    start = pipeline.backtest_start
    full = calibrate(parts, pipeline.event, settings, start)
    # Same run with the last two years removed: no earlier calibrated probability may change.
    cut = pipeline.scores.index[-504]
    equity = pipeline.prices["equity"].loc[:cut]
    event = stress_event(equity.index, find_episodes(equity, settings), settings)
    part = calibrate({k: v.loc[:cut] for k, v in parts.items()}, event, settings, start)
    pd.testing.assert_series_equal(full.stress.loc[part.stress.index], part.stress)
    assert full.calibrated.all()
    assert (full.stress > 0).all() and (full.stress < 1).all()


def test_calibrator_is_a_rising_function_of_the_detector_score(pipeline):
    cal = pipeline.calibrated()
    score = pipeline.alarm_score("combined")
    for _, block in cal.stress.groupby(cal.fits.set_index("first_day")["intercept"].reindex(cal.stress.index).ffill()):
        order = score.loc[block.index].sort_values(kind="stable").index
        assert block.loc[order].is_monotonic_increasing


def test_calibrator_falls_back_without_enough_events(settings):
    index = pd.bdate_range("2010-01-01", periods=400)
    score = pd.Series(np.linspace(0, 1, len(index)), index=index)
    event = pd.Series(0.0, index=index)
    event.iloc[100:105] = 1.0  # 5 event days: fewer than min_event_days
    out = calibrate_walk_forward({"max": score}, event, settings, index[200])
    assert not out.calibrated.any()
    pd.testing.assert_series_equal(out.stress, score.loc[index[200] :], check_names=False)


def test_alarm_is_unchanged_by_calibration(pipeline, settings):
    """Detection reads the detector score: the same as v2, whatever P(stress) is shown."""
    sources = ("jump", *settings["models"]["combined"]["stress_sources"])
    v2 = combine(*(pipeline.probabilities(m) for m in sources))
    shown = pipeline.evaluate("combined")
    before = evaluate(v2, pipeline.prices["equity"], pipeline.episodes, settings)
    for key in ("detected", "median_latency_all", "false_positives_per_year", "false_alarm_share"):
        assert shown[key] == pytest.approx(before[key]), key
    score = detector_score(*(pipeline.probabilities(m) for m in sources))
    pd.testing.assert_series_equal(pipeline.alarm_score("combined"), score)
    # ...and calibration makes the probability a probability.
    assert shown["ece"] < before["ece"] and shown["log_loss"] < before["log_loss"]


def test_alarm_on_a_date(pipeline):
    score = pipeline.alarm_score("combined")
    on_days = score.index[(score > 0.5).rolling(3).sum().eq(3)]
    alarm = pipeline.alarm("combined", on_days[len(on_days) // 2])
    assert alarm["on"] and alarm["since"] <= on_days[len(on_days) // 2].date().isoformat()
    state = pipeline.state("combined").to_dict()
    assert {"on", "since", "score", "threshold"} <= set(state["alarm"])
    assert state["calibration"]["combination"] == "calibrated"
    assert state["calibration"]["calibrator"]["weights"]["max"] >= 0


def test_max_combination_is_still_available(pipeline, settings):
    s = _deep_merge(settings, {"models": {"combined": {"stress_combination": "max"}}})
    from pfe_drai.pipeline import Pipeline

    p = Pipeline(s, use_cache=False)
    p.__dict__.update({k: pipeline.__dict__[k] for k in ("raw", "_built", "episodes", "market", "onset", "event")})
    probs = p.probabilities("combined")
    pd.testing.assert_series_equal(probs["stress"], p.alarm_score("combined"))
