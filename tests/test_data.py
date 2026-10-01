import httpx
import pandas as pd
import pytest

from pfe_drai.data import CATALOG, available_providers, get_provider
from pfe_drai.data.fred import fetch_vintages, first_releases


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
    if "realtime_start" in params:  # ALFRED: first release, then a revision
        rows = [
            {"date": "2019-12-01", "value": "100.0", "realtime_start": "2020-01-15"},
            {"date": "2019-12-01", "value": "101.0", "realtime_start": "2020-02-14"},
        ]
        return _Response({"observations": rows, "count": 2, "offset": 0})
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
    # Revised series arrive as first releases, dated on their release day.
    assert provider.release_dated == {"claims", "indpro", "cpi"}
    assert data["indpro"].to_dict() == {pd.Timestamp("2020-01-15"): 100.0}


def test_fred_without_point_in_time_reads_revised_values(monkeypatch, settings):
    monkeypatch.setattr(httpx, "get", _fake_get)
    monkeypatch.setenv("FRED_API_KEY", "fred-key")
    data_cfg = {**settings["data"], "provider": "fred", "fred_fallback": "synthetic", "point_in_time": False}
    provider = get_provider({**settings, "data": data_cfg})
    data = provider.fetch(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-10"))
    assert provider.release_dated == set()
    assert data["indpro"].tolist() == [1.5]


def _vintages(rows):
    frame = pd.DataFrame(rows, columns=["date", "value", "realtime_start"])
    frame["date"] = pd.to_datetime(frame["date"])
    frame["realtime_start"] = pd.to_datetime(frame["realtime_start"])
    return frame


def test_first_releases_keep_the_value_known_on_release_day():
    vintages = _vintages(
        [
            ("2020-01-01", 100.0, "2020-02-14"),
            ("2020-01-01", 99.0, "2020-03-17"),  # later revision: ignored
            ("2020-02-01", 101.0, "2020-03-17"),
            ("2020-02-01", 98.0, "2021-03-26"),  # annual revision: ignored
        ]
    )
    released = first_releases(vintages, "monthly")
    assert released.to_dict() == {pd.Timestamp("2020-02-14"): 100.0, pd.Timestamp("2020-03-17"): 101.0}


def test_first_releases_before_the_archive_use_the_publication_lag():
    # The archive starts in 2020-06: older months all show it as their release date.
    vintages = _vintages(
        [
            ("2020-03-01", 97.0, "2020-06-16"),
            ("2020-04-01", 98.0, "2020-06-16"),  # close to its usual date: kept late, then superseded
            ("2020-05-01", 99.0, "2020-06-16"),  # genuinely released that day
            ("2020-06-01", 100.0, "2020-07-15"),
        ]
    )
    released = first_releases(vintages, "monthly", fallback_lag_days=17)
    assert released.to_dict() == {
        pd.Timestamp("2020-04-17"): 97.0,
        pd.Timestamp("2020-06-16"): 99.0,
        pd.Timestamp("2020-07-15"): 100.0,
    }


def test_first_releases_published_together_keep_the_newest_period():
    # After a shutdown, two months come out on the same day.
    vintages = _vintages(
        [
            ("2025-08-01", 100.0, "2025-09-16"),
            ("2025-09-01", 101.0, "2025-12-03"),
            ("2025-10-01", 102.0, "2025-12-03"),
        ]
    )
    released = first_releases(vintages, "monthly")
    assert released.to_dict() == {pd.Timestamp("2025-09-16"): 100.0, pd.Timestamp("2025-12-03"): 102.0}


def test_fetch_vintages_reads_every_page(monkeypatch):
    calls = []

    def paged_get(url, params=None, timeout=None):
        calls.append(params["offset"])
        row = {"date": f"2020-0{params['offset'] + 1}-01", "value": "1.0", "realtime_start": "2020-12-01"}
        return _Response({"observations": [row], "count": 3, "offset": params["offset"]})

    monkeypatch.setattr(httpx, "get", paged_get)
    frame = fetch_vintages("INDPRO", "fred-key", "2020-01-01", "2020-12-31")
    assert calls == [0, 1, 2]
    assert len(frame) == 3


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
