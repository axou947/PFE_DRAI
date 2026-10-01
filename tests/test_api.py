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
