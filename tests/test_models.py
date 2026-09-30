import numpy as np
import pytest

from pfe_drai.models import available_models, get_model
from pfe_drai.models.jump import forward_values


@pytest.mark.parametrize("name", ["kmeans", "jump", "gbm"])
def test_probabilities_sum_to_one(pipeline, settings, name):
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
    assert set(available_models()) == {"kmeans", "jump", "gbm"}
