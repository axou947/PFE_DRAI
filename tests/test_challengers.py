"""Challenger track record (docs/CHALLENGERS.md): published next to v2.2, never changing what v2.2 publishes."""

import json

import numpy as np
import pandas as pd
import pytest

from pfe_drai import challengers
from pfe_drai.cli import main
from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.data import tiingo
from pfe_drai.features.market import EXTRA, MARKET, market_inputs
from pfe_drai.publish.record import read_live
from pfe_drai.publish.snapshot import config_fingerprint, publish

NAMES = ["vix_term", "hy_credit"]


@pytest.fixture(scope="module")
def offline(pipeline):
    """The test pipeline, allowed to publish simulated data into a temporary folder."""
    allowed = {"publish": {"require_live_data": False, "opentimestamps": False}}
    return pipeline.with_settings(_deep_merge(pipeline.settings, allowed))


def test_the_published_model_is_unchanged():
    settings = load_settings()
    assert config_fingerprint(settings) == "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"
    assert settings["models"]["onset"]["inputs"] == "market"
    assert not set(EXTRA) & set(MARKET)


def test_each_challenger_is_v22_with_one_change(settings):
    assert challengers.challenger_names(settings) == NAMES
    for name, inputs in zip(NAMES, ["market_vix_term", "market_hy_fund"], strict=True):
        s = challengers.challenger_settings(settings, name)
        assert s["models"]["onset"]["inputs"] == inputs
        assert s["models"]["version"] == f"v2.2+{name}"
        assert config_fingerprint(s) != config_fingerprint(settings)
        # Everything else is the published model's.
        assert {k: v for k, v in s["models"].items() if k not in ("onset", "version")} == {
            k: v for k, v in settings["models"].items() if k not in ("onset", "version")
        }


def test_challenger_inputs():
    days = pd.bdate_range("2020-01-01", periods=300)
    prices = pd.DataFrame(
        {
            "equity": np.linspace(100, 120, 300),
            "vix": np.r_[np.full(250, 15.0), np.full(50, 40.0)],
            "vix3m": np.full(300, 20.0),
            "hy_fund": np.r_[np.full(250, 10.0), np.full(50, 9.0)],
            "treasury_fund": np.full(300, 10.0),
        },
        index=days,
    )
    f = market_inputs(prices, load_settings())
    assert f["vix_term"].iloc[0] == 0.75 and f["vix_term"].iloc[-1] == 2.0  # inverted in the spike
    assert f["hy_credit_5d"].iloc[252] > 0  # high yield falling against Treasuries reads as stress
    bare = market_inputs(prices[["equity", "vix"]], load_settings())
    assert bare[EXTRA].isna().all().all() and bare[MARKET].equals(f[MARKET])


def test_challengers_publish_their_own_chain_and_leave_the_published_model_alone(offline, tmp_path):
    before = offline.probabilities("combined").copy()
    champion = publish(offline, out_dir=tmp_path / "us")
    out = challengers.publish_challengers(offline, tmp_path / "challengers")
    assert set(out) == set(NAMES) and all(isinstance(p, type(champion)) for p in out.values())
    for name in NAMES:
        payload = json.loads(out[name].read_text(encoding="utf-8"))
        assert payload["model_version"] == f"v2.2+{name}"
        assert payload["config_sha256"] != json.loads(champion.read_text(encoding="utf-8"))["config_sha256"]
        assert read_live(tmp_path / "challengers" / name).chain_ok
    # The same market day again: nothing new.
    assert all(p is None for p in challengers.publish_challengers(offline, tmp_path / "challengers").values())
    pd.testing.assert_frame_equal(offline.probabilities("combined"), before)

    card = challengers.scorecard(offline, tmp_path / "us", tmp_path / "challengers")
    assert card["since"] == json.loads(out["vix_term"].read_text(encoding="utf-8"))["date"]
    assert list(card["models"]) == ["v2.2 (published)", *NAMES]
    assert all(m["days"] == 1 and m["chain_ok"] for m in card["models"].values())
    text = challengers.scorecard_markdown(card)
    assert "Challenger scorecard" in text and "hy_credit" in text
    json.dumps(challengers.slim(card))  # scorecard.json is plain JSON


def test_a_challenger_without_its_series_fails_alone(offline, tmp_path):
    s = _deep_merge(offline.settings, {"challengers": {"models": {"broken": {"series": ["nothing_here"]}}}})
    p = offline.with_settings(s)
    out = challengers.publish_challengers(p, tmp_path)
    assert isinstance(out["broken"], ValueError) and "nothing_here" in str(out["broken"])
    assert not isinstance(out["vix_term"], Exception)


def test_tiingo_reads_the_challenger_funds(monkeypatch, settings):
    calls = []
    monkeypatch.setenv(settings["data"]["tiingo_api_key_env"], "test")
    monkeypatch.setattr(tiingo, "fetch_tiingo", lambda t, *a: calls.append(t) or pd.Series([1.0]))
    tiingo.TiingoProvider(settings).fetch_subset(["hy_fund", "treasury_fund"], "2000-01-01", "2000-02-01")
    assert calls == ["VWEHX", "VFITX"]


def test_cli_backtest_says_it_decides_nothing(capsys):
    main(["challengers", "--backtest"])
    out = capsys.readouterr().out
    assert "decides nothing" in out and "vix_term" in out and "hy_credit" in out
