import numpy as np
import pandas as pd
import pytest

from pfe_drai.config import _deep_merge
from pfe_drai.features.market import INPUT_SETS, market_inputs
from pfe_drai.models import get_model
from pfe_drai.models.combined import combine
from pfe_drai.validation import episode_mask, find_episodes, onset_target, walk_forward
from pfe_drai.validation.holdout import run_holdout, select
from pfe_drai.validation.metrics import false_alarm_share, median_latency_all


def test_market_inputs_are_causal(pipeline, settings):
    prices = pipeline.prices
    full = market_inputs(prices, settings)
    cut = 3000
    part = market_inputs(prices.iloc[:cut], settings)
    pd.testing.assert_frame_equal(full.iloc[:cut], part)
    assert list(full.columns) == INPUT_SETS["market_credit"]


@pytest.mark.parametrize("after_start_days", [None, 21])
def test_onset_target_only_looks_horizon_days_ahead(pipeline, settings, after_start_days):
    equity, h = pipeline.prices["equity"], 5
    full = onset_target(equity.index, find_episodes(equity, settings), h, after_start_days)
    for cut in (1500, 2600, 4000):
        part_eq = equity.iloc[:cut]
        part = onset_target(part_eq.index, find_episodes(part_eq, settings), h, after_start_days)
        # Episode membership up to a day needs prices up to that day only...
        mask_full = episode_mask(equity.index, find_episodes(equity, settings)).iloc[:cut]
        pd.testing.assert_series_equal(mask_full, episode_mask(part_eq.index, find_episodes(part_eq, settings)))
        # ...so the target is the same once the horizon is inside the data.
        pd.testing.assert_series_equal(full.iloc[: cut - h], part.iloc[: cut - h])
        assert part.iloc[cut - h :].isna().all()


def test_onset_target_after_start_keeps_only_the_first_days():
    index = pd.bdate_range("2020-01-01", periods=100)
    from pfe_drai.validation import Episode

    ep = [Episode(index[40], index[90], "drawdown", -0.2)]
    target = onset_target(index, ep, horizon_days=5, after_start_days=10)
    assert target.iloc[34] == 0 and target.iloc[35] == 1  # 5 days before the start
    assert target.iloc[49] == 1 and target.iloc[50] == 0  # 10 days from the start
    assert target.iloc[-5:].isna().all()


def _onset_settings(settings, **onset):
    return _deep_merge(settings, {"models": {"onset": {"max_iter": 30, **onset}}})


@pytest.mark.parametrize("learner", ["gbm", "logistic"])
def test_onset_walk_forward_does_not_see_the_future(pipeline, settings, learner):
    s = _onset_settings(settings, learner=learner)
    market, scores, onset = pipeline.market, pipeline.scores, pipeline.onset
    full = walk_forward("onset", pipeline.features, scores, pipeline.labels, s, market=market, onset=onset)
    # Same run with the last two years removed: earlier predictions must not change.
    cut = len(scores) - 504
    equity = pipeline.prices["equity"].iloc[:cut]
    cfg = s["models"]["onset"]
    part_onset = onset_target(equity.index, find_episodes(equity, s), cfg["horizon_days"], cfg["after_start_days"])
    part = walk_forward(
        "onset",
        pipeline.features.iloc[:cut],
        scores.iloc[:cut],
        pipeline.labels.iloc[:cut],
        s,
        market=market.iloc[:cut],
        onset=part_onset,
    )
    pd.testing.assert_frame_equal(full.loc[part.index], part)
    assert np.allclose(full.sum(axis=1), 1.0)
    assert list(full.columns) == settings["regimes"]["order"]


@pytest.mark.parametrize("learner", ["gbm", "logistic"])
def test_onset_handles_an_input_that_starts_later(pipeline, settings, learner):
    # Real holdout: LQD/IEF only start in 2002, so credit is empty in the first training windows.
    s = _onset_settings(settings, learner=learner, inputs="market_credit")
    market = pipeline.market.copy()
    market.loc[: pipeline.scores.index[2000], ["credit_5d", "credit_21d"]] = np.nan
    probs = walk_forward("onset", pipeline.features, pipeline.scores, pipeline.labels, s, market=market, onset=pipeline.onset)
    assert probs["stress"].notna().all()


