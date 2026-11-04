"""A API local recusa escrita sem token, host estranho e configuração ausente."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings, load_api_token

BASE = "http://127.0.0.1"


@pytest.fixture
def settings(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token="segredo-de-teste")


@pytest.fixture
def client(settings):
    main.app.dependency_overrides[main.settings_dep] = lambda: settings
    yield TestClient(main.app, base_url=BASE)
    main.app.dependency_overrides.clear()


WRITES = [
    ("post", "/api/studio/channels", {"fields": {"name": "x"}}),
    ("patch", "/api/studio/channels/chn_demo_rotas", {"fields": {"name": "x"}}),
    ("post", "/api/studio/channels/chn_demo_rotas/delete", {"confirm_name": "x"}),
    ("post", "/api/studio/channels/chn_demo_rotas/jobs/job_x/authorize", {}),
    ("post", "/api/studio/channels/chn_demo_rotas/briefings/brf_x/dispatch", {"idempotency_key": "k"}),
    ("post", "/api/generate", {"topic": "x", "format": "long"}),
]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_writes_without_token_are_refused(client, method, path, body):
    response = getattr(client, method)(path, json=body)
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path,body", WRITES)
def test_wrong_token_is_refused(client, method, path, body):
    assert getattr(client, method)(path, json=body, headers={"X-YTI-Token": "errado"}).status_code == 401


def test_valid_token_passes_and_read_stays_open(client):
    assert client.get("/api/studio/overview").status_code == 200
    response = client.post("/api/studio/channels", json={"fields": {"name": "Canal"}}, headers={"X-YTI-Token": "segredo-de-teste"})
    assert response.status_code == 201


def test_file_download_needs_token(client):
    assert client.get("/api/studio/channels/c/jobs/j/artifacts/a").status_code == 401


@pytest.mark.parametrize("host", ["evil.example", "192.168.0.10", "127.0.0.1.evil.example"])
def test_other_hosts_are_refused_even_for_reads(client, host):
    response = client.get("/api/system", headers={"host": host})
    assert response.status_code == 403 and response.json()["error"]["code"] == "host_not_allowed"


def test_localhost_with_port_is_accepted(client):
    assert client.get("/api/system", headers={"host": "localhost:8000"}).status_code == 200


def test_missing_configuration_fails_closed(tmp_path):
    main.app.dependency_overrides[main.settings_dep] = lambda: Settings(mode="demo", data_dir=tmp_path, api_token="")
    try:
        response = TestClient(main.app, base_url=BASE).post("/api/studio/channels", json={"fields": {"name": "x"}}, headers={"X-YTI-Token": ""})
    finally:
        main.app.dependency_overrides.clear()
    assert response.status_code == 503


def test_token_is_created_once_and_never_exposed(tmp_path, monkeypatch, settings, client):
    monkeypatch.delenv("YTI_API_TOKEN", raising=False)
    first = load_api_token(tmp_path / "novo")
    assert len(first) > 30 and load_api_token(tmp_path / "novo") == first
    assert "segredo-de-teste" not in client.get("/api/system").text
    assert "segredo-de-teste" not in client.get("/api/studio/overview").text


def test_environment_token_has_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("YTI_API_TOKEN", "do-ambiente")
    assert load_api_token(tmp_path) == "do-ambiente"
