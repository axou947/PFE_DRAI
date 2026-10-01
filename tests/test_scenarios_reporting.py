import hashlib
import json

import pandas as pd
import pytest

from pfe_drai.publish import NotLiveDataError, publish
from pfe_drai.reporting import build_note, to_html, to_markdown, to_pdf
from pfe_drai.scenarios import fund_impact, load_funds, load_library, rank_scenarios
from pfe_drai.validation import rule_fingerprint


def test_fund_weights_sum_to_one(settings):
    for fund in load_funds(settings):
        assert abs(sum(fund.weights.values()) - 1) < 1e-9, fund.id


def test_scenarios_cover_asset_classes(settings):
    assets, scenarios = load_library(settings)
    for sc in scenarios:
        assert set(sc.shocks) == set(assets), sc.id
        assert sc.regime in settings["regimes"]["order"]


def test_stress_state_ranks_crises_first(settings):
    _, scenarios = load_library(settings)
    scores = pd.Series({"stress": 3.0, "growth": -2.0, "inflation": -0.8})
    probs = pd.Series({"expansion": 0.0, "overheating": 0.0, "slowdown": 0.1, "stress": 0.9})
    ranking = rank_scenarios(scenarios, scores, probs)
    assert ranking.iloc[0]["regime"] == "stress"


def test_impact_is_weighted_sum(settings):
    _, scenarios = load_library(settings)
    impact = fund_impact({"equity_world": 1.0}, scenarios[0])
    assert impact["total"] == scenarios[0].shocks["equity_world"]


def test_note_in_both_languages(pipeline):
    for lang in ("fr", "en"):
        note = build_note(pipeline, lang)
        assert note["title"] and len(note["scenarios"]) == 3
        assert ("Noms des régimes" if lang == "fr" else "Regime names") in note["method"]
        assert "#" in to_markdown(note)
        assert to_html(note).startswith("<!doctype html>")
        assert to_pdf(note)[:4] == b"%PDF"


def test_publish_refuses_simulated_data(pipeline, tmp_path):
    with pytest.raises(NotLiveDataError):
        publish(pipeline, "kmeans", out_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_publish_writes_hash_chain(pipeline, tmp_path, monkeypatch):
    monkeypatch.setitem(pipeline.settings["publish"], "require_live_data", False)
    (tmp_path / "index.csv").write_text("date,regime,p_regime,model,data_provider,sha256\n2000-01-03,stress,0.9,kmeans,x,abc\n")
    path = publish(pipeline, "kmeans", out_dir=tmp_path)
    payload = json.loads(path.read_text())
    assert payload["previous_sha256"] == "abc"
    assert payload["episode_rule_sha256"] == rule_fingerprint(pipeline.settings)
    # Each entry keeps how the model's states were named (docs/REGIMES.md).
    assert [s["name"] for s in payload["states"]] == list(pipeline.state_map("kmeans")["name"])
    # A second run on the same market day (holiday, re-run) publishes nothing.
    assert publish(pipeline, "kmeans", out_dir=tmp_path) is None
    rows = (tmp_path / "index.csv").read_text().strip().splitlines()
    assert len(rows) == 3
    assert rows[-1].endswith(hashlib.sha256(path.read_bytes()).hexdigest())
