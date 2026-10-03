"""Explain the regime (pfe_drai/explain.py, docs/EXPLAIN.md): exact, faithful to the rule, read-only."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pfe_drai.explain import WEEK, apply_what_if, contributions, explain, note_lines, rule_step, sentences
from pfe_drai.features import DIMENSIONS, FEATURES
from pfe_drai.features.market import CREDIT, MARKET
from pfe_drai.models import available_models
from pfe_drai.publish.snapshot import config_fingerprint

FIXTURE = Path(__file__).parent / "fixtures" / "explain_invariance.json"


def _sample_dates(pipeline, n=60):
    """Every regime of the rule, spread over the history (the stress days of 2008 and 2020 included)."""
    idx = pipeline.probabilities("combined").index
    labels = pipeline.labels.loc[idx]
    picks = [labels[labels == r].index for r in labels.unique()]
    dates = {d for days in picks for d in days[:: max(1, len(days) // (n // len(picks)))]}
    return sorted(dates | {idx[-1], pd.Timestamp("2020-03-16")})


def _published(pipeline):
    """What the daily publication, the status command and the backtest read, as a fixture."""
    metrics = pipeline.evaluate("combined")
    metrics.pop("episodes", None)
    out = {
        "config_sha256": config_fingerprint(pipeline.settings),
        "state": pipeline.state("combined").to_dict(),
        "state_2020": pipeline.state("combined", "2020-03-16").to_dict(),
        "metrics": metrics,
    }
    return json.dumps(out, indent=1, sort_keys=True, default=str) + "\n"


def test_contributions_sum_to_every_score_on_every_day(pipeline):
    parts = contributions(pipeline)
    for dim in DIMENSIONS:
        gap = (parts[dim].sum(axis=1) - pipeline.scores[dim]).abs().max()
        assert gap < 1e-9, dim


def test_explanation_matches_the_rule_and_its_parts_add_up(pipeline):
    for date in _sample_dates(pipeline, 24):
        exp = explain(pipeline, "combined", date)
        day = pd.Timestamp(exp["date"])
        assert exp["rule"]["label"] == pipeline.labels.loc[day]
        assert exp["rule"]["agrees_with_model"] == (exp["rule"]["label"] == exp["regime"])
        for dim, info in exp["dimensions"].items():
            assert abs(sum(c["contribution"] for c in info["contributions"]) - info["score"]) < 1e-9
            assert abs(sum(c["week_ago"] for c in info["contributions"]) - info["week_ago"]) < 1e-9
            assert abs(sum(c["month_ago"] for c in info["contributions"]) - info["month_ago"]) < 1e-9
            assert info["score"] == pipeline.scores.at[day, dim]
        json.dumps(exp, allow_nan=False)


def test_rule_step_on_every_day(pipeline):
    scores = pipeline.scores.iloc[::7]
    steps = {"stress": "stress", "overheating": "inflation", "slowdown": "growth", "expansion": "none"}
    for day, row in scores.iterrows():
        label, step = rule_step(row, pipeline.settings)
        assert label == pipeline.labels.loc[day] and step == steps[label]


def test_each_what_if_really_flips_the_rule_and_impossible_ones_are_hidden(pipeline):
    clip = pipeline.settings["features"]["zscore_clip"]
    checked = hidden = 0
    for date in _sample_dates(pipeline):
        exp = explain(pipeline, "combined", date)
        now = exp["rule"]["label"]
        for w in exp["flip"]["what_if"]:
            dz = w["z_change"]
            assert abs(dz) <= clip
            step = np.sign(dz) * 1e-9
            assert apply_what_if(pipeline, date, w["feature"], dz * (1 + 1e-9) + step) == w["to"] != now
            assert apply_what_if(pipeline, date, w["feature"], dz * 0.99) == now  # nothing flips before it
            checked += 1
        for h in exp["flip"]["hidden"]:
            z = pipeline.features.loc[: pd.Timestamp(exp["date"]), h["feature"]]
            rows = z.iloc[-21:] if FEATURES[h["feature"]] == "growth" else z.iloc[-1:]
            assert abs(h["z_change"]) > clip or ((rows + h["z_change"]).abs() > clip).any()
            hidden += 1
        nearest = exp["flip"]["nearest"]
        if nearest:
            moves = [abs(f["score_change"]) for f in exp["flip"]["dimensions"].values() if f]
            assert abs(nearest["score_change"]) == min(moves)
    assert checked > 50 and hidden > 0


@pytest.mark.parametrize("model", available_models())
def test_alarm_drivers_for_every_model(pipeline, model):
    for date in (None, "2020-03-16", "2008-10-10"):
        exp = explain(pipeline, model, date)
        alarm = exp["alarm"]
        assert alarm["highest"] in alarm["sources"]
        assert alarm["sources"][alarm["highest"]] == max(alarm["sources"].values())
        drivers = alarm["drivers"]
        assert drivers["available"], drivers
        # Same walk-forward fit as the published probability: the occlusion starts from the shown value.
        assert drivers["reproduced"]
        assert len(drivers["inputs"]) <= 5
        changes = [r["change"] for r in drivers["inputs"]]
        assert all(-1 <= c <= 1 for c in changes) and changes == sorted(changes, key=lambda c: -abs(c))
        inputs = MARKET + CREDIT if drivers["source"] == "onset" else list(FEATURES)
        assert all(r["input"] in inputs for r in drivers["inputs"])
        json.dumps(exp, allow_nan=False)


def test_combined_alarm_reads_the_highest_source(pipeline):
    exp = explain(pipeline, "combined")
    assert set(exp["alarm"]["sources"]) == {"jump", "gbm", "onset"}
    assert abs(max(exp["alarm"]["sources"].values()) - exp["alarm"]["score"]) < 1e-4  # the alarm's own score, rounded


def test_texts_are_complete_and_plain_in_both_languages(pipeline):
    codes = {c for c in set(FEATURES) | set(MARKET) | set(CREDIT) if "_" in c}  # "drawdown" is also a plain word
    for date in (None, "2020-03-16"):
        exp = explain(pipeline, "combined", date)
        for lang in ("fr", "en"):
            text = json.dumps(sentences(exp, lang), ensure_ascii=False)
            assert "explain." not in text and "{" not in text.replace('{"', "").replace("{}", "")
            words = set(re.findall(r"[a-z_0-9]+", text))
            assert not (words & codes), words & codes  # plain names only, never a raw code
            lines = note_lines(exp, lang)
            assert 4 <= len(lines) <= 6
            advice = r"\b(should|must|buy|sell|recommend|doit|devrait|acheter|vendre|recommand)"
            assert not re.search(advice, " ".join(lines), re.I)


def test_explaining_changes_nothing_published(pipeline):
    """State (the daily JSON and `status`), the settings fingerprint and the backtest metrics stay byte-identical."""
    before = _published(pipeline)
    for model in available_models():
        explain(pipeline, model)
    explain(pipeline, "combined", "2020-03-16")
    assert _published(pipeline) == before
    # ...and the same outputs as computed on main before explain.py existed. Another machine's CPU and
    # libraries can change the last of 17 digits (summation order), so this check reads 12 significant digits.
    assert _digits(json.loads(before)) == _digits(json.loads(FIXTURE.read_text()))


def _digits(value, significant=12):
    if isinstance(value, float):
        return float(f"{value:.{significant}g}")
    if isinstance(value, dict):
        return {k: _digits(v, significant) for k, v in value.items()}
    if isinstance(value, list):
        return [_digits(v, significant) for v in value]
    return value


def test_works_on_a_region_with_dropped_inputs(settings):
    from pfe_drai.config import load_settings
    from pfe_drai.pipeline import Pipeline

    data = {"provider": "synthetic", "start": "2004-01-01", "end": "2026-06-30"}
    em = load_settings(overrides={"data": data, "models": {"gbm": {"max_iter": 30}}}, region="em")
    p = Pipeline(em, use_cache=False)
    exp = explain(p, "kmeans")
    used = {c["feature"] for d in exp["dimensions"].values() for c in d["contributions"]}
    assert used.isdisjoint(em["features"]["drop"])
    for dim, info in exp["dimensions"].items():
        assert abs(sum(c["contribution"] for c in info["contributions"]) - info["score"]) < 1e-9, dim


def test_week_and_month_ago_dates(pipeline):
    exp = explain(pipeline, "kmeans")
    idx = pipeline.scores.index
    pos = idx.get_loc(pd.Timestamp(exp["date"]))
    assert exp["dates"]["week_ago"] == idx[pos - WEEK].date().isoformat()
    assert exp["dates"]["month_ago"] == idx[pos - 21].date().isoformat()
