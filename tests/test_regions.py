"""UK, Japan and emerging-market regions: overlays, parsers, composites, the US model untouched (docs/REGIONS.md).

Everything runs offline on small recorded payloads and simulated data.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pfe_drai.config import available_regions, load_settings
from pfe_drai.data import get_provider, official, regional
from pfe_drai.features.build import FEATURES
from pfe_drai.pipeline import Pipeline
from pfe_drai.publish.snapshot import NotEnabledError, config_fingerprint, publish
from pfe_drai.validation import rule_fingerprint
from pfe_drai.validation.holdout import run_holdout

FIXTURES = Path(__file__).parent / "fixtures"
REGIONS = ["uk", "japan", "em"]
US_CONFIG_SHA256 = "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"
# Features each region does not have (docs/REGIONS.md, "What each region reads").
DROPPED = {
    "uk": {"credit_stress"},
    "japan": {"credit_stress", "breakeven_level", "breakeven_change"},
    "em": {"jobless_claims", "breakeven_level", "breakeven_change"},
}


def test_regions_are_listed_and_the_us_is_untouched():
    assert available_regions() == ["us", "em", "euro", "japan", "uk"]
    assert config_fingerprint(load_settings()) == US_CONFIG_SHA256


@pytest.mark.parametrize("region", REGIONS)
def test_overlay(region):
    settings = load_settings(region=region)
    assert settings["region"] == region and settings["data"]["provider"] == "regional"
    assert settings["publish"] == {**settings["publish"], "dir": f"track_record/{region}", "enabled": False}
    assert settings["models"]["version"] == f"{region}-v1"
    assert config_fingerprint(settings) != US_CONFIG_SHA256
    # The US rule, unchanged and frozen on its own; the US onset detector, without a holdout selection.
    frozen = settings["validation"]["episodes"]["frozen"]
    assert frozen["sha256"] == rule_fingerprint(settings) == rule_fingerprint(load_settings())
    assert settings["models"]["onset"] == {**load_settings()["models"]["onset"], "learner": "gbm", "inputs": "market"}
    assert settings["validation"]["holdout"] is None
    assert set(settings["features"]["drop"]) == DROPPED[region]


def test_no_holdout_for_the_new_regions():
    with pytest.raises(ValueError, match="No holdout for region 'uk'"):
        run_holdout(load_settings(region="uk"))


# ---- parsers ----------------------------------------------------------------------------------------


def test_parse_boe():
    frame = official.parse_boe((FIXTURES / "boe_iadb.csv").read_text())
    assert list(frame.columns) == ["IUDMNZC", "IUDMRZC"]
    assert frame.index[0] == pd.Timestamp("2024-01-02") and frame.loc["2024-01-04", "IUDMNZC"] == 3.7421
    assert np.isnan(frame.loc["2024-01-03", "IUDMRZC"])


def test_parse_boe_refuses_an_error_page():
    with pytest.raises(official.NoDataError, match="web page"):
        official.parse_boe("<html><body>Invalid series code value supplied.</body></html>")


def test_parse_mof():
    frame = official.parse_mof((FIXTURES / "mof_jgbcme.csv").read_text())
    assert frame.index[0] == pd.Timestamp("1974-09-24") and np.isnan(frame.iloc[0]["10Y"])
    assert frame.loc["2024-01-05", "2Y"] == 0.05 and frame.loc["2024-01-05", "10Y"] == 0.65


def test_parse_sdmx_csv_bis():
    frame = official.parse_sdmx_csv((FIXTURES / "bis_cpi.csv").read_text())
    assert sorted(frame.columns) == ["GB", "JP", "NA"]  # "NA" is Namibia, not a missing value
    assert frame.loc["2024-02-01", "GB"] == 132.3
    assert np.isnan(frame.loc["2024-02-01", "JP"])  # the BIS writes "NaN"


def test_parse_sdmx_csv_oecd():
    frame = official.parse_sdmx_csv((FIXTURES / "oecd_kei.csv").read_text())
    assert list(frame.index) == [pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-01")]
    assert frame.loc["2026-07-01", "JPN"] == 2.5 and np.isnan(frame.loc["2026-06-01", "JPN"])


def test_parse_sdmx_csv_refuses_an_open_dimension():
    text = "REF_AREA,MEASURE,TIME_PERIOD,OBS_VALUE\nGBR,CP,2026-07,1\nGBR,PRVM,2026-07,2\n"
    with pytest.raises(ValueError, match="several series for GBR"):
        official.parse_sdmx_csv(text)


def test_period_start():
    assert official.period_start("2024-03") == pd.Timestamp("2024-03-01")
    assert official.period_start("2024-03-15") == pd.Timestamp("2024-03-15")
    assert official.period_start("2024-Q2") == pd.Timestamp("2024-04-01")


# ---- composites -------------------------------------------------------------------------------------


def test_composite_index_weights_the_changes():
    months = pd.date_range("2024-01-01", periods=4, freq="MS")
    frame = pd.DataFrame({"A": [100, 110, 121, 133.1], "B": [100, 100, 100, 100.0]}, index=months)
    out = regional.composite(frame, {"A": 3, "B": 1}, "index")
    # Each month: a quarter of B's 0% and three quarters of A's log(1.1).
    assert out.iloc[0] == 100 and np.allclose(np.log(out).diff().dropna(), 0.75 * np.log(1.1))


def test_composite_renormalises_and_needs_half_the_weight():
    months = pd.date_range("2024-01-01", periods=4, freq="MS")
    frame = pd.DataFrame(
        {"A": [100, 110, 121, np.nan], "B": [100, 100, np.nan, np.nan], "C": [100, 100, 100, 101.0]}, index=months
    )
    out = regional.composite(frame, {"A": 6, "B": 3, "C": 1}, "index")
    # March: B is missing, A and C carry 7/10 of the weight: their average change.
    assert np.isclose(np.log(out.loc["2024-03-01"] / out.loc["2024-02-01"]), 6 / 7 * np.log(1.1))
    # April: only C reports (1/10 of the weight): not a value, the composite ends in March.
    assert out.index[-1] == pd.Timestamp("2024-03-01")
    with pytest.raises(ValueError, match="never reach"):
        regional.composite(frame[["C"]], {"A": 6, "C": 1}, "index")


def test_composite_rate_carries_a_level_only_inside_its_own_range():
    days = pd.date_range("2024-01-01", periods=5, freq="D")
    frame = pd.DataFrame({"A": [5.0, np.nan, 5.5, 5.5, 5.5], "B": [1.0, 1.0, 1.0, np.nan, np.nan]}, index=days)
    out = regional.composite(frame, {"A": 1, "B": 1}, "rate")
    assert out.iloc[0] == 3.0  # weighted level on the first day
    assert out.loc["2024-01-03"] == 3.25  # A's +0.5 (carried 5.0 on Jan 2), B flat: half of it
    # B stops on Jan 3: it is not carried after, A alone holds half the weight and is flat.
    assert out.loc["2024-01-05"] == 3.25


def test_composite_offset_does_not_move_zscores():
    from pfe_drai.features.build import expanding_zscore

    x = pd.Series(np.random.default_rng(1).normal(size=400)).cumsum().to_frame("x")
    assert np.allclose(expanding_zscore(x, 252, 4).dropna(), expanding_zscore(x + 7.5, 252, 4).dropna())


# ---- provider ---------------------------------------------------------------------------------------


def _settings(region):
    return load_settings(
        region=region,
        overrides={
            "data": {"start": "2004-01-01", "end": "2026-06-30"},
            "validation": {"refit_every_days": 252},
            "models": {"gbm": {"max_iter": 30}},
        },
    )


@pytest.fixture(scope="module")
def sim():
    settings = _settings("uk")
    provider = get_provider({**settings, "data": {**settings["data"], "provider": "synthetic"}})
    return provider.fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))


@pytest.fixture
def patched_sources(monkeypatch, sim):
    """Region-shaped payloads built from the simulator: each source's meaning, not its numbers."""
    calls = []
    monthly = {k: sim[k].resample("MS").last().dropna() for k in ("cpi", "indpro", "claims", "us10y")}
    tickers = {"EWU": sim["equity"], "EWJ": sim["equity"], "EEM": sim["equity"], "EMB": sim["hy_bond"], "IEF": sim["treasury"]}
    boe = pd.DataFrame({"IUDMNZC": sim["us10y"], "IUDSNZC": sim["us2y"], "IUDMRZC": sim["us10y"] - sim["breakeven10"]})
    measures = {"PRVM": monthly["indpro"], "UNEMP": monthly["claims"] / 50_000, "IRLT": monthly["us10y"]}

    def areas(key):
        return next(part for part in key.split(".") if any(c.isupper() for c in part) and len(part) >= 2 and part != "M")

    def sdmx(series, key):
        names = areas(key).split("+")
        return pd.DataFrame({name: series * (1 + 0.01 * i) for i, name in enumerate(names)})

    def fake_oecd(flow, key, start):
        calls.append(("oecd", key))
        return sdmx(measures[key.split(".")[2]], key)

    def fake_bis(flow, key, start):
        calls.append(("bis", key))
        return sdmx(monthly["cpi"] if flow == "WS_LONG_CPI" else sim["us2y"], key)

    monkeypatch.setenv("TIINGO_API_KEY", "test")
    monkeypatch.setenv("FRED_API_KEY", "test")

    def fake_tiingo(ticker, key, start, end):
        calls.append(("tiingo", ticker))
        return tickers[ticker]

    monkeypatch.setattr(regional, "fetch_tiingo", fake_tiingo)
    fx = pd.Series(1.3, index=sim["equity"].index)
    monkeypatch.setattr(regional, "fetch_fred", lambda sid, key, start, end: calls.append(("fred", sid)) or fx)
    monkeypatch.setattr(regional, "fetch_boe", lambda codes, start, end: calls.append(("boe", tuple(codes))) or boe[codes])
    monkeypatch.setattr(regional, "fetch_mof", lambda start, end: pd.DataFrame({"2Y": sim["us2y"], "10Y": sim["us10y"]}))
    monkeypatch.setattr(regional, "fetch_oecd", fake_oecd)
    monkeypatch.setattr(regional, "fetch_bis", fake_bis)
    return calls


