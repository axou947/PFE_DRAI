import httpx
import pandas as pd
import pytest

from pfe_drai.data import CATALOG, available_providers, get_provider


def test_providers_registered():
    assert {"synthetic", "csv", "fred", "tiingo", "yahoo"} <= set(available_providers())


def test_synthetic_returns_every_series(settings):
    provider = get_provider(settings)
    data = provider.fetch(pd.Timestamp("2010-01-01"), pd.Timestamp("2012-12-31"))
    provider.check(data)
    assert set(CATALOG) <= set(data)
    assert provider.truth().isin(settings["regimes"]["order"]).all()


def test_synthetic_is_reproducible(settings):
    a = get_provider(settings).fetch(pd.Timestamp("2010-01-01"), pd.Timestamp("2010-12-31"))
    b = get_provider(settings).fetch(pd.Timestamp("2010-01-01"), pd.Timestamp("2010-12-31"))
    pd.testing.assert_series_equal(a["equity"], b["equity"])


def test_csv_provider_reads_files(tmp_path, settings):
    source = get_provider(settings).fetch(pd.Timestamp("2010-01-01"), pd.Timestamp("2010-06-30"))
    for name, series in source.items():
        series.rename("value").rename_axis("date").to_csv(tmp_path / f"{name}.csv")
    csv = get_provider({**settings, "data": {**settings["data"], "provider": "csv", "csv_dir": str(tmp_path)}})
    data = csv.fetch(pd.Timestamp("2010-01-01"), pd.Timestamp("2010-06-30"))
    assert data["vix"].iloc[-1] == pytest.approx(source["vix"].iloc[-1])


def test_unknown_provider(settings):
    with pytest.raises(ValueError):
        get_provider({**settings, "data": {**settings["data"], "provider": "nope"}})


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _fake_get(url, params=None, headers=None, timeout=None):
    """Answers like FRED or Tiingo, without network access."""
    dates = ["2020-01-02", "2020-01-03"]
    if "tiingo" in url:
        assert headers["Authorization"] == "Token tiingo-key"
        return _Response([{"date": f"{d}T00:00:00.000Z", "close": 100.0, "adjClose": 99.0 + i} for i, d in enumerate(dates)])
    assert params["api_key"] == "fred-key"
    return _Response({"observations": [{"date": dates[0], "value": "1.5"}, {"date": dates[1], "value": "."}]})


def test_fred_with_tiingo_fallback_returns_every_series(monkeypatch, settings):
    monkeypatch.setattr(httpx, "get", _fake_get)
    monkeypatch.setenv("FRED_API_KEY", "fred-key")
    monkeypatch.setenv("TIINGO_API_KEY", "tiingo-key")
    provider = get_provider({**settings, "data": {**settings["data"], "provider": "fred", "fred_fallback": "tiingo"}})
    data = provider.fetch(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))
    provider.check(data)
    assert data["hy_bond"].tolist() == [99.0, 100.0]  # adjusted close
    assert data["us10y"].tolist() == [1.5]  # FRED "." means missing
    assert provider.is_live


def test_fred_with_synthetic_fallback_is_not_live(monkeypatch, settings):
    monkeypatch.setattr(httpx, "get", _fake_get)
    monkeypatch.setenv("FRED_API_KEY", "fred-key")
    provider = get_provider({**settings, "data": {**settings["data"], "provider": "fred", "fred_fallback": "synthetic"}})
    provider.fetch(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))
    assert not provider.is_live


def test_tiingo_needs_a_key(monkeypatch, settings):
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    provider = get_provider({**settings, "data": {**settings["data"], "provider": "tiingo"}})
    with pytest.raises(RuntimeError, match="TIINGO_API_KEY"):
        provider.fetch(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))
