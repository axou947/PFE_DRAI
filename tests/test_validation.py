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
