import numpy as np
import pandas as pd
import pytest

from pfe_drai.config import _deep_merge
from pfe_drai.models import available_models, get_model
from pfe_drai.models.combined import combine
from pfe_drai.models.jump import forward_values


@pytest.mark.parametrize("name", ["kmeans", "jump", "gbm", "combined"])
def test_probabilities_sum_to_one(pipeline, settings, name):
    # A combined model can only be fitted directly with z-score components (v1, jump + gbm).
    settings = _deep_merge(settings, {"models": {"combined": {"stress_sources": ["gbm"], "stress_combination": "max"}}})
    model = get_model(name, settings).fit(pipeline.features, pipeline.scores, pipeline.labels)
    probs = model.predict_proba(pipeline.features, pipeline.scores)
    assert list(probs.columns) == settings["regimes"]["order"]
    assert np.allclose(probs.sum(axis=1), 1.0)


def test_jump_filter_is_causal():
    rng = np.random.default_rng(0)
    loss = rng.random((200, 4))
    full = forward_values(loss, 5.0)
    part = forward_values(loss[:120], 5.0)
    assert np.allclose(full[:120], part)


def test_registry():
    assert set(available_models()) == {"kmeans", "jump", "gbm", "combined", "onset"}


def test_combined_takes_the_higher_stress_probability():
    idx = pd.bdate_range("2020-01-01", periods=3)
    cols = ["expansion", "overheating", "slowdown", "stress"]
    jump = pd.DataFrame([[0.6, 0.2, 0.1, 0.1], [0.0, 0.0, 0.0, 1.0], [0.5, 0.3, 0.2, 0.0]], index=idx, columns=cols)
    gbm = pd.DataFrame([[0.1, 0.1, 0.1, 0.7], [0.9, 0.0, 0.1, 0.0], [0.7, 0.3, 0.0, 0.0]], index=idx, columns=cols)
    out = combine(jump, gbm)
    assert list(out.columns) == cols
    assert np.allclose(out.sum(axis=1), 1.0)
    assert np.allclose(out["stress"], [0.7, 1.0, 0.0])
    # Calm regimes keep the jump model's proportions.
    assert np.allclose(out.iloc[0, :3], np.array([0.6, 0.2, 0.1]) / 0.9 * 0.3)
    assert np.allclose(out.iloc[2], jump.iloc[2])


def test_combined_walk_forward_matches_its_parts(pipeline, settings):
    from pfe_drai.validation import walk_forward

    probs = pipeline.probabilities("combined")
    parts = [pipeline.probabilities(m)["stress"].loc[probs.index] for m in get_model("combined", settings).components]
    # The alarm reads the highest stress probability; P(stress) shown is its calibrated version.
    assert np.allclose(pipeline.alarm_score("combined"), np.maximum.reduce(parts))
    assert np.allclose(probs["stress"], pipeline.calibrated().stress)
    assert np.allclose(probs.sum(axis=1), 1.0)
    direct = walk_forward(
        "combined",
        pipeline.features,
        pipeline.scores,
        pipeline.labels,
        settings,
        market=pipeline.market,
        onset=pipeline.onset,
        event=pipeline.event,
    )
    pd.testing.assert_frame_equal(direct, probs)
