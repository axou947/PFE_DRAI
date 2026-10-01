"""Public track-record page: live record checks, live scoring, the frozen backtest record, the page itself."""

import copy
import json
import re

import pandas as pd
import pytest
import yaml

from pfe_drai.cli import main
from pfe_drai.config import load_settings
from pfe_drai.pipeline import State
from pfe_drai.publish import NotLiveDataError, publish
from pfe_drai.publish.page import LANGS, build_site, render
from pfe_drai.publish.record import (
    _BITCOIN_TAG,
    _PENDING_TAG,
    config_fingerprint,
    find_backtest,
    live_scorecard,
    ots_status,
    read_live,
    record_backtest,
)
from pfe_drai.validation import Episode, stress_signal
from pfe_drai.validation.metrics import alarm_spells, false_positives_per_year, latencies


def _settings(settings, **publish):
    s = copy.deepcopy(settings)
    s["publish"].update({"require_live_data": False, "opentimestamps": False, **publish})
    return s


class _Day:
    """Stands in for a Pipeline in `publish`: one published day with a given alarm state."""

    def __init__(self, settings, day, on, score=0.7, p=0.3):
        self.settings, self.day, self.on, self.score, self.p = settings, pd.Timestamp(day), on, score, p

    def state(self, model=None):
        probs = {"expansion": 1 - self.p, "overheating": 0.0, "slowdown": 0.0, "stress": self.p}
        alarm = {"on": self.on, "since": None, "score": self.score if self.on else 0.1, "threshold": 0.5, "confirm_days": 3}
        return State(
            date=self.day,
            model="combined",
            regime="stress" if self.p > 0.5 else "expansion",
            probabilities=probs,
            scores={},
            alarm=alarm,
            calibration={"combination": "calibrated"},
            data_provider="test",
            is_live_data=True,
        )


def _publish_days(settings, folder, days, alarm_on=()):
    for d in days:
        publish(_Day(settings, d, d in set(alarm_on)), out_dir=folder)


# ---------------------------------------------------------------- metrics
def test_alarm_spells_match_the_false_positive_count(settings):
    index = pd.bdate_range("2015-01-01", periods=400)
    on = pd.Series(False, index=index)
    on.iloc[50:60] = True  # a false alarm
    on.iloc[95:130] = True  # turns on 5 days before the episode: counts for it
    on.iloc[300:305] = True  # another false alarm
    on.iloc[395:] = True  # still on at the end
    eps = [Episode(index[100], index[150], "drawdown", -0.15)]
    spells = alarm_spells(on, eps, settings)
    assert list(spells["start"]) == [index[50], index[95], index[300], index[395]]
    assert list(spells["days"]) == [10, 35, 5, 5]
    assert list(spells["false_alarm"]) == [True, False, True, True]
    assert spells.loc[1, "episode_start"] == index[100]
    assert list(spells["open"]) == [False, False, False, True]
    years = (index[-1] - index[0]).days / 365.25
    assert spells["false_alarm"].sum() == pytest.approx(false_positives_per_year(on, eps, settings) * years)


def test_latencies_give_the_first_alarm_day_and_whether_the_window_is_over(settings):
    index = pd.bdate_range("2020-01-01", periods=120)
    signal = pd.Series(False, index=index)
    signal.iloc[33:40] = True
    eps = [Episode(index[30], index[40], "drawdown", -0.12), Episode(index[100], index[110], "volatility", -0.05)]
    lat = latencies(signal, eps, settings)
    assert lat.loc[0, "latency_days"] == 3 and lat.loc[0, "signal_date"] == index[33] and lat.loc[0, "window_complete"]
    assert not lat.loc[1, "detected"] and not lat.loc[1, "window_complete"]  # only 20 days of window seen so far


# ---------------------------------------------------------------- live record
def test_live_record_checks_every_hash_and_the_chain(settings, tmp_path):
    s = _settings(settings)
    days = pd.bdate_range("2026-10-01", periods=5)
    _publish_days(s, tmp_path, days, alarm_on=days[3:])
    live = read_live(tmp_path)
    assert [e["date"] for e in live.entries] == [d.date().isoformat() for d in days]
    assert live.chain_ok and not live.problems
    assert [e["alarm_on"] for e in live.entries] == [False, False, False, True, True]
    # Editing a published day shows: its hash no longer matches index.csv.
    path = tmp_path / f"{days[2].date()}.json"
    payload = json.loads(path.read_text())
    payload["regime"] = "expansion" if payload["regime"] == "stress" else "stress"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tampered = read_live(tmp_path)
    assert not tampered.chain_ok and any(days[2].date().isoformat() in p for p in tampered.problems)


