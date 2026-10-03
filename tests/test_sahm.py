"""Sahm rule test (docs/SAHM_HY.md): the gap, the step-1 holdout and its rule. The published model (v2.2) is unchanged."""

import numpy as np
import pandas as pd

from pfe_drai.cli import main
from pfe_drai.config import _deep_merge, load_settings
from pfe_drai.data import fred
from pfe_drai.data.synthetic import simulate
from pfe_drai.features.build import FEATURES, sahm_gap
from pfe_drai.publish.snapshot import config_fingerprint
from pfe_drai.validation.slowdown import sahm_holdout


def test_the_test_does_not_change_the_published_fingerprint():
    # US settings fingerprint on main (test_euro.py): the `sahm` block is outside it.
    assert config_fingerprint(load_settings()) == "7d25ca3445b05e50899a79e8bc0639edcead03fb2f8c6ed6a4b9ae379a59fd0a"


def test_the_published_model_never_reads_the_sahm_gap(pipeline):
    assert "unemployment_gap" not in FEATURES
    assert list(pipeline.features.columns) == list(FEATURES)


def test_sahm_gap_is_zero_at_a_low_and_reads_a_rise_as_weaker_growth():
    days = pd.bdate_range("2000-01-03", periods=600)
    flat = pd.Series(4.0, index=days)
    assert sahm_gap(flat).dropna().abs().max() == 0
    rising = flat.copy()
    rising.iloc[400:] = 5.0  # unemployment up a point
    gap = sahm_gap(rising)
    assert gap.iloc[399] == 0
    assert gap.iloc[-1] == -1.0  # the 3-month average is a point above its 12-month low
    assert gap.loc[: days[450]].equals(sahm_gap(rising.loc[: days[450]]))  # past data only


def test_simulated_unemployment_follows_the_regime():
    data, truth = simulate("2000-01-03", "2026-06-30", 42)
    by_regime = data["unrate"].groupby(truth.reindex(data["unrate"].index)).mean()
    assert by_regime["slowdown"] > by_regime["expansion"] > by_regime["overheating"]


def test_holdout_compares_v22_with_the_sahm_gap(settings):
    s = _deep_merge(settings, {"validation": {"holdout": {"start": "2000-01-03", "end": "2009-04-02"}}})
    s["validation"]["slowdown"]["holdout"]["evaluate_from"] = "2003-01-02"
    res = sahm_holdout(s)
    assert list(res["rows"]["candidate"]) == ["v2.2 (published)", "v2.2 + Sahm gap"]
    assert res["rows"]["days"].min() > 1000 and res["rows"]["balanced_accuracy"].notna().all()
    gain = res["rows"]["balanced_accuracy"].iloc[1] - res["rows"]["balanced_accuracy"].iloc[0]
    assert res["passed"] == (gain >= 0.02 and res["rows"]["spells_per_year"].iloc[1] <= 2.0)


def test_fred_reads_the_unemployment_rate_as_first_releases(monkeypatch, settings):
    calls = []

    def vintages(series_id, key, start, end):
        calls.append(series_id)
        return pd.DataFrame(
            {"date": pd.to_datetime(["2000-01-01"]), "value": [4.0], "realtime_start": pd.to_datetime(["2000-02-04"])}
        )

    monkeypatch.setenv(settings["data"]["fred_api_key_env"], "test")
    monkeypatch.setattr(fred, "fetch_vintages", vintages)
    provider = fred.FredProvider(settings)
    data = provider.fetch_subset(["unrate"], pd.Timestamp("2000-01-01"), pd.Timestamp("2000-03-01"))
    assert calls == ["UNRATE"] and "unrate" in provider.release_dated
    assert data["unrate"].index[0] == pd.Timestamp("2000-02-04")


def test_cli_sahm_runs_on_simulated_data(capsys):
    main(["sahm"])
    out = capsys.readouterr().out
    assert "SIMULATED" in out and "v2.2 + Sahm gap" in out and "Step 1" in out
    assert np.isfinite(float(out.split("gain ")[1].split(")")[0]))
