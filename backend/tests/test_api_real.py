"""Integração com a Data API: formato oficial, erros reais, cache, cota e proveniência.

Aqui nada acessa a rede. Os corpos de erro em `yt_mock` foram capturados do Google, e os campos vêm do documento
público de descoberta. Isso prova que o aplicativo entende o formato, não que uma consulta real com chave funcionou.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import collector, main
from app.config import Settings, get_settings, loopback_base_url
from app.connectors.quota import BudgetExceeded, QuotaLedger
from app.connectors.youtube_data import CredentialError, NetworkError, QuotaExceeded, ResponseFormatError, YouTubeApiError, YouTubeDataClient
from app.connectors.youtube_shape import check_response
from app.db import connect, migrate
from app.deps import settings_dep
from app.intel import api_status
from app.intel import router as intel_router
from app.logging_safe import redact
from tests.yt_mock import REAL_INVALID_KEY, REAL_NO_KEY, FakeYouTube, error_response

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
KEY = "AIzaTESTKEY0000000000000000"
OFFICIAL = json.loads((Path(__file__).parent / "fixtures" / "youtube_discovery_fields.json").read_text(encoding="utf-8"))


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token="t", quota_default_daily=100, quota_search_daily=5)


@pytest.fixture
def db(cfg):
    conn = connect(cfg.live_db_path)
    migrate(conn)
    yield conn
    conn.close()


def client(cfg, db, fake, clock=lambda: NOW):
    return YouTubeDataClient(cfg, db, transport=fake.transport(), sleep=lambda _s: None, clock=clock)


def factory(fake):
    return lambda settings, conn: client(settings, conn, fake)


# --- Formato oficial ------------------------------------------------------------------------------

@pytest.mark.parametrize("resource,call", [
    ("search", lambda c: c.search_videos("roma", "pt", "BR", "2026-11-01T00:00:00Z", None, "date")),
    ("search", lambda c: c.search_channels("roma", "pt", "BR")),
    ("videos", lambda c: c.videos(["vid00"])),
    ("channels", lambda c: c.channels(ids=["UCfake1"])),
    ("channels", lambda c: c.channels(handle="@falso")),
    ("playlistItems", lambda c: c.playlist_items("UUfake1")),
])
def test_every_parameter_sent_exists_in_the_official_schema(cfg, db, resource, call):
    fake = FakeYouTube(NOW)
    call(client(cfg, db, fake))
    sent = set(fake.calls[-1].url.params) - {"key"}
    assert sent <= set(OFFICIAL["parameters"][resource]), sent - set(OFFICIAL["parameters"][resource])


def test_max_results_is_not_sent_together_with_ids(cfg, db):
    """A documentação proíbe. O YouTube falso antigo aceitava, e o defeito só apareceria com a API real."""
    fake = FakeYouTube(NOW)
    c = client(cfg, db, fake)
    c.videos(["vid00"])
    c.channels(ids=["UCfake1"])
    assert all("maxResults" not in call.url.params for call in fake.calls)


@pytest.mark.parametrize("schema,paths", [
    ("Video", ["id", "snippet.channelId", "snippet.title", "snippet.publishedAt", "snippet.liveBroadcastContent", "snippet.defaultAudioLanguage", "snippet.thumbnails",
               "contentDetails.duration", "statistics.viewCount", "statistics.likeCount", "statistics.commentCount", "player.embedWidth", "player.embedHeight", "liveStreamingDetails"]),
    ("Channel", ["id", "snippet.title", "snippet.customUrl", "snippet.country", "contentDetails.relatedPlaylists.uploads", "statistics.subscriberCount", "statistics.hiddenSubscriberCount", "statistics.videoCount"]),
    ("SearchResult", ["id.videoId", "id.channelId", "snippet.channelId", "snippet.publishedAt"]),
    ("PlaylistItem", ["contentDetails.videoId"]),
    ("SearchListResponse", ["items", "nextPageToken", "pageInfo.totalResults"]),
])
def test_every_field_read_exists_in_the_official_schema(schema, paths):
    assert set(paths) <= set(OFFICIAL["fields"][schema])


def test_simulator_only_uses_official_fields():
    fake = FakeYouTube(NOW)

    def walk(node, prefix=""):
        for key, value in node.items():
            path = f"{prefix}{key}"
            yield path
            if isinstance(value, dict) and key not in {"thumbnails"}:
                yield from walk(value, path + ".")

    assert set(walk(next(iter(fake.videos.values())))) <= set(OFFICIAL["fields"]["Video"])
    assert set(walk(fake.channel)) <= set(OFFICIAL["fields"]["Channel"])


# --- Erros: corpos reais do Google ----------------------------------------------------------------

def test_real_invalid_key_body_is_understood_and_not_retried(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.Response(400, json=REAL_INVALID_KEY)]
    with pytest.raises(CredentialError) as caught:
        client(cfg, db, fake).channels(handle="@x")
    assert caught.value.kind == "key_invalid" and caught.value.reason == "API_KEY_INVALID"
    assert len(fake.calls) == 1


def test_real_missing_key_body_is_understood(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.Response(403, json=REAL_NO_KEY)]
    with pytest.raises(CredentialError) as caught:
        client(cfg, db, fake).channels(handle="@x")
    assert caught.value.kind == "key_missing"


@pytest.mark.parametrize("status,reason,kind", [
    (403, "accessNotConfigured", "api_disabled"), (403, "ipRefererBlocked", "key_restricted"), (400, "keyInvalid", "key_invalid"),
])
def test_credential_failures_have_their_own_kind(cfg, db, status, reason, kind):
    fake = FakeYouTube(NOW)
    fake.fail_next = [error_response(status, reason)]
    with pytest.raises(CredentialError) as caught:
        client(cfg, db, fake).channels(handle="@x")
    assert caught.value.kind == kind


def test_error_message_never_contains_the_key(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.ConnectError(f"falhou em ?key={KEY}")] * 4
    with pytest.raises(NetworkError) as caught:
        client(cfg, db, fake).channels(handle="@x")
    assert KEY not in str(caught.value) and KEY not in redact(f"key={KEY}")


def test_network_failure_retries_then_reports_network(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.ConnectError("sem rede")] * 2
    assert client(cfg, db, fake).channels(handle="@x")["items"]
    assert len(fake.calls) == 3
    fake.fail_next = [httpx.ReadTimeout("lento")] * 4
    with pytest.raises(NetworkError) as caught:
        client(cfg, db, fake).check_channel("@x")
    assert caught.value.kind == "network"


def test_google_quota_refusal_stops_calls_until_next_quota_day(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [error_response(403, "quotaExceeded")]
    with pytest.raises(QuotaExceeded):
        client(cfg, db, fake).check_channel("@x")
    before = len(fake.calls)
    with pytest.raises(BudgetExceeded):
        client(cfg, db, fake).check_channel("@x")
    assert len(fake.calls) == before
    tomorrow = NOW + timedelta(days=1)
    assert client(cfg, db, fake, clock=lambda: tomorrow).check_channel("@x")["items"]


def test_local_budget_stops_search_before_any_call(tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token="t", quota_search_daily=1)
    conn = connect(settings.live_db_path)
    migrate(conn)
    fake = FakeYouTube(NOW)
    c = client(settings, conn, fake)
    c.search_videos("roma")
    with pytest.raises(BudgetExceeded):
        c.search_videos("vikings")
    assert sum(1 for call in fake.calls if call.url.path.endswith("/search")) == 1
    conn.close()


# --- Formato inesperado ---------------------------------------------------------------------------

@pytest.mark.parametrize("response", [httpx.Response(200, text="<html>erro</html>"), httpx.Response(200, json=[1, 2]), httpx.Response(200, json={"items": "x"})])
def test_broken_200_is_an_error_and_never_cached(cfg, db, response):
    fake = FakeYouTube(NOW)
    fake.fail_next = [response]
    with pytest.raises(ResponseFormatError):
        client(cfg, db, fake).channels(handle="@x")
    assert db.execute("SELECT COUNT(*) AS n FROM api_cache").fetchone()["n"] == 0


def test_incomplete_item_is_dropped_and_reported(cfg, db):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.Response(200, json={"items": [{"id": "semsnippet"}, fake.videos["vid00"]]})]
    c = client(cfg, db, fake)
    assert [item["id"] for item in c.videos(["semsnippet", "vid00"])["items"]] == ["vid00"]
    assert any("sem snippet" in warning for warning in c.provenance()["warnings"])


def test_hidden_public_fields_are_not_format_errors():
    item = {"id": "UC1", "snippet": {"title": "T"}, "statistics": {"hiddenSubscriberCount": True, "viewCount": "5"}}
    report = check_response("channels.list", {"items": [item]})
    assert report.valid_items and report.availability["statistics.subscriberCount"] == 0


def test_response_without_items_means_no_results():
    assert check_response("search.list", {"pageInfo": {"totalResults": 0}}).fatal is None


# --- Cache e proveniência -------------------------------------------------------------------------

def test_cached_response_is_not_recorded_as_a_new_measurement(cfg, db):
    """Antes, cada repetição gravava views antigas com a hora atual, criando medições falsas."""
    fake = FakeYouTube(NOW, video_count=2)
    first = client(cfg, db, fake)
    collector.search_niche(first, db, cfg, "roma", NOW)
    later = NOW + timedelta(minutes=5)
    second = client(cfg, db, fake, clock=lambda: later)
    calls = len(fake.calls)
    collector.search_niche(second, db, cfg, "roma", later)
    assert len(fake.calls) == calls
    assert second.provenance()["api_calls"] == 0 and second.provenance()["cache_hits"] >= 2
    times = {row["captured_at"] for row in db.execute("SELECT captured_at FROM snapshots")}
    assert times == {NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_provenance_counts_calls_and_dates(cfg, db):
    fake = FakeYouTube(NOW, video_count=2)
    c = client(cfg, db, fake)
    c.search_videos("roma")
    c.search_videos("roma")
    data = c.provenance()
    assert data["source"] == "youtube_data_api" and data["api_calls"] == 1 and data["cache_hits"] == 1
    assert data["oldest_data_at"] == "2026-11-04T12:00:00Z" and data["methods"] == ["search.list"]


# --- Teste de conexão -----------------------------------------------------------------------------

def test_check_without_key_makes_no_call_and_stays_pending(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path, api_token="t")
    def explode(*_a):
        raise AssertionError("sem chave não abre cliente")
    result = api_status.run_check(settings, explode, NOW)
    assert not result["ok"] and result["kind"] == "no_key"
    status = api_status.status(settings, NOW)
    assert status["validation_state"] == "pendente" and status["last_real_validation"] is None and status["key_configured"] is False


def test_status_without_key_does_not_create_the_real_database(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path, api_token="t")
    api_status.status(settings, NOW)
    assert not settings.live_db_path.exists()


def test_check_success_uses_one_unit_and_validates(cfg):
    fake = FakeYouTube(NOW)
    result = api_status.run_check(cfg, factory(fake), NOW)
    assert result["ok"] and result["details"]["steps"][0]["fields"]["statistics.subscriberCount"] == 1
    assert len(fake.calls) == 1 and "forHandle" in fake.calls[0].url.params
    assert api_status.status(cfg, NOW)["validation_state"] == "validada"


def test_check_with_search_records_each_step(cfg):
    fake = FakeYouTube(NOW)
    result = api_status.run_check(cfg, factory(fake), NOW, with_search=True)
    assert [step["method"] for step in result["details"]["steps"]] == ["channels.list", "search.list", "videos.list"]
    assert result["details"]["steps"][1]["total_results_present"] is True


def test_simulated_target_never_counts_as_real_validation(tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token="t", youtube_base_url="http://127.0.0.1:9/")
    result = api_status.run_check(settings, factory(FakeYouTube(NOW)), NOW)
    assert result["ok"] and result["target"] == "simulada" and "não valida" in result["message"]
    status = api_status.status(settings, NOW)
    assert status["validation_state"] == "pendente" and status["last_real_validation"] is None


@pytest.mark.parametrize("failure,kind", [
    (httpx.Response(400, json=REAL_INVALID_KEY), "key_invalid"), (error_response(403, "accessNotConfigured"), "api_disabled"),
    (error_response(403, "quotaExceeded"), "quota"), (httpx.Response(200, text="quebrado"), "format"),
])
def test_check_failure_is_recorded_with_what_to_do(cfg, failure, kind):
    fake = FakeYouTube(NOW)
    fake.fail_next = [failure]
    result = api_status.run_check(cfg, factory(fake), NOW)
    assert not result["ok"] and result["kind"] == kind and result["action"] and result["title"]
    assert KEY not in json.dumps(result)
    assert api_status.status(cfg, NOW)["validation_state"] == "pendente"


def test_check_network_failure_is_reported(cfg):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.ConnectError("sem rede")] * 4
    assert api_status.run_check(cfg, factory(fake), NOW)["kind"] == "network"


def test_check_exhausted_local_budget_is_reported(tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token="t", quota_default_daily=0)
    assert api_status.run_check(settings, factory(FakeYouTube(NOW)), NOW)["kind"] == "quota_local"


def test_check_keeps_quota_in_real_database_even_in_demo_mode(tmp_path):
    settings = Settings(mode="demo", youtube_api_key=KEY, data_dir=tmp_path, api_token="t")
    api_status.run_check(settings, factory(FakeYouTube(NOW)), NOW)
    conn = connect(settings.live_db_path)
    assert QuotaLedger(conn, settings).used("default", NOW) == 1
    conn.close()
    assert not settings.db_path.exists()


# --- API local ------------------------------------------------------------------------------------

@pytest.fixture
def web(cfg):
    main.app.dependency_overrides[settings_dep] = lambda: cfg
    main.app.dependency_overrides[intel_router.client_factory] = lambda: factory(FakeYouTube(NOW))
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_status_route_never_exposes_the_key(web):
    response = web.get("/api/intel/api-status")
    assert response.status_code == 200 and KEY not in response.text and response.json()["key_configured"] is True


def test_check_route_requires_token(web):
    assert web.post("/api/intel/api-status/check", json={}).status_code == 401
    result = web.post("/api/intel/api-status/check", json={}, headers={"X-YTI-Token": "t"})
    assert result.status_code == 200 and result.json()["ok"] and KEY not in result.text


def test_context_reports_target(web):
    assert web.get("/api/intel/context").json()["api_target"] == "google"


# --- Endereço alternativo -------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["https://evil.example.com/", "http://192.168.0.5:9/", "http://127.0.0.1.evil.com/"])
def test_test_url_only_accepts_this_computer(monkeypatch, value):
    monkeypatch.setenv("YTI_YOUTUBE_BASE_URL", value)
    with pytest.raises(ValueError):
        loopback_base_url()


def test_test_url_accepts_loopback(monkeypatch):
    monkeypatch.setenv("YTI_YOUTUBE_BASE_URL", "http://127.0.0.1:8999/youtube/v3")
    assert loopback_base_url() == "http://127.0.0.1:8999/youtube/v3"
    assert get_settings().api_target == "simulada"


def test_default_target_is_google(tmp_path):
    assert Settings(mode="live", data_dir=tmp_path).api_target == "google"
    assert YouTubeApiError("x").kind == "api_error"