def test_ots_status_reads_the_proof(tmp_path):
    day = tmp_path / "2026-10-02.json"
    day.write_text("{}")
    assert ots_status(day) == "missing"
    proof = tmp_path / "2026-10-02.json.ots"
    proof.write_bytes(b"\x00OpenTimestamps\x00" + _PENDING_TAG + b"https://alice.btc.calendar")
    assert ots_status(day) == "pending"
    proof.write_bytes(proof.read_bytes() + _BITCOIN_TAG + b"\x01")
    assert ots_status(day) == "bitcoin"


def test_live_scorecard_uses_the_alarms_as_published(settings, tmp_path):
    s = _settings(settings)
    index = pd.bdate_range("2026-10-01", periods=80)
    published = index.delete(10)  # one day without a publication
    _publish_days(s, tmp_path, published, alarm_on=index[40:50])
    live = read_live(tmp_path)
    eps = [
        Episode(index[42], index[55], "drawdown", -0.11),  # alarm on 2 days before: -2
        Episode(index[70], index[79], "volatility", -0.04),  # no alarm yet, window still open
    ]
    score = live_scorecard(live, eps, index, s)
    assert score["missing_days"] == 1
    first, second = score["episodes"]
    assert first["latency_days"] == -2 and first["status"] == "detected" and first["signal_date"] == str(index[40].date())
    assert second["latency_days"] is None and second["status"] == "pending"
    (alarm,) = score["alarms"]
    assert alarm["episode_start"] == str(index[42].date()) and not alarm["false_alarm"]
    assert alarm["peak_score"] == pytest.approx(0.7)


def test_a_recent_unexplained_alarm_is_pending_not_false(settings, tmp_path):
    s = _settings(settings)
    index = pd.bdate_range("2026-10-01", periods=60)
    _publish_days(s, tmp_path, index, alarm_on=list(index[5:8]) + list(index[50:53]))
    score = live_scorecard(read_live(tmp_path), [], index, s)
    old, recent = score["alarms"]
    assert old["false_alarm"] and not old["pending"]
    assert recent["pending"]  # an episode may still start within the look-back window


# ---------------------------------------------------------------- backtest record
def test_backtest_record_holds_every_episode_and_alarm(pipeline, tmp_path):
    with pytest.raises(NotLiveDataError):  # simulated data never goes into the official record
        record_backtest(pipeline, tmp_path)
    assert not (tmp_path / "backtest").exists()
    saved = dict(pipeline.settings["publish"])
    pipeline.settings["publish"].update({"require_live_data": False, "opentimestamps": False})
    try:
        path, record, written = record_backtest(pipeline, tmp_path)
        again = record_backtest(pipeline, tmp_path)
    finally:
        pipeline.settings["publish"].update(saved)
    assert written and not again[2] and again[0] == path  # written once, never rewritten
    assert json.loads(path.read_text()) == record

    result = pipeline.evaluate()
    m = record["metrics"]
    assert m["detected"] == result["detected"] and m["n_episodes"] == len(record["episodes"]) == result["n_episodes"]
    assert m["false_positives_per_year"] == pytest.approx(result["false_positives_per_year"], abs=1e-4)
    assert [e["latency_days"] for e in record["episodes"]] == [
        None if pd.isna(v) else int(v) for v in result["episodes"]["latency_days"]
    ]
    years = (pd.Timestamp(record["period"]["end"]) - pd.Timestamp(record["period"]["start"])).days / 365.25
    assert m["n_false_alarms"] == pytest.approx(m["false_positives_per_year"] * years, abs=0.01)
    cfg = pipeline.settings["validation"]
    signal = stress_signal(pipeline.alarm_score(), cfg["stress_probability_threshold"], cfg["confirm_days"])
    assert sum(record["daily"]["alarm"]) == int(signal.sum())
    assert len(record["daily"]["date"]) == record["period"]["days"]
    assert record["config_sha256"] == config_fingerprint(pipeline.settings)
    assert "equity" not in json.dumps(record)  # no market prices (data licences)


def test_a_new_configuration_gets_a_new_backtest_record(settings, tmp_path):
    folder = tmp_path / "backtest"
    folder.mkdir()
    (folder / "2026-10-01.json").write_text(json.dumps({"config_sha256": config_fingerprint(settings)}))
    assert find_backtest(tmp_path, settings)[0].name == "2026-10-01.json"
    changed = copy.deepcopy(settings)
    changed["validation"]["confirm_days"] += 1
    assert find_backtest(tmp_path, changed) is None
    # The data source and end date do not change the configuration.
    later = copy.deepcopy(settings)
    later["data"].update({"provider": "fred", "end": "2030-01-01"})
    assert config_fingerprint(later) == config_fingerprint(settings)