@pytest.mark.parametrize("region", REGIONS)
def test_provider_returns_release_dated_series(patched_sources, region):
    settings = _settings(region)
    provider = get_provider(settings)
    data = provider.fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    provider.check(data)
    assert set(data) == set(settings["data"]["regional"]["series"])
    market = {n for n, s in settings["data"]["regional"]["series"].items() if s["source"] in ("tiingo", "realised_vol")}
    assert provider.release_dated == set(data) - market
    # 2004-01 CPI is public at the end of January plus 45 days, not before.
    assert data["cpi"].index[0] >= pd.Timestamp("2004-03-16") and provider.is_live
    assert all(provider.details[name] for name in data)


def test_local_currency(patched_sources, sim):
    data = get_provider(_settings("uk")).fetch_subset(["equity"], pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    assert np.allclose(data["equity"], sim["equity"].loc["2004-01-01":] / 1.3)  # dollars / dollars per pound
    data = get_provider(_settings("japan")).fetch_subset(["equity"], pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    assert np.allclose(data["equity"], sim["equity"].loc["2004-01-01":] * 1.3)  # dollars * yen per dollar


def test_fetch_subset_reads_only_what_is_asked(patched_sources):
    data = get_provider(_settings("em")).fetch_subset(["vix"], pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    assert list(data) == ["vix"] and patched_sources == [("tiingo", "EEM")]


def test_em_composites_use_one_query_per_series(patched_sources):
    get_provider(_settings("em")).fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    sdmx = [key for source, key in patched_sources if source in ("oecd", "bis")]
    assert len(sdmx) == 4 and "CHN+IND+KOR+BRA+ZAF+MEX.M.IRLT.PA._Z._Z._Z" in sdmx


def test_a_stale_series_stops_the_run(patched_sources, monkeypatch):
    old = pd.DataFrame({"GB": pd.Series([100.0, 101.0], index=pd.to_datetime(["2021-05-01", "2021-06-01"]))})
    monkeypatch.setattr(regional, "fetch_bis", lambda flow, key, start: old)
    with pytest.raises(ValueError, match="'cpi' is stale"):
        get_provider(_settings("uk")).fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))


def test_missing_keys_are_named(monkeypatch):
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TIINGO_API_KEY"):
        get_provider(_settings("uk")).fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))


@pytest.mark.parametrize("region", REGIONS)
def test_pipeline_runs(patched_sources, region):
    p = Pipeline(_settings(region), use_cache=False)
    assert set(FEATURES) - set(p.features.columns) == DROPPED[region]
    assert list(p.scores.columns) == ["stress", "growth", "inflation"] and not p.scores.isna().any().any()
    state = p.state()
    assert state.regime in ("expansion", "overheating", "slowdown", "stress") and state.is_live_data
    with pytest.raises(NotEnabledError, match="decision rule"):
        publish(p)
