import numpy as np
import pandas as pd
import pytest

from pfe_drai.cli import main
from pfe_drai.config import load_settings
from pfe_drai.world import (
    HORIZONS,
    Market,
    breadth,
    fetch_fx,
    fetch_prices,
    fx_rates,
    indicators,
    link_snapshot,
    link_to_us,
    load_markets,
    load_replay,
    local_view,
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


# ---------------------------------------------------------------- local currency
def _mk(id_, fx):
    return Market(id=id_, ticker=id_, region="europe", tracks="", benchmark="", name={"fr": id_, "en": id_}, fx=fx)


def test_markets_file_has_fx(world_settings):
    markets = load_markets(world_settings)
    by = {m.id: m for m in markets}
    assert by["USA"].fx is None and by["SAU"].fx == {"peg": 3.75}
    assert all(m.fx["quote"] in ("per_usd", "usd_per") for m in markets if m.fx and "series" in m.fx)
    # The five euro markets share one series; the ETF list and tickers are untouched.
    assert {by[i].fx["series"] for i in ["FRA", "DEU", "ITA", "ESP", "NLD"]} == {"DEXUSEU"}
    assert len(markets) == 20


def test_local_return_is_usd_return_when_fx_is_flat():
    idx = pd.bdate_range("2026-01-05", periods=60)
    prices = pd.DataFrame({"AAA": np.linspace(100, 130, 60), "BBB": np.linspace(50, 40, 60)}, index=idx)
    markets = [_mk("AAA", {"series": "X", "quote": "per_usd"}), _mk("BBB", None)]
    flat = pd.DataFrame({"AAA": 1.3}, index=idx)
    rates = fx_rates(flat, markets, idx, 2)
    for horizon in ["1D", "1W", "1M"]:
        lv = local_view(prices, rates, markets, idx[-1], horizon, 21)
        for i in ("AAA", "BBB"):
            assert lv.loc[i, "return_local"] == pytest.approx(period_return(prices[i], idx[-1], horizon))
            assert lv.loc[i, "currency"] == pytest.approx(0.0, abs=1e-12)


def test_local_return_maths_and_currency_split():
    idx = pd.bdate_range("2026-01-05", periods=30)
    usd = pd.Series(100.0, index=idx)
    usd.iloc[-1] = 110.0
    per_usd = pd.Series(2.0, index=idx)
    per_usd.iloc[-1] = 2.2  # the local currency lost 10% of its dollar value
    markets = [_mk("AAA", {"series": "X"})]
    rates = fx_rates(pd.DataFrame({"AAA": per_usd}), markets, idx, 2)
    lv = local_view(pd.DataFrame({"AAA": usd}), rates, markets, idx[-1], "1D", 21)
    assert lv.loc["AAA", "return_local"] == pytest.approx(110 * 2.2 / (100 * 2.0) - 1)  # +21%
    assert lv.loc["AAA", "currency"] == pytest.approx(0.10 - 0.21)  # USD return minus local return, exactly
    assert lv.loc["AAA", "fx_status"] == "ok"


def test_fx_is_never_carried_past_its_last_published_date():
    idx = pd.bdate_range("2026-01-05", periods=40)
    raw = pd.Series(1.1, index=idx[:30])  # published through idx[29]
    markets = [_mk("AAA", {"series": "X"})]
    rates = fx_rates(pd.DataFrame({"AAA": raw}), markets, idx, 2)
    assert rates["AAA"].iloc[:30].notna().all() and rates["AAA"].iloc[30:].isna().all()
    prices = pd.DataFrame({"AAA": np.linspace(100, 120, 40)}, index=idx)
    lv = local_view(prices, rates, markets, idx[-1], "1W", 21)
    assert np.isnan(lv.loc["AAA", "return_local"]) and lv.loc["AAA", "fx_status"] == "pending"
    assert np.isnan(lv.loc["AAA", "vol_local"])
    # Up to the last published date the local figures exist again.
    assert local_view(prices, rates, markets, idx[29], "1W", 21).loc["AAA", "fx_status"] == "ok"


def test_fx_holiday_gap_is_filled_briefly_but_not_longer():
    idx = pd.bdate_range("2026-01-05", periods=30)
    raw = pd.Series(np.arange(30.0) + 1, index=idx)
    raw = raw.drop(idx[[10, 20, 21, 22]])  # one day missing, then three in a row
    rates = fx_rates(pd.DataFrame({"AAA": raw}), [_mk("AAA", {"series": "X"})], idx, 2)["AAA"]
    assert rates.iloc[10] == raw.loc[idx[9]]  # a Fed holiday that is no NYSE holiday: carried one day
    assert rates.iloc[20] == raw.loc[idx[19]] and rates.iloc[21] == raw.loc[idx[19]] and np.isnan(rates.iloc[22])


def test_pegged_and_usd_markets_have_no_currency_effect():
    idx = pd.bdate_range("2026-01-05", periods=30)
    prices = pd.DataFrame({"SAU": np.linspace(10, 12, 30), "USA": np.linspace(10, 11, 30)}, index=idx)
    markets = [_mk("SAU", {"peg": 3.75}), _mk("USA", None)]
    rates = fx_rates(pd.DataFrame(), markets, idx, 2)
    lv = local_view(prices, rates, markets, idx[-1], "1W", 21)
    assert (lv["currency"].abs() < 1e-12).all() and (lv["fx_status"] == "usd").all()
    assert lv.loc["SAU", "vol_local"] == pytest.approx(np.log(prices["SAU"]).diff().rolling(21).std().iloc[-1] * np.sqrt(252))


def test_fred_fx_inverts_usd_per_series_and_reports_failures(world_settings, monkeypatch, tmp_path):
    from pfe_drai.data import fred

    calls = []

    def fake(series_id, key, start, end, vintage=None):
        calls.append(series_id)
        if series_id == "DEXBZUS":
            raise RuntimeError("400 bad series")
        value = {"DEXUSEU": 1.25, "DEXUSUK": 1.6}.get(series_id, 100.0)
        return pd.Series(value, index=pd.bdate_range("2026-01-05", periods=5))

    monkeypatch.setattr(fred, "fetch_fred", fake)
    monkeypatch.setenv("FRED_API_KEY", "test")
    settings = load_settings(overrides={"data": {"cache_dir": str(tmp_path), "end": "2026-01-09"}})
    fx, errors = fetch_fx(settings, "fred")
    assert calls.count("DEXUSEU") == 1  # one download for the five euro markets
    assert fx["FRA"].iloc[0] == pytest.approx(1 / 1.25) and fx["GBR"].iloc[0] == pytest.approx(1 / 1.6)
    assert fx["JPN"].iloc[0] == 100.0
    assert list(errors) == ["BRA"] and "DEXBZUS" in errors["BRA"] and "BRA" not in fx
    assert not (tmp_path / "world").exists()  # an incomplete download is not cached


def test_fred_fx_needs_a_key(world_settings, monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    settings = load_settings(overrides={"data": {"cache_dir": str(tmp_path), "end": "2026-01-09"}})
    with pytest.raises(RuntimeError, match="FRED_API_KEY"):
        fetch_fx(settings, "fred")


def test_synthetic_fx_and_local_view(world, world_settings):
    prices, _, _ = world
    markets = load_markets(world_settings)
    fx, errors = fetch_fx(world_settings, "synthetic")
    assert errors == {} and set(fx.columns) == {m.id for m in markets if m.fx and "series" in m.fx}
    assert (fx["FRA"] == fx["DEU"]).all()  # one euro
    rates = fx_rates(fx, markets, prices.index, world_settings["world"]["fx_fill_days"])
    lv = local_view(prices, rates, markets, "2020-03-16", "1M", 21)
    assert len(lv) == 20 and lv["return_local"].notna().all()
    usd = snapshot(prices, indicators(prices, world_settings), markets, "2020-03-16", "1M")["return"]
    assert (lv["currency"] - (usd - lv["return_local"])).abs().max() < 1e-12


# ---------------------------------------------------------------- link to the US
def _link_settings(windows=(20,), return_days=1, stress_window=60, floor=5):
    link = {"return_days": return_days, "windows": list(windows), "min_share": 1.0, "min_markets": 1}
    return {"world": {"link": {**link, "stress_window": stress_window, "min_stress_days": floor}}}


def _pair(n=120, seed=1):
    idx = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(seed)
    us = rng.normal(0, 0.01, n)
    x = 0.8 * us + rng.normal(0, 0.006, n)
    prices = pd.DataFrame({"USA": 100 * np.exp(np.cumsum(us)), "XXX": 50 * np.exp(np.cumsum(x))}, index=idx)
    state = pd.DataFrame({"USA": np.where(np.arange(n) % 4 == 0, 2.0, 0.0), "XXX": 0.0}, index=idx)
    return prices, {"state": state}


def test_rolling_beta_and_correlation_match_a_hand_computation():
    prices, ind = _pair()
    stats = link_to_us(prices, ind, _link_settings())
    r = np.log(prices).diff()
    last = r.iloc[-20:]
    assert stats.corr[20]["XXX"].iloc[-1] == pytest.approx(np.corrcoef(last["XXX"], last["USA"])[0, 1])
    assert stats.beta[20]["XXX"].iloc[-1] == pytest.approx(np.cov(last["XXX"], last["USA"])[0, 1] / last["USA"].var())
    assert stats.corr[20]["USA"].iloc[-1] == pytest.approx(1.0) and stats.beta[20]["USA"].iloc[-1] == pytest.approx(1.0)
    assert stats.corr[20]["XXX"].iloc[:19].isna().all()  # a full window first
    # 1-day lead/lag: today's market against yesterday's US, and yesterday's market against today's US.
    win = r.iloc[-20:]
    assert stats.follows[20]["XXX"].iloc[-1] == pytest.approx(np.corrcoef(win["XXX"], r["USA"].shift(1).iloc[-20:])[0, 1])
    assert stats.leads[20]["XXX"].iloc[-1] == pytest.approx(np.corrcoef(r["XXX"].shift(1).iloc[-20:], win["USA"])[0, 1])
    assert stats.avg_corr[20].iloc[-1] == pytest.approx(stats.corr[20]["XXX"].iloc[-1])  # the US is not in its own average


def test_headline_uses_5_day_returns():
    prices, ind = _pair()
    stats = link_to_us(prices, ind, _link_settings(return_days=5))
    r5 = np.log(prices).diff(5).iloc[-20:]
    assert stats.corr[20]["XXX"].iloc[-1] == pytest.approx(np.corrcoef(r5["XXX"], r5["USA"])[0, 1])


def test_stress_and_calm_correlations_use_only_those_days():
    prices, ind = _pair(n=200)
    stats = link_to_us(prices, ind, _link_settings(stress_window=100, floor=5))
    r = np.log(prices).diff().iloc[-100:]
    flag = ind["state"]["USA"].iloc[-100:]
    on, off = r[flag == 2], r[flag == 0]
    assert stats.corr_stress["XXX"].iloc[-1] == pytest.approx(np.corrcoef(on["XXX"], on["USA"])[0, 1])
    assert stats.corr_calm["XXX"].iloc[-1] == pytest.approx(np.corrcoef(off["XXX"], off["USA"])[0, 1])
    assert stats.stress_days["XXX"].iloc[-1] == (flag == 2).sum()
    # Too few US stress days in the window: no number.
    sparse = {"state": ind["state"].assign(USA=np.where(np.arange(200) == 150, 2.0, 0.0))}
    assert np.isnan(link_to_us(prices, sparse, _link_settings(stress_window=100, floor=5)).corr_stress["XXX"].iloc[-1])


def test_link_has_no_look_ahead(world, world_settings):
    prices, ind, _ = world
    cut = "2015-06-30"
    full = link_to_us(prices, ind, world_settings)
    early = link_to_us(prices.loc[:cut], indicators(prices.loc[:cut], world_settings), world_settings)
    for w in world_settings["world"]["link"]["windows"]:
        for name in ["corr", "beta", "corr_1d", "follows", "leads", "avg_corr"]:
            pd.testing.assert_frame_equal(pd.DataFrame(getattr(early, name)[w]), pd.DataFrame(getattr(full, name)[w]).loc[:cut])
    for name in ["corr_stress", "corr_calm", "stress_days"]:
        pd.testing.assert_frame_equal(getattr(early, name), getattr(full, name).loc[:cut])


def test_link_on_synthetic_markets(world, world_settings):
    prices, ind, _ = world
    stats = link_to_us(prices, ind, world_settings)
    markets = load_markets(world_settings)
    snap = link_snapshot(stats, markets, prices, "2020-03-16", 252, world_settings["world"]["stale_days"])
    assert len(snap) == 20
    assert snap.loc["USA", "corr"] == pytest.approx(1.0) and np.isnan(snap.loc["USA", "follows"])
    assert (snap["corr"].dropna().abs() <= 1).all()
    # The simulated markets follow the simulated US (their own beta), the Saudi one least.
    assert snap.loc["CAN", "corr"] > snap.loc["SAU", "corr"]
    # Correlations rise in the scripted crisis, on average.
    avg = stats.avg_corr[63]
    assert avg.loc["2020-03-01":"2020-04-15"].max() > avg.loc["2019-06-01":"2019-12-31"].mean()
    gone = prices.copy()
    gone.loc["2020-01-01":, "FRA"] = np.nan
    stale = link_snapshot(link_to_us(gone, ind, world_settings), markets, gone, "2020-03-16", 63, 5)
    assert stale.loc["FRA"].isna().all()


def test_cli_world_local_and_link(capsys):
    main(["world", "--date", "2020-03-16", "--horizon", "1M", "--currency", "local", "--link", "--window", "63"])
    out = capsys.readouterr().out
    assert "Local currency" in out and "vol local" in out and "Link to the US" in out
    assert "Average correlation of the other markets" in out and "Saudi Arabia" in out
    with pytest.raises(SystemExit):
        main(["world", "--link", "--window", "10"])
