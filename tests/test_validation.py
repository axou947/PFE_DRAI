import pandas as pd
import pytest

from pfe_drai.config import load_settings
from pfe_drai.validation import find_episodes, rule_fingerprint, walk_forward


def test_walk_forward_is_out_of_sample(pipeline, settings):
    probs = walk_forward("kmeans", pipeline.features, pipeline.scores, pipeline.labels, settings)
    assert probs.index[0] == pipeline.scores.index[settings["validation"]["min_train_days"]]
    assert probs.index.is_unique


def test_episodes_found_on_crises(pipeline, settings):
    episodes = find_episodes(pipeline.prices["equity"], settings)
    starts = pd.DatetimeIndex([e.start for e in episodes])
    assert any((starts >= "2008-01-01") & (starts <= "2008-12-31"))
    assert all(e.end >= e.start for e in episodes)


def test_evaluate_reports_targets(pipeline):
    result = pipeline.evaluate("kmeans")
    for key in ("median_latency", "false_positives_per_year", "brier_stress", "meets_latency_target", "accuracy_truth"):
        assert key in result
    assert 0 <= result["brier_stress"] <= 1


def test_episode_rule_is_frozen(settings):
    frozen = settings["validation"]["episodes"]["frozen"]
    assert rule_fingerprint(settings) == frozen["sha256"]


def test_changed_episode_rule_is_refused(pipeline, settings):
    changed = load_settings(overrides={"validation": {"episodes": {"drawdown_threshold": -0.08}}})
    with pytest.raises(ValueError, match="frozen"):
        find_episodes(pipeline.prices["equity"], changed)


def _path(*legs):
    """Equity curve from (number of business days, total return) legs."""
    values = [100.0]
    for days, ret in legs:
        step = (1 + ret) ** (1 / days)
        values += [values[-1] * step**k for k in range(1, days + 1)]
    return pd.Series(values, index=pd.bdate_range("2000-01-03", periods=len(values)))


def test_two_falls_after_a_recovery_are_two_episodes(settings):
    # Fall, full recovery, then a second fall 3 months later (2015 then 2016, 2022).
    equity = _path((300, 0.2), (20, -0.15), (30, 0.18), (60, 0.0), (20, -0.15), (100, 0.0))
    starts = [e.start for e in find_episodes(equity, settings)]
    assert len(starts) == 2


def test_no_new_episode_without_recovery(settings):
    # Crash, then a market that hovers around -10% without recovering (2009, early 2023).
    equity = _path((300, 0.2), (40, -0.4), (100, 0.45), (5, -0.03), (5, 0.03), (5, -0.03), (100, 0.0))
    assert len(find_episodes(equity, settings)) == 1
