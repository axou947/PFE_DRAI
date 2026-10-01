import numpy as np
import pandas as pd

from pfe_drai.features import DIMENSIONS
from pfe_drai.models import get_model
from pfe_drai.regimes import name_states, regime_centres, rule_labels


def _days(points, settings):
    scores = pd.DataFrame(points, columns=DIMENSIONS, index=pd.bdate_range("2020-01-01", periods=len(points)))
    return scores, rule_labels(scores, settings)


def test_states_take_the_name_of_the_closest_regime_centre(settings):
    scores, labels = _days([[2.5, -1.0, 0.0]] * 5 + [[-0.5, 0.5, 0.0]] * 10 + [[0.3, -0.8, 0.0]] * 5, settings)
    centres = regime_centres(scores, labels, settings)
    assert list(centres.index) == ["expansion", "slowdown", "stress"]  # no overheating day: no centre
    assert centres.loc["stress", "days"] == 5
    states = np.array([0] * 5 + [1] * 10 + [2] * 5)
    # State 2's centre sits between slowdown and stress, closer to slowdown.
    centroids = np.array([[2.4, -1.0, 0.0], [-0.5, 0.5, 0.1], [0.9, -0.8, 0.0]])
    table = name_states(states, centroids, scores, labels, settings)
    assert list(table["name"]) == ["stress", "expansion", "slowdown"]
    assert table.loc[2, "purity"] == 1.0 and np.isclose(table.loc[2, "distance"], 0.6)
    assert np.allclose(table[[c for c in table if c.startswith("share_")]].sum(axis=1), 1.0)


def test_absent_regime_is_not_forced_onto_a_state(settings):
    """The old one-to-one matching on hand-set prototypes gave every regime a state, even one the
    training window never saw: here no day is overheating, so no state can be called that."""
    scores, labels = _days([[-0.5, 0.5, 0.0]] * 20 + [[-0.2, 0.7, 0.3]] * 10 + [[2.0, -1.0, 0.0]] * 10, settings)
    states = np.array([0] * 20 + [1] * 10 + [2] * 5 + [3] * 5)
    centroids = np.array([[-0.5, 0.5, 0.0], [-0.2, 0.7, 0.3], [2.0, -1.0, 0.0], [0.1, -0.2, 0.75]])
    table = name_states(states, centroids, scores, labels, settings)
    assert "overheating" not in set(table["name"])
    assert list(table["name"][:3]) == ["expansion", "expansion", "stress"]


def test_models_expose_their_state_names(pipeline, settings):
    for name in ["jump", "kmeans"]:
        model = get_model(name, settings).fit(pipeline.features, pipeline.scores, pipeline.labels)
        assert list(model.state_table["name"]) == model.state_names
        assert set(model.state_names) <= set(settings["regimes"]["order"])


def test_state_map_matches_the_walk_forward_fit(pipeline):
    maps = pipeline.state_maps("combined")
    assert maps and all(start in pipeline.scores.index for start, _ in maps)
    latest = pipeline.state_map("combined")
    assert latest.equals(maps[-1][1])
    assert pipeline.state_map("combined", maps[0][0]).equals(maps[0][1])
    assert pipeline.state_map("combined", pipeline.scores.index[0]) is None  # before out-of-sample
    assert pipeline.state_map("gbm") is None and pipeline.state_maps("gbm") == []
    states = pipeline.state("combined").to_dict()["states"]
    assert [s["name"] for s in states] == list(latest["name"])