# ---------------------------------------------------------------- the page
def _record():
    days = pd.bdate_range("2020-01-01", periods=30)
    return {
        "kind": "backtest",
        "model": "combined",
        "stress_sources": ["gbm", "onset"],
        "combination": "calibrated",
        "data_provider": "fred",
        "is_live_data": True,
        "generated_at": "2026-10-01T22:40:00+00:00",
        "code_version": "abc1234",
        "config_sha256": "0" * 64,
        "episode_rule_sha256": "1" * 64,
        "period": {"start": "2020-01-01", "end": "2020-02-11", "days": 30},
        "rules": {
            "alarm_threshold": 0.5,
            "confirm_days": 3,
            "detection_window_days": 60,
            "lookback_days": 20,
            "calibration_horizon_days": 5,
            "drawdown_threshold": -0.1,
            "vol_quantile": 0.95,
        },
        "targets": {"max_median_latency_days": 5, "max_false_positives_per_year": 1.5, "max_false_alarm_share": 0.1},
        "metrics": {
            "n_episodes": 2,
            "detected": 1,
            "median_latency": -3.0,
            "median_latency_all": 28.5,
            "false_positives_per_year": 1.26,
            "false_alarm_share": 0.049,
            "switches_per_year": 5.6,
            "n_alarms": 2,
            "n_false_alarms": 1,
            "brier": 0.091,
            "ece": 0.042,
            "log_loss": 0.316,
            "brier_skill": 0.22,
            "base_rate": 0.136,
            "mean_p": 0.14,
            "n_days": 25,
        },
        "reliability": [{"low": 0.0, "high": 0.1, "predicted": 0.05, "observed": 0.04, "days": 25}],
        "episodes": [
            {"start": "2020-01-10", "end": "2020-01-24", "trigger": "drawdown", "max_drawdown": -0.2, "latency_days": -3},
            {"start": "2020-02-03", "end": "2020-02-11", "trigger": "volatility", "max_drawdown": -0.06, "latency_days": None},
        ],
        "alarms": [
            {"start": "2020-01-07", "end": "2020-01-20", "days": 10, "peak_score": 0.9, "episode_start": "2020-01-10"},
            {"start": "2020-01-28", "end": "2020-01-29", "days": 2, "peak_score": 0.6, "episode_start": None},
        ],
        "daily": {
            "date": [str(d.date()) for d in days],
            "p_stress": [0.1] * 30,
            "score": [0.2] * 30,
            "alarm": [0] * 4 + [1] * 10 + [0] * 16,
        },
    }


def test_page_shows_every_episode_and_alarm_and_needs_nothing_external(settings, tmp_path):
    s = _settings(settings)
    record = _record()
    record["alarms"][0].update({"false_alarm": False, "open": False})
    record["alarms"][1].update({"false_alarm": True, "open": False})
    days = pd.bdate_range("2026-10-01", periods=3)
    _publish_days(s, tmp_path, days, alarm_on=days[2:])
    live = read_live(tmp_path)
    score = {"episodes": [], "alarms": [], "missing_days": 0, "last_market_day": str(days[-1].date())}
    meta = {"file": "backtest/2020-02-11.json", "sha256": "f" * 64, "ots": "pending"}
    for lang in LANGS:
        page = render(live, score, record, meta, s, lang)
        assert page == render(live, score, record, meta, s, lang)  # same records, same file
        for ep in record["episodes"]:
            assert ep["start"] in page or pd.Timestamp(ep["start"]).strftime("%d/%m/%Y") in page
        assert page.count("<tr>") >= 2 + 2 + 3  # episodes, alarms, published days
        assert not re.search(r"<(script|link|img)[^>]+(src|href)=", page)  # self-contained
        assert "2026-10-05.json" in page  # links to the published files
    assert "missed" in render(live, score, record, meta, s, "en")
    assert "manqué" in render(live, score, record, meta, s, "fr")


def test_page_with_no_published_day_says_so(settings, tmp_path):
    page = render(read_live(tmp_path), {}, None, {}, settings, "en")
    assert "No day published yet" in page and "Backtest record" in page


def test_preview_leaves_the_track_record_untouched(pipeline, settings, tmp_path):
    records, preview = tmp_path / "track_record", tmp_path / "preview"
    _publish_days(_settings(settings), records, pd.bdate_range("2026-10-01", periods=2))
    before = sorted(p.name for p in records.iterdir())
    result = build_site(pipeline, records, preview)  # simulated data: allowed outside the record
    assert sorted(p.name for p in records.iterdir()) == before
    assert {p.name for p in result["pages"]} == set(LANGS.values())
    assert result["score"].get("unscored")  # live days are only scored with real market data
    page = (preview / "index.html").read_text()
    assert "SIMULATED DATA" in page and "2026-10-02" in page


def test_cli_refuses_to_write_a_simulated_backtest_into_the_track_record(tmp_path):
    config = tmp_path / "settings.yaml"
    config.write_text(yaml.safe_dump(load_settings(overrides={"publish": {"dir": str(tmp_path / "track_record")}})))
    with pytest.raises(NotLiveDataError):
        main(["--config", str(config), "track-record"])