def test_onset_needs_market_inputs(pipeline, settings):
    with pytest.raises(ValueError, match="market inputs"):
        walk_forward("onset", pipeline.features, pipeline.scores, pipeline.labels, settings)


def test_onset_hold_keeps_a_probability_on():
    idx = pd.bdate_range("2020-01-01", periods=10)
    model = get_model("onset", {"regimes": {"order": ["expansion", "stress"]}, "models": {"onset": {"hold_days": 3}}})
    model.p_stress = lambda market: pd.Series([0, 0, 0.9, 0, 0, 0, 0, 0, 0, 0], index=idx, dtype=float)
    probs = model.predict_proba(pd.DataFrame(index=idx), None)
    assert list(probs["stress"]) == [0, 0, 0.9, 0.9, 0.9, 0, 0, 0, 0, 0]
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_combined_takes_the_highest_of_several_sources():
    idx = pd.bdate_range("2020-01-01", periods=2)
    cols = ["expansion", "overheating", "slowdown", "stress"]
    jump = pd.DataFrame([[0.6, 0.2, 0.1, 0.1], [0.5, 0.3, 0.2, 0.0]], index=idx, columns=cols)
    gbm = pd.DataFrame([[0.1, 0.1, 0.1, 0.7], [0.9, 0.0, 0.1, 0.0]], index=idx, columns=cols)
    onset = pd.DataFrame([[0.1, 0.1, 0.1, 0.7], [0.2, 0.2, 0.2, 0.4]], index=idx, columns=cols)
    out = combine(jump, gbm, onset)
    assert np.allclose(out["stress"], [0.7, 0.4])
    assert np.allclose(out.sum(axis=1), 1.0)
    pd.testing.assert_frame_equal(combine(jump, gbm), combine(jump, gbm, gbm))


def test_combined_v2_matches_its_parts(settings):
    from pfe_drai.pipeline import Pipeline

    s = _onset_settings(settings)
    s = _deep_merge(s, {"models": {"combined": {"stress_sources": ["gbm", "onset"]}}})
    p = Pipeline(s, use_cache=False)
    probs = p.probabilities("combined")
    parts = [p.probabilities(m)["stress"] for m in ("jump", "gbm", "onset")]
    assert np.allclose(probs["stress"], np.maximum.reduce([x.loc[probs.index] for x in parts]))
    # v2 can only raise P(stress): it detects every episode v1 detects, no later.
    v1 = combine(p.probabilities("jump"), p.probabilities("gbm"))
    assert (probs["stress"] >= v1["stress"].loc[probs.index] - 1e-12).all()


def test_median_latency_counts_misses_as_window_end(settings):
    lat = pd.DataFrame({"latency_days": [2, None, None, -3, 5]})
    assert median_latency_all(lat, settings) == 5.0
    lat = pd.DataFrame({"latency_days": [2, None, None]})
    assert median_latency_all(lat, settings) == settings["validation"]["episodes"]["detection_window_days"]


def test_false_alarm_share_sees_a_signal_that_stays_on(settings):
    idx = pd.bdate_range("2020-01-01", periods=200)
    always = pd.Series(True, index=idx)
    assert false_alarm_share(always, [], settings) == 1.0
    assert false_alarm_share(~always, [], settings) == 0.0


def test_holdout_selection_rule(settings):
    rows = pd.DataFrame(
        {
            "median_latency_all": [3.0, -2.0, 1.0, 1.0],
            "fp_per_year": [0.5, 2.0, 0.8, 0.6],
            "false_alarm_share": [0.04, 0.03, 0.12, 0.05],
        }
    )
    # Candidate 1 has too many false positives, 2 too much alarm time: 3 beats 0 on latency.
    assert select(rows, settings) == 3
    assert select(rows.iloc[[1, 2]], settings) is None


def test_holdout_runs_on_simulated_data(settings):
    s = _onset_settings(settings)
    s["validation"]["holdout"]["candidates"] = s["validation"]["holdout"]["candidates"][:2]
    res = run_holdout(s)
    assert not res.is_live
    assert len(res.rows) == 2 and res.rows["episodes"].gt(0).all()
    assert res.first_prediction >= pd.Timestamp(s["validation"]["holdout"]["start"])
    assert res.last_day <= pd.Timestamp(s["validation"]["holdout"]["end"])
    assert list(res.latencies.columns) == ["max_drawdown", *res.rows["candidate"]]
