"""Global board: every published region side by side, read from the track record, and the challenger scorecard."""

import copy
import json
import re

import pandas as pd
import pytest

from pfe_drai.cli import main
from pfe_drai.pipeline import State
from pfe_drai.publish import publish
from pfe_drai.publish.board import board, published_regions, read_scorecard
from pfe_drai.publish.page import LANGS, render
from pfe_drai.publish.record import read_live


@pytest.fixture
def s(settings):
    out = copy.deepcopy(settings)
    out["publish"].update({"require_live_data": False, "opentimestamps": False})
    return out


class _Day:
    """Stands in for a Pipeline in `publish`: one published day with a given P(stress)."""

    def __init__(self, settings, day, p, on=False):
        self.settings, self.day, self.p, self.on = settings, pd.Timestamp(day), p, on

    def state(self, model=None):
        probs = {"expansion": 1 - self.p, "overheating": 0.0, "slowdown": 0.0, "stress": self.p}
        alarm = {"on": self.on, "since": str(self.day.date()) if self.on else None, "score": 0.7 if self.on else 0.1}
        return State(
            date=self.day,
            model="combined",
            regime="stress" if self.p > 0.5 else "expansion",
            probabilities=probs,
            scores={},
            alarm={**alarm, "threshold": 0.5, "confirm_days": 3},
            calibration={"combination": "calibrated"},
            data_provider="test",
            is_live_data=True,
        )


def _publish(settings, folder, days, ps, on=()):
    for d, p in zip(days, ps, strict=True):
        publish(_Day(settings, d, p, on=d in set(on)), out_dir=folder)


def test_only_regions_that_passed_their_rule_are_on_the_board():
    names = [r for r, _ in published_regions()]
    assert names == ["us", "uk", "japan", "em"]  # the euro area stays experimental (docs/EURO.md)


def test_board_reads_each_region_as_published(s, tmp_path):
    days = pd.bdate_range("2026-10-01", periods=5)
    _publish(s, tmp_path, days, [0.1, 0.2, 0.7, 0.8, 0.9], on=days[3:])
    _publish(s, tmp_path / "uk", days, [0.1] * 5)
    _publish(s, tmp_path / "japan", days[:1], [0.3])
    out = board(s, tmp_path)
    rows = {r["region"]: r for r in out["regions"]}
    assert list(rows) == ["us", "uk", "japan", "em"] and out["newest"] == str(days[-1].date())

    us = rows["us"]
    assert us["regime"] == "stress" and us["p_stress"] == pytest.approx(0.9) and us["p_regime"] == pytest.approx(0.9)
    assert us["alarm_on"] and us["alarm_since"] == str(days[-1].date())
    # The regime changed on the third day: three published days in it, not since the record began.
    assert (us["regime_since"], us["regime_days"], us["regime_since_record_start"]) == (str(days[2].date()), 3, False)
    assert us["folder"] == "." and us["chain_ok"] and us["days"] == 5

    uk = rows["uk"]
    assert uk["regime"] == "expansion" and uk["regime_days"] == 5 and uk["regime_since_record_start"]
    assert uk["folder"] == "uk" and not uk["late"]
    assert rows["japan"]["late"]  # four business days behind the newest region
    assert rows["em"]["date"] is None and not rows["em"]["late"]


def test_board_shows_a_broken_chain(s, tmp_path):
    days = pd.bdate_range("2026-10-01", periods=2)
    _publish(s, tmp_path / "uk", days, [0.1, 0.1])
    path = tmp_path / "uk" / f"{days[0].date()}.json"
    path.write_text(path.read_text().replace("expansion", "slowdown"), encoding="utf-8")
    uk = next(r for r in board(s, tmp_path)["regions"] if r["region"] == "uk")
    assert not uk["chain_ok"] and uk["problems"] >= 1


def _card(folder):
    folder.mkdir(parents=True)
    card = {
        "since": "2026-10-06",
        "last_market_day": "2026-10-08",
        "models": {
            n: {
                "name": n,
                "days": 3,
                "first_day": "2026-10-06",
                "chain_ok": True,
                "alarm_days": 0,
                "episodes_scored": 0,
                "detected": 0,
                "pending": 0,
                "median_latency": None,
                "false_alarms": 0,
                "false_alarms_pending": 0,
            }
            for n in ["v2.2 (published)", "vix_term", "hy_credit"]
        },
        "episodes": [],
        "months": [],
    }
    (folder / "scorecard.json").write_text(json.dumps(card), encoding="utf-8")


def test_page_shows_the_board_and_the_scorecard_and_stays_self_contained(s, tmp_path):
    days = pd.bdate_range("2026-10-01", periods=3)
    _publish(s, tmp_path, days, [0.1, 0.1, 0.1])
    _publish(s, tmp_path / "uk", days, [0.1, 0.1, 0.1])
    assert read_scorecard(s, tmp_path) is None
    _card(tmp_path / "challengers")
    card = read_scorecard(s, tmp_path)
    assert card["folder"] == "challengers"
    live, gb = read_live(tmp_path), board(s, tmp_path)
    for lang in LANGS:
        page = render(live, {"unscored": True}, None, {}, s, lang, board=gb, challengers=card)
        assert page == render(live, {"unscored": True}, None, {}, s, lang, board=gb, challengers=card)
        assert 'href="uk/index.csv"' in page and f'href="uk/{days[-1].date()}.json"' in page
        assert 'href="challengers/scorecard.md"' in page and "vix_term" in page and "hy_credit" in page
        assert not re.search(r"<(script|link|img)[^>]+(src|href)=", page)
    en = render(live, {"unscored": True}, None, {}, s, "en", board=gb, challengers=card)
    fr = render(live, {"unscored": True}, None, {}, s, "fr", board=gb, challengers=card)
    assert "Global board" in en and "United Kingdom" in en
    assert "the record began" in en and "no day published yet" in en
    assert "Vue mondiale" in fr and "Royaume-Uni" in fr and "Tableau des challengers" in fr
    # Before the first challenger day the page says so.
    assert "No challenger day published yet" in render(live, {"unscored": True}, None, {}, s, "en", board=gb)
    # Without a board the page is the one it was before.
    assert "Global board" not in render(live, {"unscored": True}, None, {}, s, "en")


def test_cli_board_reads_without_data(capsys):
    main(["--lang", "en", "board"])
    out = capsys.readouterr().out
    assert "United States" in out and "Emerging markets" in out


def test_api_board_and_challengers(pipeline):
    from fastapi.testclient import TestClient

    import api.main as api_main

    client = TestClient(api_main.app)
    body = client.get("/board", params={"lang": "en"}).json()
    assert [r["region"] for r in body["regions"]] == ["us", "uk", "japan", "em"]
    assert body["regions"][0]["region_label"] == "United States"
    assert client.get("/challengers").status_code in (200, 404)
