"""Agendador: desligado até a aprovação, respeita cota, evita duplicadas, registra erros e pausa sozinho."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import demo, main
from app.config import Settings
from app.connectors.youtube_data import YouTubeDataClient
from app.db import connect, migrate, to_iso, utcnow
from app.deps import settings_dep
from app.intel import api_status, automation, keywords, research
from app.intel import router as intel_router
from app.policy import apply_retention, retention_if_due
from app.studio import store
from tests.yt_mock import REAL_INVALID_KEY, FakeYouTube, error_response

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
KEY = "AIzaTESTKEY0000000000000000"
TOKEN = "segredo"


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_default_daily=500, quota_search_daily=20)


@pytest.fixture
def db(cfg):
    conn = connect(cfg.live_db_path)
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def studio(cfg):
    conn = store.open_studio(cfg)
    store.seed_demo_once(conn)
    yield conn
    conn.close()


@pytest.fixture
def channel(studio):
    return store.create_channel(studio, {"name": "Canal Real", "language": "pt", "keywords": ["roma"]})


def factory(fake, now=NOW):
    return lambda settings, conn: YouTubeDataClient(settings, conn, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: now)


def validated(cfg, fake=None):
    """Registra uma consulta real confirmada, como o botão Testar conexão faria."""
    assert api_status.run_check(cfg, factory(fake or FakeYouTube(NOW)), NOW)["ok"]


def schedule(db, studio, cfg, channel, query="roma antiga", interval=24, **filters):
    return automation.create(db, studio, cfg, channel["id"], kind=filters.pop("kind", "recent"), query=query, filters=filters, interval_hours=interval, now=NOW)


def approved(db, cfg, limit=5):
    validated(cfg)
    automation.approve(db, cfg, limit, NOW)


# --- Desligado até aprovar ------------------------------------------------------------------------

def test_real_execution_starts_disabled_and_makes_no_call(db, studio, cfg, channel):
    schedule(db, studio, cfg, channel)
    validated(cfg)
    fake = FakeYouTube(NOW)
    result = automation.tick(db, studio, cfg, NOW, factory(fake))
    assert result["state"] == "aguardando_aprovacao" and result["ran"] == 0 and fake.calls == []
    assert db.execute("SELECT real_enabled FROM automation_settings").fetchone()["real_enabled"] == 0


def test_without_key_nothing_runs_and_approval_is_refused(tmp_path, studio):
    settings = Settings(mode="live", data_dir=tmp_path, api_token=TOKEN)
    conn = connect(settings.live_db_path)
    migrate(conn)
    assert automation.gate(conn, settings, NOW)["state"] == "sem_chave"
    with pytest.raises(store.StudioError) as caught:
        automation.approve(conn, settings, 5, NOW)
    assert caught.value.code == "api_key_missing"
    conn.close()


def test_approval_requires_a_confirmed_real_query(db, cfg):
    assert automation.gate(db, cfg, NOW)["state"] == "sem_validacao"
    with pytest.raises(store.StudioError) as caught:
        automation.approve(db, cfg, 5, NOW)
    assert caught.value.code == "validation_missing"
    validated(cfg)
    assert automation.gate(db, cfg, NOW)["state"] == "aguardando_aprovacao"
    assert automation.approve(db, cfg, 5, NOW)["state"] == "ligado"


def test_failed_check_does_not_count_as_validation(db, cfg):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.Response(400, json=REAL_INVALID_KEY)]
    api_status.run_check(cfg, factory(fake), NOW)
    with pytest.raises(store.StudioError):
        automation.approve(db, cfg, 5, NOW)


def test_simulated_check_does_not_validate_google(db, tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN)
    simulated = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, youtube_base_url="http://127.0.0.1:9/")
    api_status.run_check(simulated, factory(FakeYouTube(NOW)), NOW)
    assert automation.gate(db, settings, NOW)["state"] == "sem_validacao"


@pytest.mark.parametrize("value", [0, -1, 21, 1000])
def test_limit_must_be_reasonable(db, cfg, value):
    validated(cfg)
    with pytest.raises(store.StudioError):
        automation.approve(db, cfg, value, NOW)


def test_limit_never_passes_the_local_search_bucket(tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_search_daily=3)
    conn = connect(settings.live_db_path)
    migrate(conn)
    validated(settings)
    with pytest.raises(store.StudioError):
        automation.approve(conn, settings, 4, NOW)
    conn.close()


def test_revoke_stops_everything(db, studio, cfg, channel):
    approved(db, cfg)
    schedule(db, studio, cfg, channel)
    automation.revoke(db, cfg, NOW)
    fake = FakeYouTube(NOW)
    assert automation.tick(db, studio, cfg, NOW, factory(fake))["ran"] == 0 and fake.calls == []


def test_approval_cannot_exist_in_demo(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)
    conn = connect(settings.db_path)
    migrate(conn)
    with pytest.raises(store.StudioError) as caught:
        automation.approve(conn, settings, 5, NOW)
    assert caught.value.code == "not_needed_in_demo"
    conn.close()


def test_agent_contract_cannot_approve():
    from app.studio import mcp_server

    source = open(mcp_server.__file__, encoding="utf-8").read()
    assert "automation" not in source and "research-tick" not in source


# --- Rodar, cota e duplicadas ---------------------------------------------------------------------

def test_due_schedule_runs_and_records_history(db, studio, cfg, channel):
    approved(db, cfg)
    created = schedule(db, studio, cfg, channel, language="pt", country="BR", days=30)
    result = automation.tick(db, studio, cfg, NOW, factory(FakeYouTube(NOW)))
    assert result["ran"] == 1
    run = research.list_runs(db, channel_id=channel["id"])["items"][0]
    assert run["schedule_id"] == created["id"] and run["filters"]["country"] == "BR"
    event = automation.overview(db, studio, cfg, NOW)["events"]["items"][0]
    assert event["status"] == "ok_api" and event["run_id"] == run["id"] and "resultados" in event["message"]
    row = automation.overview(db, studio, cfg, NOW)["schedules"][0]
    assert row["last_status"] == "ok_api" and row["next_run_at"] == to_iso(NOW + timedelta(hours=24))


def test_not_due_does_not_run(db, studio, cfg, channel):
    approved(db, cfg)
    schedule(db, studio, cfg, channel)
    automation.tick(db, studio, cfg, NOW, factory(FakeYouTube(NOW)))
    fake = FakeYouTube(NOW)
    later = NOW + timedelta(hours=23)
    assert automation.tick(db, studio, cfg, later, factory(fake, later))["ran"] == 0 and fake.calls == []


def test_daily_limit_is_respected_across_ticks(db, studio, cfg, channel):
    approved(db, cfg, limit=2)
    for index in range(4):
        schedule(db, studio, cfg, channel, query=f"tema numero {index} roma")
    fake = FakeYouTube(NOW)
    assert automation.tick(db, studio, cfg, NOW, factory(fake))["ran"] == 2
    searches = sum(1 for call in fake.calls if call.url.path.endswith("/search"))
    second = automation.tick(db, studio, cfg, NOW, factory(fake))
    assert second["state"] == "limite_do_dia" and second["ran"] == 0
    assert sum(1 for call in fake.calls if call.url.path.endswith("/search")) == searches == 2
    tomorrow = NOW + timedelta(days=1)
    assert automation.tick(db, studio, cfg, tomorrow, factory(fake, tomorrow))["ran"] == 2


def test_one_tick_has_a_ceiling(db, studio, cfg, channel):
    approved(db, cfg, limit=20)
    for index in range(8):
        schedule(db, studio, cfg, channel, query=f"tema numero {index} roma")
    assert automation.tick(db, studio, cfg, NOW, factory(FakeYouTube(NOW)))["ran"] == automation.MAX_RUNS_PER_TICK


def test_recent_manual_search_avoids_duplicate(db, studio, cfg, channel):
    approved(db, cfg)
    fake = FakeYouTube(NOW)
    research.run_search(db, studio, cfg, kind="recent", query="roma antiga", channel_id=channel["id"], now=NOW, language="pt", days=7, factory=factory(fake))
    schedule(db, studio, cfg, channel, language="pt", days=7)
    before = len(fake.calls)
    result = automation.tick(db, studio, cfg, NOW + timedelta(hours=1), factory(fake, NOW + timedelta(hours=1)))
    assert result["duplicates"] == 1 and result["ran"] == 0 and len(fake.calls) == before
    assert automation.overview(db, studio, cfg, NOW)["events"]["items"][0]["status"] == "duplicada"


def test_same_search_cannot_be_scheduled_twice_in_a_channel(db, studio, cfg, channel, tmp_path):
    schedule(db, studio, cfg, channel, query="Roma  Antiga", language="pt")
    with pytest.raises(store.StudioError) as caught:
        schedule(db, studio, cfg, channel, query="roma antiga", language="pt")
    assert caught.value.code == "duplicate_schedule"
    assert schedule(db, studio, cfg, channel, query="roma antiga", language="en")["id"]


def test_cached_answer_does_not_use_the_approved_budget(db, studio, cfg, channel):
    """Outro canal já buscou o mesmo termo: a resposta vem do cache, sem gastar busca."""
    approved(db, cfg, limit=1)
    other = store.create_channel(studio, {"name": "Outro", "language": "pt"})
    fake = FakeYouTube(NOW)
    research.run_search(db, studio, cfg, kind="recent", query="roma antiga", channel_id=other["id"], now=NOW, days=7, factory=factory(fake))
    schedule(db, studio, cfg, channel, days=7)
    later = NOW + timedelta(hours=1)
    result = automation.tick(db, studio, cfg, later, factory(fake, later))
    assert result["cached"] == 1 and result["ran"] == 0
    assert automation.gate(db, cfg, later)["used_today"] == 0


# --- Erros e pausas -------------------------------------------------------------------------------

def test_quota_pauses_everything_until_next_quota_day(db, studio, cfg, channel):
    approved(db, cfg)
    schedule(db, studio, cfg, channel, query="primeiro tema roma")
    schedule(db, studio, cfg, channel, query="segundo tema roma")
    fake = FakeYouTube(NOW)
    fake.fail_next = [error_response(403, "quotaExceeded")]
    result = automation.tick(db, studio, cfg, NOW, factory(fake))
    assert result["paused"] is True and result["errors"] == 1 and len(fake.calls) == 1
    gate = automation.gate(db, cfg, NOW)
    assert gate["state"] == "pausado" and "cota" in gate["reason"]
    # Volta sozinho depois da virada, à meia-noite do Pacífico (08:00 UTC em novembro).
    assert automation.gate(db, cfg, NOW + timedelta(hours=21))["state"] == "ligado"


def test_local_budget_also_pauses(tmp_path, studio, channel):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_search_daily=1)
    conn = connect(settings.live_db_path)
    migrate(conn)
    validated(settings)
    automation.approve(conn, settings, 1, NOW)
    research.run_search(conn, studio, settings, kind="videos", query="outra coisa", channel_id=None, now=NOW, factory=factory(FakeYouTube(NOW)))
    schedule(conn, studio, settings, channel)
    assert automation.tick(conn, studio, settings, NOW, factory(FakeYouTube(NOW)))["paused"] is True
    conn.close()


@pytest.mark.parametrize("failure", [httpx.Response(400, json=REAL_INVALID_KEY), error_response(403, "accessNotConfigured")])
def test_key_problem_pauses_until_owner_resumes(db, studio, cfg, channel, failure):
    approved(db, cfg)
    schedule(db, studio, cfg, channel)
    fake = FakeYouTube(NOW)
    fake.fail_next = [failure]
    assert automation.tick(db, studio, cfg, NOW, factory(fake))["paused"] is True
    much_later = NOW + timedelta(days=30)
    assert automation.gate(db, cfg, much_later)["state"] == "pausado" and "chave" in automation.gate(db, cfg, much_later)["reason"]
    assert automation.gate(db, cfg, much_later)["paused_until"] is None
    assert automation.resume(db, cfg, much_later)["state"] == "ligado"


def test_passing_failure_is_logged_retried_and_paused_after_three(db, studio, cfg, channel):
    approved(db, cfg, limit=20)
    created = schedule(db, studio, cfg, channel)
    fake = FakeYouTube(NOW)
    moment = NOW
    for attempt in range(3):
        fake.fail_next = [httpx.ConnectError("sem rede")] * 4
        result = automation.tick(db, studio, cfg, moment, factory(fake, moment))
        assert result["errors"] == 1 and not result["paused"]
        moment += timedelta(hours=25)
    row = automation.overview(db, studio, cfg, moment)["schedules"][0]
    assert row["id"] == created["id"] and row["enabled"] is False and "3 falhas" in row["paused_reason"] and row["last_error"]
    assert automation.overview(db, studio, cfg, moment)["events"]["total"] == 3
    fake.fail_next = []
    assert automation.tick(db, studio, cfg, moment, factory(fake, moment))["ran"] == 0


def test_resuming_schedule_clears_errors(db, studio, cfg, channel):
    approved(db, cfg)
    created = schedule(db, studio, cfg, channel)
    db.execute("UPDATE research_schedules SET enabled = 0, consecutive_errors = 3, paused_reason = 'x' WHERE id = ?", (created["id"],))
    db.commit()
    row = automation.update(db, channel["id"], created["id"], enabled=True, interval_hours=None, now=NOW)
    assert row["enabled"] is True and row["consecutive_errors"] == 0 and row["paused_reason"] is None


def test_one_failure_does_not_block_the_other_schedules(db, studio, cfg, channel):
    approved(db, cfg, limit=20)
    schedule(db, studio, cfg, channel, query="primeiro tema roma")
    schedule(db, studio, cfg, channel, query="segundo tema roma")
    fake = FakeYouTube(NOW)
    fake.fail_next = [error_response(400, "badRequest")]
    result = automation.tick(db, studio, cfg, NOW, factory(fake))
    assert result["errors"] == 1 and result["ran"] == 1


def test_key_never_appears_in_history(db, studio, cfg, channel):
    approved(db, cfg)
    schedule(db, studio, cfg, channel)
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.ConnectError(f"falhou com key={KEY}")] * 4
    automation.tick(db, studio, cfg, NOW, factory(fake))
    assert KEY not in str(automation.overview(db, studio, cfg, NOW))


# --- Por canal e validação ------------------------------------------------------------------------

def test_periodicity_is_per_channel(db, studio, cfg, channel):
    other = store.create_channel(studio, {"name": "Outro", "language": "pt"})
    schedule(db, studio, cfg, channel, interval=24)
    automation.create(db, studio, cfg, other["id"], kind="recent", query="roma antiga", filters={}, interval_hours=720, now=NOW)
    assert {item["interval_label"] for item in automation.overview(db, studio, cfg, NOW)["schedules"]} == {"Todo dia", "Todo mês"}
    assert len(automation.overview(db, studio, cfg, NOW, channel["id"])["schedules"]) == 1


def test_schedule_of_other_channel_is_not_found(db, studio, cfg, channel):
    other = store.create_channel(studio, {"name": "Outro", "language": "pt"})
    created = schedule(db, studio, cfg, channel)
    with pytest.raises(store.StudioError) as caught:
        automation.update(db, other["id"], created["id"], enabled=False, interval_hours=None, now=NOW)
    assert caught.value.status == 404
    with pytest.raises(store.StudioError):
        automation.delete(db, other["id"], created["id"])


def test_fictional_channel_cannot_schedule_real_search(db, studio, cfg):
    with pytest.raises(store.StudioError) as caught:
        automation.create(db, studio, cfg, "chn_demo_cronicas", kind="recent", query="roma", filters={}, interval_hours=24, now=NOW)
    assert caught.value.code == "channel_data_mismatch"


@pytest.mark.parametrize("kwargs", [{"interval_hours": 1}, {"interval_hours": 25}, {"kind": "outro"}, {"query": "x"}, {"filters": {"country": "Brasil"}}, {"filters": {"format": "vertical"}}])
def test_invalid_schedule_is_refused(db, studio, cfg, channel, kwargs):
    base = {"kind": "recent", "query": "roma antiga", "filters": {}, "interval_hours": 24}
    with pytest.raises(store.StudioError):
        automation.create(db, studio, cfg, channel["id"], now=NOW, **{**base, **kwargs})


def test_channel_limit(db, studio, cfg, channel):
    for index in range(automation.MAX_PER_CHANNEL):
        schedule(db, studio, cfg, channel, query=f"tema {index} roma")
    with pytest.raises(store.StudioError) as caught:
        schedule(db, studio, cfg, channel, query="mais um tema")
    assert caught.value.code == "too_many_schedules"


def test_schedule_from_run_keeps_filters(db, studio, cfg, channel):
    run = research.run_search(db, studio, cfg, kind="recent", query="roma antiga", channel_id=channel["id"], now=NOW, language="pt", country="BR", days=30, factory=factory(FakeYouTube(NOW)), tags={"niche": "História", "subniche": "Mundo antigo", "discovery": True})
    created = automation.create_from_run(db, studio, cfg, channel["id"], run["id"], 168, NOW)
    assert created["filters"]["niche"] == "História" and created["filters"]["country"] == "BR" and created["interval_label"] == "Toda semana"
    other = store.create_channel(studio, {"name": "Outro", "language": "pt"})
    with pytest.raises(store.StudioError):
        automation.create_from_run(db, studio, cfg, other["id"], run["id"], 168, NOW)


# --- Modo demonstração ----------------------------------------------------------------------------

@pytest.fixture
def demo_cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def demo_db(demo_cfg):
    conn = connect(demo_cfg.db_path)
    migrate(conn)
    demo.seed_demo(conn, utcnow())
    keywords.seed_demo_terms(conn, utcnow())
    yield conn
    conn.close()


def test_demo_runs_without_network_and_is_fictional(demo_db, studio, demo_cfg):
    def explode(*_a):
        raise AssertionError("o modo demo não abre cliente")
    now = utcnow()
    automation.create(demo_db, studio, demo_cfg, "chn_demo_cronicas", kind="videos", query="roma", filters={}, interval_hours=24, now=now)
    result = automation.tick(demo_db, studio, demo_cfg, now, explode)
    assert result["ran"] == 1 and result["state"] == "demo"
    run = research.list_runs(demo_db, channel_id="chn_demo_cronicas")["items"][0]
    assert run["fictional"] and run["provenance"]["source"] == "dados_ficticios"


def test_demo_works_with_a_key_configured_without_touching_the_api(tmp_path, studio):
    settings = Settings(mode="demo", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN)
    conn = connect(settings.db_path)
    migrate(conn)
    demo.seed_demo(conn, utcnow())
    def explode(*_a):
        raise AssertionError("o modo demo não abre cliente, mesmo com chave")
    created = research.run_search(conn, studio, settings, kind="videos", query="roma", channel_id=None, now=utcnow(), factory=explode)
    assert created["fictional"] and created["result_count"] > 0
    conn.close()


# --- Retenção -------------------------------------------------------------------------------------

def test_retention_clears_totals_and_old_events_but_keeps_the_search(db, studio, cfg, channel):
    approved(db, cfg)
    schedule(db, studio, cfg, channel)
    automation.tick(db, studio, cfg, NOW, factory(FakeYouTube(NOW)))
    run = research.list_runs(db)["items"][0]
    assert run["total_results_approx"] is not None
    removed = apply_retention(db, cfg, NOW + timedelta(days=40))
    assert removed["schedule_events"] == 1 and removed["totals"] >= 1
    kept = research.get_run(db, run["id"])
    assert kept["query"] == "roma antiga" and kept["total_results_approx"] is None


def test_retention_runs_without_the_scheduler_at_most_once_a_day(db, cfg):
    assert retention_if_due(db, cfg, NOW) is not None
    assert retention_if_due(db, cfg, NOW + timedelta(hours=2)) is None
    assert retention_if_due(db, cfg, NOW + timedelta(days=2)) is not None


# --- Rotas ----------------------------------------------------------------------------------------

@pytest.fixture
def web(cfg):
    main.app.dependency_overrides[settings_dep] = lambda: cfg
    main.app.dependency_overrides[intel_router.client_factory] = lambda: factory(FakeYouTube(utcnow()), utcnow())
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_routes_protect_approval_and_tick_with_token(web):
    for path, body in (("/api/intel/automation/approve", {"max_searches_per_day": 5}), ("/api/intel/automation/tick", {}), ("/api/intel/automation/revoke", {})):
        assert web.post(path, json=body).status_code == 401


def test_route_flow(web, channel):
    headers = {"X-YTI-Token": TOKEN}
    assert web.get("/api/intel/automation").json()["gate"]["state"] == "sem_validacao"
    created = web.post(f"/api/intel/channels/{channel['id']}/schedules", json={"query": "roma antiga", "kind": "recent", "interval_hours": 168}, headers=headers)
    assert created.status_code == 201
    assert web.post("/api/intel/automation/tick", headers=headers).json()["ran"] == 0
    assert web.post("/api/intel/api-status/check", json={}, headers=headers).json()["ok"]
    assert web.post("/api/intel/automation/approve", json={"max_searches_per_day": 3}, headers=headers).json()["state"] == "ligado"
    assert web.post("/api/intel/automation/tick", headers=headers).json()["ran"] == 1
    data = web.get("/api/intel/automation").json()
    assert data["events"]["total"] == 1 and data["gate"]["used_today"] == 1 and data["quota"]["search_used"] == 1
    sid = data["schedules"][0]["id"]
    assert web.post(f"/api/intel/channels/{channel['id']}/schedules/{sid}/update", json={"enabled": False}, headers=headers).json()["enabled"] is False
    assert web.post(f"/api/intel/channels/{channel['id']}/schedules/{sid}/delete", headers=headers).json() == {"deleted": sid}
