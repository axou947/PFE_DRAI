"""Euro-area region: region overlay, parsers, release dating, the US model untouched (docs/EURO.md).

Everything runs offline on small recorded payloads and simulated data.
"""

import json
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

from pfe_drai.config import available_regions, load_settings
from pfe_drai.data import euro, get_provider
from pfe_drai.features.build import FEATURES, align
from pfe_drai.pipeline import Pipeline
from pfe_drai.publish.snapshot import NotEnabledError, config_fingerprint, publish
from pfe_drai.validation import find_episodes, rule_fingerprint

FIXTURES = Path(__file__).parent / "fixtures"
# Settings fingerprint of the US model on main before the region mechanism existed (2026-10-01).
US_CONFIG_SHA256 = "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"


def test_us_settings_untouched():
    settings = load_settings()
    assert "region" not in settings and "enabled" not in settings["publish"]
    assert config_fingerprint(settings) == US_CONFIG_SHA256
    assert config_fingerprint(load_settings(region="us")) == US_CONFIG_SHA256
    assert settings["validation"]["episodes"]["frozen"]["sha256"] == rule_fingerprint(settings)


def test_euro_overlay():
    assert available_regions() == ["us", "euro"]
    settings = load_settings(region="euro")
    assert settings["region"] == "euro" and settings["data"]["provider"] == "euro"
    assert settings["publish"]["dir"] == "track_record/euro" and settings["publish"]["enabled"] is False
    assert settings["models"]["version"] != load_settings()["models"]["version"]
    assert config_fingerprint(settings) != US_CONFIG_SHA256
    with pytest.raises(ValueError, match="Unknown region"):
        load_settings(region="mars")


def test_euro_rule_is_frozen_with_its_own_hash():
    settings = load_settings(region="euro")
    frozen = settings["validation"]["episodes"]["frozen"]
    assert frozen["sha256"] == rule_fingerprint(settings) and frozen["date"]
    # Same parameters as the US rule (no new degree of freedom), so the same hash.
    assert rule_fingerprint(settings) == rule_fingerprint(load_settings())
    tuned = load_settings(region="euro", overrides={"validation": {"episodes": {"drawdown_threshold": -0.08}}})
    with pytest.raises(ValueError, match="frozen"):
        find_episodes(pd.Series(np.linspace(100, 90, 300), index=pd.bdate_range("2020-01-01", periods=300)), tuned)


def test_parse_ecb_skips_missing_observations():
    series = euro.parse_ecb(json.loads((FIXTURES / "ecb_yc_10y.json").read_text()))
    assert list(series.index.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03", "2024-01-05"]
    assert list(series) == [2.51, 2.55, 2.6]


def test_parse_ecb_needs_one_series():
    payload = {"dataSets": [{"series": {"0": {"observations": {}}, "1": {"observations": {}}}}]}
    with pytest.raises(ValueError, match="one ECB series"):
        euro.parse_ecb(payload)


def test_parse_eurostat_monthly():
    series = euro.parse_eurostat(json.loads((FIXTURES / "eurostat_hicp.json").read_text()))
    assert list(series.index.strftime("%Y-%m-%d")) == ["2024-01-01", "2024-02-01", "2024-04-01"]  # March is missing
    assert list(series) == [100.0, 100.5, 101.4]


def test_parse_eurostat_refuses_several_series():
    payload = {
        "id": ["geo", "time"],
        "size": [2, 1],
        "value": {},
        "dimension": {"geo": {"category": {"index": {"EA": 0, "DE": 1}}}, "time": {"category": {"index": {"2024-01": 0}}}},
    }
    with pytest.raises(ValueError, match=r"more than one series.*geo \(2 values, e.g. EA, DE\)"):
        euro.parse_eurostat(payload)


def test_eurostat_alternatives_are_tried_in_order(monkeypatch):
    calls = []

    def fake(dataset, filters, start):
        calls.append(filters["unit"])
        if filters["unit"] != "I15":
            raise euro.NoDataError("the filters match no data")
        return pd.Series([1.0], index=[pd.Timestamp("2024-01-01")])

    monkeypatch.setattr(euro, "fetch_eurostat", fake)
    spec = {"dataset": "x", "filters": {"unit": "I21"}, "alternatives": [{"unit": "I10"}, {"unit": "I15"}]}
    series, used = euro.fetch_eurostat_any(spec, "2024-01-01")
    assert calls == ["I21", "I10", "I15"] and used == {"unit": "I15"} and len(series) == 1
    monkeypatch.setattr(euro, "fetch_eurostat", lambda *a: (_ for _ in ()).throw(euro.NoDataError("none")))
    with pytest.raises(euro.NoDataError):
        euro.fetch_eurostat_any(spec, "2024-01-01")


def test_parse_eurostat_empty_dimension_is_no_data():
    payload = {"id": ["geo", "time"], "size": [0, 1], "value": {}, "dimension": {"time": {"category": {"index": {"2024-01": 0}}}}}
    with pytest.raises(euro.NoDataError):
        euro.parse_eurostat(payload)


def test_ecb_alternative_keys_on_404(monkeypatch):
    def fake(dataset, key, start, end, monthly=False):
        if key != "B":
            response = httpx.Response(404, request=httpx.Request("GET", "https://x"))
            raise httpx.HTTPStatusError("not found", request=response.request, response=response)
        return pd.Series([1.0], index=[pd.Timestamp("2026-08-01")])

    monkeypatch.setattr(euro, "fetch_ecb", fake)
    series, used = euro.fetch_ecb_any({"dataset": "HICP", "key": "A", "alternative_keys": ["B"]}, "2026-01-01", "2026-09-30")
    assert used == {"key": "B"} and len(series) == 1
    with pytest.raises(euro.NoDataError, match="A: 404"):
        euro.fetch_ecb_any({"dataset": "HICP", "key": "A"}, "2026-01-01", "2026-09-30")


def test_stale_series_is_refused():
    old = pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-11-01", "2025-12-01"]))
    euro.check_fresh("cpi", old, "2026-01-31", 150)
    with pytest.raises(ValueError, match="stale.*2025-12-01"):
        euro.check_fresh("cpi", old, "2026-10-01", 150)
    with pytest.raises(ValueError, match="stale"):
        euro.check_fresh("cpi", pd.Series(dtype=float), "2026-10-01", 150)


def test_parse_ecb_monthly_period():
    payload = {
        "dataSets": [{"series": {"0": {"observations": {"0": [100.0], "1": [100.4]}}}}],
        "structure": {"dimensions": {"observation": [{"values": [{"id": "2024-01"}, {"id": "2024-02"}]}]}},
    }
    assert list(euro.parse_ecb(payload).index) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]


