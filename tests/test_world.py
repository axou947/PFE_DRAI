import numpy as np
import pandas as pd
import pytest

from pfe_drai.cli import main
from pfe_drai.config import load_settings
from pfe_drai.world import (
    HORIZONS,
    breadth,
    fetch_prices,
    indicators,
    load_markets,
    load_replay,
    period_return,
    snapshot,
    state_since,
)


@pytest.fixture(scope="module")
def world_settings():
    return load_settings(overrides={"data": {"start": "2004-01-01", "end": "2026-06-30"}})


@pytest.fixture(scope="module")
def world(world_settings):
    prices, errors = fetch_prices(world_settings, "synthetic")
    return prices, indicators(prices, world_settings), errors


def test_markets_file(world_settings):
    markets = load_markets(world_settings)
    ids = [m.id for m in markets]
    assert len(ids) == len(set(ids)) == 20
    assert all(len(i) == 3 and i.isupper() for i in ids)  # ISO-3 codes place them on the map
    assert {"USA", "FRA", "DEU", "GBR", "JPN"} <= set(ids)
    assert all(m.name["fr"] and m.name["en"] for m in markets)
    assert all(isinstance(r["date"], pd.Timestamp) for r in load_replay(world_settings))


def test_synthetic_prices(world, world_settings):
    prices, _, errors = world
    assert errors == {}
    assert list(prices.columns) == [m.id for m in load_markets(world_settings)]
    assert (prices > 0).all().all()
    # The US market is the same series as the regime model's equity input.
    from pfe_drai.data.synthetic import simulate

    data, _ = simulate("2004-01-01", "2026-06-30", world_settings["data"]["seed"])
    pd.testing.assert_series_equal(prices["USA"], data["equity"], check_names=False)


def test_period_return():
    idx = pd.bdate_range("2025-12-01", "2026-03-31")
    s = pd.Series(np.arange(len(idx), dtype=float) + 100, index=idx)
    last = idx[-1]
    assert period_return(s, last, "1D") == pytest.approx(s.iloc[-1] / s.iloc[-2] - 1)
    assert period_return(s, last, "YTD") == pytest.approx(s.iloc[-1] / s.loc[:"2025-12-31"].iloc[-1] - 1)
    assert period_return(s, last, "1M") == pytest.approx(s.iloc[-1] / s.loc[: last - pd.DateOffset(months=1)].iloc[-1] - 1)
    assert np.isnan(period_return(s, last, "1Y"))  # not enough history


def test_states_have_no_look_ahead(world, world_settings):
    prices, ind, _ = world
    cut = "2015-06-30"
    early = indicators(prices.loc[:cut], world_settings)
    for key in ["vol", "vol_pct", "drawdown", "state"]:
        pd.testing.assert_frame_equal(early[key], ind[key].loc[:cut])


def test_state_rule(world, world_settings):
    _, ind, _ = world
    state = ind["state"]
    assert set(np.unique(state.stack().dropna())) <= {0.0, 1.0, 2.0}
    assert state.iloc[:252].isna().all().all()  # needs a year of volatility history
    cfg = world_settings["world"]
    stress = state == 2
    # Stress is only ever entered on a day both conditions hold.
    entries = stress & ~stress.shift(fill_value=False)
    assert entries.values.sum() > 0
    assert (ind["vol_pct"].values[entries.values] >= cfg["stress"]["vol_percentile"]).all()
    assert (ind["drawdown"].values[entries.values] <= cfg["stress"]["drawdown"]).all()
    # Calm most of the time, stress rarely, and widespread in the scripted 2008 and 2020 crises.
    shares = state.stack().dropna().value_counts(normalize=True)
    assert shares[0.0] > 0.6 and shares[2.0] < 0.15
    b = breadth(state)
    assert b.loc["2020-03-01":"2020-04-30", "stress"].max() >= 0.5
    assert b.loc["2008-09-15":"2008-11-30", "stress"].max() > 0.5
    assert b.loc["2017-01-01":"2017-12-31", "stress"].max() < 0.5
    assert ((b["stress"] + b["elevated"]) <= 1).all()


def test_snapshot(world, world_settings):
    prices, ind, _ = world
    markets = load_markets(world_settings)
    for horizon in HORIZONS:
        snap = snapshot(prices, ind, markets, "2020-03-16", horizon)
        assert len(snap) == 20 and snap["return"].notna().all()
    snap = snapshot(prices, ind, markets, "2020-04-01", "1M")
    assert (snap["state"] == "stress").sum() >= 10
    assert all(d <= pd.Timestamp("2020-04-01") for d in snap["since"])
    # A market that stopped trading shows as no data instead of an old state.
    gone = prices.copy()
    gone.loc["2020-01-01":, "FRA"] = np.nan
    snap = snapshot(gone, indicators(gone, world_settings), markets, "2020-03-16", "1M")
    assert snap.loc["FRA", "state"] is None and np.isnan(snap.loc["FRA", "return"])


def test_state_since():
    s = pd.Series([0, 0, 1, 1, 2, 2, 2], index=pd.bdate_range("2026-01-05", periods=7), dtype=float)
    assert state_since(s, s.index[-1]) == s.index[4]
    assert state_since(s, s.index[3]) == s.index[2]


def test_tiingo_errors_do_not_hide_other_markets(world_settings, monkeypatch, tmp_path):
    from pfe_drai.data import tiingo

    def fake(ticker, key, start, end):
        if ticker == "KSA":
            raise RuntimeError("404")
        return pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-05", "2026-01-06"]))

    monkeypatch.setattr(tiingo, "fetch_tiingo", fake)
    monkeypatch.setenv("TIINGO_API_KEY", "test")
    settings = load_settings(overrides={"data": {"cache_dir": str(tmp_path), "end": "2026-01-06"}})
    prices, errors = fetch_prices(settings, "fred")
    assert list(errors) == ["SAU"] and "SAU" not in prices and len(prices.columns) == 19
    assert not (tmp_path / "world").exists()  # an incomplete download is not cached


def test_cli_world(capsys):
    main(["world", "--date", "2020-03-16", "--horizon", "3M"])
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "France" in out and "In stress:" in out
