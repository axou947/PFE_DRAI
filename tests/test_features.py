import pandas as pd

from pfe_drai.features import build


def test_features_are_point_in_time(pipeline, settings):
    """Features on a given day must not change when later data is added."""
    raw = pipeline.raw
    cut = pd.Timestamp("2015-06-30")
    truncated = {k: v.loc[:cut] for k, v in raw.items()}
    _, z_short, _ = build(truncated, settings)
    common = z_short.index[-50:]
    pd.testing.assert_frame_equal(z_short.loc[common], pipeline.features.loc[common], check_exact=False, atol=1e-9)


def test_scores_have_three_dimensions(pipeline):
    assert list(pipeline.scores.columns) == ["stress", "growth", "inflation"]
    assert not pipeline.scores.isna().any().any()
