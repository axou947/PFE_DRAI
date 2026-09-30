import pandas as pd
import pytest

from pfe_drai.data import CATALOG, available_providers, get_provider


def test_providers_registered():
    assert {"synthetic", "csv", "fred", "yahoo"} <= set(available_providers())


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
