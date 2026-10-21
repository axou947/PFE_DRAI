import datetime as dt
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_world_date_outside_the_data_is_clamped():
    # A map date kept from an earlier run (e.g. today, before the source's last close) must not crash the app.
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.session_state["world_date"] = dt.date(2099, 1, 1)
    at.run()
    assert not at.exception
    assert at.session_state["world_date"] < dt.date(2099, 1, 1)


def test_world_local_currency_and_link_views():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception

    def control(label):
        return next(c for c in at.segmented_control if c.label == label)

    control("View").set_value("returns").run()
    control("Currency").set_value("local").run()
    assert not at.exception
    assert any("H.10" in c.value for c in at.caption)  # the FX note and its caveat are shown
    control("View").set_value("link").run()
    assert not at.exception
    control("Colour by").set_value("beta").run()
    control("Window").set_value(63).run()
    assert not at.exception
    assert any("not a cause" in c.value for c in at.caption)


def test_dark_mode_switch_restyles_the_charts_and_both_languages_have_the_label():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    toggle = next(c for c in at.sidebar.toggle if c.key == "dark_mode")
    assert toggle.value is False
    toggle.set_value(True).run()
    assert not at.exception
    assert at.session_state["dark_mode"] is True
    assert any("background:#0d0d0d" in m.value for m in at.markdown)  # the dark page CSS is injected
    toggle.set_value(False).run()
    assert not at.exception
    assert not any("background:#0d0d0d" in m.value for m in at.markdown)


def test_dashboard_explains_the_regime_in_both_languages():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    assert not at.exception
    assert any(h.value == "Pourquoi ce régime" for h in at.subheader)
    assert any(m.value.startswith("La règle donne") for m in at.markdown)
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception
    assert {"Why this regime", "What would flip the rule", "What drives the stress alarm"} <= {h.value for h in at.subheader}
    assert any("not a cause" in c.value or "does not identify a cause" in c.value for c in at.caption)


def test_global_board_tab_reads_the_published_record():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    assert not at.exception
    assert {"Vue mondiale", "Tableau des challengers"} <= {h.value for h in at.subheader}
    assert any(m.label == "États-Unis" for m in at.metric)


def test_dashboard_shows_the_outlook_from_history_with_its_caveat():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    assert not at.exception
    assert any(h.value == "Outlook from history" for h in at.subheader)
    assert any("not a forecast and not advice" in c.value for c in at.caption)


def test_scenarios_with_your_own_portfolio_in_memory():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    source = next(c for c in at.segmented_control if c.key == "portfolio_source")
    source.set_value("own").run()
    assert not at.exception
    assert any("Paste or upload your weights" in i.value for i in at.info)
    assert any("nothing is saved on disk" in c.value for c in at.caption)
    box = next(a for a in at.text_area if a.key == "portfolio_text")
    box.input("asset,weight\nbitcoin,100\n").run()
    assert not at.exception
    assert any('unknown asset class "bitcoin"' in e.value for e in at.error)
    box.input("holding,asset_class,weight\nMSCI World ETF,equity_world,60\nBund,gov_bonds,40\n").run()
    assert not at.exception
    assert not at.error
    assert any(h.value == "Impact of the selected scenarios on your portfolio" for h in at.subheader)
    assert any("2 holdings read" in c.value for c in at.caption)


def test_single_stock_on_simulated_data_says_it_needs_real_prices():
    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    next(c for c in at.segmented_control if c.key == "portfolio_source").set_value("own").run()
    next(a for a in at.text_area if a.key == "portfolio_text").input(
        "holding,asset_class,ticker,weight\nApple,stock,AAPL,20\nWorld,equity_world,,80\n"
    ).run()
    assert not at.exception
    assert any("Single stocks need real prices" in e.value for e in at.error)
    assert any("Apple" in str(df.value) for df in at.dataframe)  # the holdings read are still shown


def test_single_stock_impact_with_prices(monkeypatch):
    # Real prices need Tiingo: stand in a price feed (SPY-like for 1993 on, a young stock from 2015).
    import numpy as np
    import pandas as pd

    import pfe_drai.scenarios.stocks as stocks

    idx = pd.bdate_range("1993-01-29", "2026-10-02")
    spy = pd.Series(100 * np.cumprod(1 + np.random.default_rng(3).normal(0.0003, 0.01, len(idx))), index=idx)
    feed = {"SPY": spy, "OLDCO": spy * 2, "NEWCO": spy.loc["2015":] * 3}
    monkeypatch.setattr(stocks, "tiingo_fetcher", lambda settings: lambda tk: feed[tk])

    at = AppTest.from_file(str(APP), default_timeout=900)
    at.run()
    at.sidebar.radio[0].set_value("English").run()
    next(c for c in at.segmented_control if c.key == "portfolio_source").set_value("own").run()
    next(a for a in at.text_area if a.key == "portfolio_text").input(
        "holding,asset_class,ticker,weight\nOld Co,stock,OLDCO,20\nNew Co,stock,NEWCO,20\nWorld,equity_world,,60\n"
    ).run()
    assert not at.exception
    assert not at.error
    assert any(h.value == "Impact of the selected scenarios on your portfolio" for h in at.subheader)
    assert any("estimated from beta" in c.value for c in at.caption)
    assert any("NEWCO" in str(df.value) for df in at.dataframe)
