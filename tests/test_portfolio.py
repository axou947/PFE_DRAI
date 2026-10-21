import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from pfe_drai.reporting import build_note, to_markdown
from pfe_drai.scenarios import fund_impact, load_library
from pfe_drai.scenarios.portfolio import PortfolioError, holdings_impact, messages, parse_portfolio, template
from pfe_drai.scenarios.stocks import StockDataError, beta, stock_moves, tiingo_fetcher, window_return, with_stocks


@pytest.fixture(scope="module")
def library(settings):
    return load_library(settings)


def codes(text, assets):
    with pytest.raises(PortfolioError) as err:
        parse_portfolio(text, assets)
    return [e["code"] for e in err.value.errors]


def test_english_csv_in_percent(library):
    assets, _ = library
    p = parse_portfolio("holding,asset_class,weight\nMSCI World,equity_world,60\nBund,gov_bonds,30\nGold ETC,gold,10\n", assets)
    assert p.unit == "percent"
    assert p.weights["equity_world"] == pytest.approx(0.6) and p.weights["gold"] == pytest.approx(0.1)
    assert set(p.weights) == set(assets) and sum(p.weights.values()) == pytest.approx(1)
    assert [h.name for h in p.holdings] == ["MSCI World", "Bund", "Gold ETC"]


def test_french_excel_export(library):
    # Excel in French: semicolons, decimal commas, "%" signs, accented labels, cp1252 bytes.
    assets, _ = library
    text = "Ligne;Classe d'actif;Poids (%)\nAmundi;Actions monde;55,5 %\nOr physique;Or;4,5\nLivret;Liquidités;40\n"
    p = parse_portfolio(text.encode("cp1252"), assets)
    assert p.weights["equity_world"] == pytest.approx(0.555)
    assert p.weights["gold"] == pytest.approx(0.045) and p.weights["cash"] == pytest.approx(0.40)


def test_fractions_no_header_and_same_class_rows_add_up(library):
    assets, _ = library
    p = parse_portfolio("equity_world,0.3\nworld equities,0.2\nhigh yield,0.5\n", assets)
    assert p.unit == "fraction"
    assert p.weights["equity_world"] == pytest.approx(0.5) and p.weights["hy_credit"] == pytest.approx(0.5)
    assert len(p.holdings) == 2 + 1


def test_every_class_and_label_is_accepted(library):
    assets, _ = library
    from pfe_drai.i18n import t

    for lang in ("fr", "en"):
        rows = "\n".join(f"{t(f'asset.{a}', lang)};{100 / len(assets)}" for a in assets)
        p = parse_portfolio(rows, assets)
        assert all(p.weights[a] == pytest.approx(1 / len(assets)) for a in assets)
    assert parse_portfolio(template(assets, "fr"), assets).weights["equity_world"] == pytest.approx(0.4)
    assert parse_portfolio(template(assets, "en"), assets).weights["equity_world"] == pytest.approx(0.4)


def test_errors_are_all_reported_with_their_line(library):
    assets, _ = library
    with pytest.raises(PortfolioError) as err:
        parse_portfolio("asset,weight\nbitcoin,50\nequity_world,abc\ngold,-3\n", assets)
    found = [(e["code"], e.get("line")) for e in err.value.errors]
    assert ("unknown_asset", 2) in found and ("bad_weight", 3) in found and ("negative_weight", 4) in found
    assert ("accepted", None) in found
    en, fr = messages(err.value.errors, "en"), messages(err.value.errors, "fr")
    assert en[0] == 'Line 2: unknown asset class "bitcoin".'
    assert fr[0] == "Ligne 2 : classe d'actif inconnue « bitcoin »."


