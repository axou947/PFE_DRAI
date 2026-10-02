import pytest
from fastapi.testclient import TestClient

import api.main as api_main


@pytest.fixture(scope="module")
def client(pipeline):
    api_main.pipeline.cache_clear()
    api_main.pipeline = lambda: pipeline  # reuse the test pipeline
    return TestClient(api_main.app)


def test_regime(client):
    body = client.get("/regime", params={"model": "kmeans", "lang": "en"}).json()
    assert body["regime"] in ("expansion", "overheating", "slowdown", "stress")
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-6


def test_scenarios_and_report(client):
    assert len(client.get("/scenarios", params={"model": "kmeans"}).json()) == 3
    assert client.get("/report", params={"model": "kmeans", "fmt": "pdf"}).content[:4] == b"%PDF"


def test_bad_model(client):
    assert client.get("/regime", params={"model": "nope"}).status_code == 400


def test_regime_states(client):
    body = client.get("/regime/states", params={"model": "combined", "lang": "en"}).json()
    latest = body[-1]["states"]
    assert all(abs(sum(s[f"share_{r}"] for r in ("expansion", "overheating", "slowdown", "stress")) - 1) < 1e-6 for s in latest)
    assert {s["name_label"] for s in latest} <= {"Expansion", "Inflationary overheating", "Slowdown", "Stress / crisis"}
    assert client.get("/regime/states", params={"model": "gbm"}).status_code == 404


def test_world(client):
    body = client.get("/world", params={"date": "2020-04-01", "horizon": "1W", "lang": "en"}).json()
    assert body["date"] == "2020-04-01" and len(body["markets"]) == 20
    assert body["share_stress"] + body["share_elevated"] > 0.5
    france = next(m for m in body["markets"] if m["id"] == "FRA")
    assert france["name"] == "France" and france["ticker"] == "EWQ" and france["state"] in ("calm", "elevated", "stress")


def test_world_default_output_is_unchanged(client):
    # The currency toggle must not alter the default (USD) response: compared with a fixture from before it.
    from pathlib import Path

    expected = (Path(__file__).parent / "fixtures" / "world_api_default.json").read_text()
    params = {"date": "2020-04-01", "horizon": "1W", "lang": "en"}
    assert client.get("/world", params=params).text == expected
    assert client.get("/world", params={**params, "currency": "usd"}).text == expected


def test_world_local_currency(client):
    params = {"date": "2020-04-01", "horizon": "1M", "lang": "en"}
    usd = client.get("/world", params=params).json()
    local = client.get("/world", params={**params, "currency": "local"}).json()
    assert local["currency"] == "local" and local["fx_last_published"]
    for u, m in zip(usd["markets"], local["markets"], strict=True):
        assert m["return"] == u["return"] and m["state"] == u["state"]  # USD figures and states unchanged
        assert abs((m["return"] - m["return_local"]) - m["currency"]) < 2e-4  # rounded to 4 decimals
    usa = next(m for m in local["markets"] if m["id"] == "USA")
    assert usa["fx_status"] == "usd" and usa["currency"] == 0
    assert client.get("/world", params={**params, "currency": "eur"}).status_code == 422


def test_world_link(client):
    body = client.get("/world/link", params={"date": "2020-04-01", "window": 63, "lang": "en"}).json()
    assert body["window_days"] == 63 and len(body["markets"]) == 20 and 0 < body["average_correlation"] <= 1
    usa = next(m for m in body["markets"] if m["id"] == "USA")
    assert usa["corr"] == 1 and usa["follows"] is None
    assert client.get("/world/link", params={"window": 10}).status_code == 400


def test_calibration(client):
    body = client.get("/calibration", params={"model": "combined"}).json()
    assert body["probability"]["ece"] < body["detector_score"]["ece"]
    assert sum(b["days"] for b in body["probability"]["reliability"]) == body["probability"]["n_days"]
    assert body["calibrator"]["weights"]["max"] >= 0
    regime = client.get("/regime", params={"model": "combined", "date": "2020-03-20"}).json()
    assert regime["alarm"]["on"] is True and regime["calibration"]["combination"] == "calibrated"