def test_release_dating_is_point_in_time():
    monthly = euro.parse_eurostat(json.loads((FIXTURES / "eurostat_hicp.json").read_text()))
    dated = euro.release_dated(monthly, lag_days=18, monthly=True)
    # January's index is public 18 days after January 31, not on January 1.
    assert dated.index[0] == pd.Timestamp("2024-02-18") and dated.iloc[0] == 100.0
    days = pd.bdate_range("2024-01-02", "2024-03-29")
    prices = align({"equity": pd.Series(1.0, index=days), "cpi": dated}, {}, {"cpi"})
    assert prices["cpi"].loc[:"2024-02-16"].isna().all()
    assert prices.loc["2024-02-19", "cpi"] == 100.0
    assert prices.loc["2024-03-15", "cpi"] == 100.0  # February's index is public from March 18
    assert prices.loc["2024-03-19", "cpi"] == 100.5


def test_realised_vol_in_percent():
    eq = pd.Series(
        100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.01, 200))), index=pd.bdate_range("2020-01-01", periods=200)
    )
    vol = euro.realised_vol_percent(eq)
    assert vol.index[0] == eq.index[21] and 5 < vol.mean() < 30  # about 1% a day = 16% a year


@pytest.fixture(scope="module")
def euro_settings():
    return load_settings(
        region="euro",
        overrides={
            "data": {"start": "2004-01-01", "end": "2026-06-30"},
            "validation": {"refit_every_days": 252},
            "models": {"gbm": {"max_iter": 30}},
        },
    )


@pytest.fixture
def patched_sources(monkeypatch, euro_settings):
    """Euro-shaped payloads built from the simulator: the euro catalog's meaning, not its numbers."""
    sim = get_provider({**euro_settings, "data": {**euro_settings["data"], "provider": "synthetic"}}).fetch(
        pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30")
    )
    monthly = {k: sim[k].resample("MS").last().dropna() for k in ("cpi", "indpro", "claims")}
    spread = (sim["us10y"] * 0 + 0.5 + (sim["vix"] / 40)).rename("spread")
    ecb = {
        "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y": sim["us10y"],
        "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y": sim["us2y"],
        "B.U2.EUR.4F.G_N_C.SV_C_YM.SR_10Y": sim["us10y"] + spread,
        "M.U2.N.000000.4D0.INX": monthly["cpi"],
    }
    stat = {"sts_inpr_m": monthly["indpro"], "une_rt_m": monthly["claims"] / 50_000}
    monkeypatch.setenv("TIINGO_API_KEY", "test")
    monkeypatch.setattr(euro, "fetch_tiingo", lambda ticker, key, start, end: sim["equity"])
    monkeypatch.setattr(euro, "fetch_ecb", lambda dataset, key, start, end, monthly=False: ecb[key])
    monkeypatch.setattr(euro, "fetch_eurostat", lambda dataset, filters, start: stat[dataset])


def test_euro_provider_returns_release_dated_series(patched_sources, euro_settings):
    provider = get_provider(euro_settings)
    data = provider.fetch(pd.Timestamp("2004-01-01"), pd.Timestamp("2026-06-30"))
    provider.check(data)
    assert set(data) == set(euro.REQUIRED)
    assert provider.release_dated == {"us10y", "us2y", "credit_spread", "cpi", "indpro", "claims"}
    # Monthly series are public after the end of their month plus the lag (2004-01 HICP: 2004-01-31 + 18 days).
    assert data["cpi"].index[0] >= pd.Timestamp("2004-02-18")
    assert data["claims"].index[0] >= pd.Timestamp("2004-03-06")
    assert provider.is_live


def test_euro_pipeline_runs_without_breakeven_and_credit_etf(patched_sources, euro_settings):
    p = Pipeline(euro_settings, use_cache=False)
    assert set(FEATURES) - set(p.features.columns) == {"breakeven_level", "breakeven_change"}
    assert list(p.scores.columns) == ["stress", "growth", "inflation"] and not p.scores.isna().any().any()
    assert p.scores.index[0] > pd.Timestamp("2005-01-01")
    state = p.state()
    assert state.regime in ("expansion", "overheating", "slowdown", "stress") and state.is_live_data
    assert "credit_stress" in p.features.columns and p.market.shape[1] == 13


def test_euro_publication_is_off(euro_settings):
    with pytest.raises(NotEnabledError, match="decision rule"):
        publish(Pipeline(euro_settings, use_cache=False))
