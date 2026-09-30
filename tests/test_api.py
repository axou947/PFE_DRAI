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
