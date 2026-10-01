import pandas as pd

from pfe_drai.features import build
from pfe_drai.features.build import align


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


def test_monthly_values_are_known_after_their_month_and_lag():
    days = pd.bdate_range("2020-01-01", "2020-03-31")
    raw = {
        "equity": pd.Series(1.0, index=days),
        "indpro": pd.Series([100.0, 101.0], index=pd.to_datetime(["2020-01-01", "2020-02-01"])),
    }
    # FRED dates January on the 1st; it is published mid-February.
    prices = align(raw, {"indpro": 17})
    assert pd.isna(prices.loc["2020-02-14", "indpro"])
    assert prices.loc["2020-02-18", "indpro"] == 100.0
    assert prices.loc["2020-03-18", "indpro"] == 101.0


def test_release_dated_series_are_not_lagged_again():
    days = pd.bdate_range("2020-01-01", "2020-03-31")
    raw = {"equity": pd.Series(1.0, index=days), "indpro": pd.Series([100.0], index=pd.to_datetime(["2020-02-14"]))}
    prices = align(raw, {"indpro": 17}, release_dated={"indpro"})
    assert prices.loc["2020-02-14", "indpro"] == 100.0


def test_investment_grade_credit_stands_in_before_high_yield(pipeline, settings):
    """History starts with LQD; once HYG has its own z-score, nothing changes."""
    hyg_start = pd.Timestamp("2009-01-02")
    raw = {**pipeline.raw, "hy_bond": pipeline.raw["hy_bond"].loc[hyg_start:]}
    _, z, _ = build(raw, settings)
    assert z.index[0] == pipeline.features.index[0]  # no year lost waiting for HYG
    later = z.index[z.index > hyg_start + pd.Timedelta(days=600)]
    hy_only = build({**raw, "ig_bond": raw["ig_bond"] * float("nan")}, settings)[1]
    pd.testing.assert_series_equal(z.loc[later, "credit_stress"], hy_only.loc[later, "credit_stress"])
