"""Regime outlook from history (pfe_drai/outlook.py, docs/OUTLOOK.md): base rates of the displayed path, read-only."""

import json

import pandas as pd

from pfe_drai.outlook import MIN_DAYS, outlook, raw_runs, sentences, spells
from pfe_drai.publish.snapshot import config_fingerprint


def _path(*runs):
    values = [r for r, n in runs for _ in range(n)]
    return pd.Series(values, index=pd.bdate_range("2020-01-01", periods=len(values)))


def test_blips_fold_into_the_spell_before_them():
    path = _path(("expansion", 30), ("stress", 2), ("expansion", 20), ("slowdown", 40), ("stress", 3))
    table = spells(path)
    assert list(table["regime"]) == ["expansion", "slowdown", "stress"]
    assert list(table["days"]) == [52, 40, 3]  # the two-day flicker stays inside expansion; the running run is never folded
    assert list(table["blips"]) == [1, 0, 0]
    assert list(table["next"]) == ["slowdown", "stress", None]
    assert list(table["complete"]) == [False, True, False]  # the first is cut by the history, the last still runs
    assert table["days"].sum() == len(path)


def test_a_chain_of_blips_keeps_the_regime_before_them():
    path = _path(("expansion", 10), ("stress", 2), ("slowdown", 3), ("expansion", 10))
    assert list(spells(path)["regime"]) == ["expansion"]
    assert len(raw_runs(path)) == 4


def test_counts_add_up_and_nothing_after_the_date_is_used(pipeline):
    path = pipeline.regimes("combined")
    for date in [None, "2020-03-20", "2012-06-01"]:
        out = outlook(pipeline, "combined", date)
        day = pd.Timestamp(out["date"])
        assert out["regime"] == path.loc[day]
        assert out["spells"][-1]["end"] == out["date"]
        assert sum(s["market_days"] for s in out["spells"]) == len(path.loc[:day]) == out["period"]["market_days"]
        assert sum(d["spells"] for d in out["duration"].values()) == out["period"]["complete_spells"]
        assert sum(n["ended"] for n in out["next"].values()) == out["period"]["spells"] - 1
        for info in out["next"].values():
            assert sum(v["count"] for v in info["to"].values()) == info["ended"]
        cur = out["current"]
        assert cur["market_days"] >= cur["unbroken_days"] >= 1
        assert path.loc[cur["unbroken_start"] : day].nunique() == 1
        if not cur["from_history_start"]:
            assert path.loc[: cur["start"]].iloc[-2] != out["regime"] or cur["blips"]
        reached = out["reached"]
        past = [s["market_days"] for s in out["spells"] if s["complete"] and s["regime"] == out["regime"]]
        assert reached["longer"] == sum(d > cur["market_days"] for d in past)
        json.dumps(out, allow_nan=False)
    # The same history cut at the date gives the same answer.
    cut = outlook(pipeline, "combined", "2015-06-01")
    assert cut["period"]["end"] <= "2015-06-01"
    assert all(s["end"] <= "2015-06-01" for s in cut["spells"])


def test_text_in_both_languages_says_it_is_not_a_forecast(pipeline):
    out = outlook(pipeline, "combined", "2020-03-20")
    for lang, words in (("en", "not a forecast"), ("fr", "ni prévision")):
        text = sentences(out, lang)
        assert words in text["caveat"]
        assert str(out["current"]["market_days"]) in text["so_far"]
        assert not any("{" in line for line in [*text.values(), *text["notes"]] if isinstance(line, str))
    slowdown = [s["end"] for s in out["spells"] if s["regime"] == "slowdown" and s["complete"]]
    out = outlook(pipeline, "combined", slowdown[-1])
    assert out["regime"] == "slowdown"
    assert any("SLOWDOWN_V23" in n for n in sentences(out, "en")["notes"])


def test_read_only(pipeline):
    before = (config_fingerprint(pipeline.settings), pipeline.state("combined").to_dict())
    outlook(pipeline, "combined")
    assert (config_fingerprint(pipeline.settings), pipeline.state("combined").to_dict()) == before
    assert MIN_DAYS == 5