def test_sum_rules(library):
    assets, _ = library
    assert codes("equity_world,60\ngold,30\n", assets) == ["bad_sum"]
    assert codes("", assets) == ["empty"]
    assert codes("asset,weight\n", assets) == ["empty"]
    assert codes("a,b\nx,y\n", assets) == ["no_asset_column"]
    assert "decimal_comma" in codes("gold,2,5\nequity_world,97,5\n", assets)
    # A rounding gap within half a point is spread pro rata, and said.
    p = parse_portfolio("gold,50\nequity_europe,50.2\n", assets)
    assert sum(p.weights.values()) == pytest.approx(1)
    assert [w["code"] for w in p.warnings] == ["rescaled"]
    assert codes("gold;" + "\n".join(["equity_world;0"] * 600), assets) == ["too_many_rows"]


def test_impact_matches_the_fund_formula_and_splits_by_holding(library):
    assets, scenarios = library
    p = parse_portfolio("MSCI World,equity_world,40\nS&P 500 ETF,equity_world,20\nBund,gov_bonds,40\n", assets)
    sc = next(s for s in scenarios if s.id == "gfc_2008")
    total = fund_impact(p.weights, sc)["total"]
    assert total == pytest.approx(0.6 * sc.shocks["equity_world"] + 0.4 * sc.shocks["gov_bonds"])
    per = holdings_impact(p, scenarios, ["gfc_2008"])
    assert per["gfc_2008"].sum() == pytest.approx(total)
    assert per.loc["S&P 500 ETF", "gfc_2008"] == pytest.approx(0.2 * sc.shocks["equity_world"])


def test_note_names_your_portfolio(pipeline, library):
    assets, _ = library
    fund = parse_portfolio("equity_world,70\ngov_bonds,30\n", assets).fund()
    for lang, words in (("fr", "Votre propre portefeuille"), ("en", "Your own portfolio")):
        note = build_note(pipeline, lang, "kmeans", fund=fund)
        assert note["fund"].startswith(words)
        assert words in to_markdown(note)


def test_api_portfolio(pipeline, monkeypatch):
    monkeypatch.setattr(api_main, "pipeline", lambda: pipeline)
    client = TestClient(api_main.app)
    body = client.post(
        "/scenarios/portfolio", params={"model": "kmeans", "lang": "en"}, json={"csv": "equity_world,60\ngov_bonds,40\n"}
    ).json()
    _, scenarios = load_library(pipeline.settings)
    assert len(body["scenarios"]) == len(scenarios)
    assert body["weights"]["equity_world"] == pytest.approx(0.6)
    gfc = next(s for s in body["scenarios"] if s["id"] == "gfc_2008")
    assert gfc["impact"] == pytest.approx(sum(gfc["by_holding"]))
    bad = client.post("/scenarios/portfolio", params={"lang": "fr"}, json={"csv": "bitcoin,100\n"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["messages"][0] == "Ligne 1 : classe d'actif inconnue « bitcoin »."


# ---------------------------------------------------------------- single stocks
def _prices(start, daily, days=None, end="2026-10-02", seed=0):
    idx = pd.bdate_range(start, end)
    noise = np.random.default_rng(seed).normal(0, 0.01, len(idx)) if days is None else days(idx)
    return pd.Series(100 * np.cumprod(1 + daily + noise), index=idx)


def test_stock_rows_are_read_with_their_ticker(library):
    assets, _ = library
    p = parse_portfolio(
        "holding,asset_class,ticker,weight\nApple,stock,aapl,10\nBerkshire,action,BRK-B,10\nWorld,equity_world,,80\n", assets
    )
    assert p.tickers == ["AAPL", "BRK-B"]
    assert p.weights["stock:AAPL"] == pytest.approx(0.1) and p.weights["equity_world"] == pytest.approx(0.8)
    assert [h.ticker for h in p.holdings] == ["AAPL", "BRK-B", None]
    # Headerless: a 4th column is the ticker; or the holding name when written as a ticker.
    assert parse_portfolio("Apple;stock;AAPL;50\nWorld;equity_world;;50\n", assets).tickers == ["AAPL"]
    assert parse_portfolio("MSFT,stock,100\n", assets).tickers == ["MSFT"]
    assert codes("Apple,stock,100\n", assets) == ["missing_ticker"]
    assert codes("holding,asset_class,ticker,weight\nX,stock,AA PL!,100\n", assets) == ["bad_ticker"]


def test_actual_move_when_listed_and_beta_estimate_otherwise(library):
    _, scenarios = library
    spy = _prices("1993-01-29", 0.0003, seed=1)
    old = spy * 1.0  # an old stock: identical to SPY, listed since 1993
    young = _prices("2015-01-02", 0.0, days=lambda idx: 2 * spy.pct_change().reindex(idx).fillna(0).values)  # beta 2
    feed = {"SPY": spy, "OLD": old, "YOUNG": young}

    def fetch(tk):
        if tk not in feed:
            raise LookupError(tk)
        return feed[tk]

    moves = stock_moves(["OLD", "YOUNG"], scenarios, fetch)
    gfc = next(s for s in scenarios if s.id == "gfc_2008")
    spy_gfc = window_return(spy, gfc.start, gfc.end)
    assert moves["OLD"].sources["gfc_2008"] == "actual" and moves["OLD"].moves["gfc_2008"] == pytest.approx(spy_gfc)
    assert moves["YOUNG"].beta == pytest.approx(2, abs=1e-6)
    assert moves["YOUNG"].sources["gfc_2008"] == "estimated"
    assert moves["YOUNG"].moves["gfc_2008"] == pytest.approx(2 * spy_gfc)
    assert moves["YOUNG"].sources["covid_2020"] == "actual"

    with pytest.raises(StockDataError) as err:
        stock_moves(["NOPE", "TINY"], scenarios, lambda tk: {**feed, "TINY": spy.tail(30)}[tk] if tk != "NOPE" else fetch(tk))
    assert [e["code"] for e in err.value.errors] == ["unknown_ticker", "short_history"]
    assert messages(err.value.errors, "en")[0].startswith("Tiingo does not know the ticker NOPE")


def test_stock_impact_flows_into_tables_and_note(pipeline, library):
    assets, scenarios = library
    spy = _prices("1993-01-29", 0.0003, seed=2)
    p = parse_portfolio("holding,asset_class,ticker,weight\nIndex twin,stock,TWIN,40\nBund,gov_bonds,,60\n", assets)
    moves = stock_moves(p.tickers, scenarios, lambda tk: spy)
    augmented = with_stocks(scenarios, moves)
    gfc = next(s for s in augmented if s.id == "gfc_2008")
    total = fund_impact(p.weights, gfc)["total"]
    assert total == pytest.approx(0.4 * window_return(spy, gfc.start, gfc.end) + 0.6 * gfc.shocks["gov_bonds"])
    assert holdings_impact(p, augmented, ["gfc_2008"])["gfc_2008"].sum() == pytest.approx(total)
    note = build_note(pipeline, "en", "kmeans", fund=p.fund(), scenarios=augmented)
    assert any(a["name"] == "Stock TWIN" for a in note["impact_assets"])


def test_stocks_need_live_data_and_a_key(settings, monkeypatch):
    with pytest.raises(StockDataError) as err:
        tiingo_fetcher(settings)  # the test settings use simulated data
    assert err.value.errors == [{"code": "needs_live"}]
    live = {**settings, "data": {**settings["data"], "provider": "fred"}}
    monkeypatch.delenv(settings["data"]["tiingo_api_key_env"], raising=False)
    with pytest.raises(StockDataError) as err:
        tiingo_fetcher(live)
    assert err.value.errors[0]["code"] == "needs_key"
    assert beta(pd.Series([1.0, 2.0]), pd.Series([1.0, 2.0])) is None


def test_api_stock_portfolio_on_simulated_data_says_why(pipeline, monkeypatch):
    monkeypatch.setattr(api_main, "pipeline", lambda: pipeline)
    client = TestClient(api_main.app)
    bad = client.post("/scenarios/portfolio", params={"lang": "en"}, json={"csv": "AAPL,stock,100\n"})
    assert bad.status_code == 422
    assert bad.json()["detail"]["messages"][0].startswith("Single stocks need real prices")
