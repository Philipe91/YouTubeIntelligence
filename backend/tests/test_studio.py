from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import demo as research_demo, main
from app.config import BACKEND_DIR, Settings
from app.db import connect, migrate
from app.studio import recommend, simulator, status, store
from app.studio.contract import Contract
from app.studio.store import StudioError

from .conftest import APPROVED

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


def valid_recommendation(**changes):
    data = {
        "subject": "O porto de Cartago", "justification": "Tema ligado ao perfil editorial do canal.",
        "sources": [{"label": "Livro de referência", "url": "https://example.org/livro"}],
        "titles": ["Título um", "Título dois", "Título três"], "thumbnail_idea": "Um porto circular visto de cima",
        "hook": "Como uma cidade escondeu sua frota?", "format": "long", "duration_seconds": 600,
        "target_audience": "Adultos curiosos", "editorial_priority": "alta", "facts_to_verify": ["Formato do porto"],
    }
    data.update(changes)
    return data


@pytest.fixture
def settings(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path)


@pytest.fixture
def db(settings):
    conn = store.open_studio(settings)
    yield conn
    conn.close()


@pytest.fixture
def clock():
    class Clock:
        now = NOW

        def __call__(self):
            return self.now

        def advance(self, **kwargs):
            self.now = self.now + timedelta(**kwargs)

    return Clock()


@pytest.fixture
def contract(db, settings, clock):
    return Contract(db, settings, clock)


def make_channel(db, name="Canal A", **fields):
    base = {"name": name, "language": "pt", "keywords": ["roma"], "formats": ["long"], "audience": "Adultos"}
    base.update(fields)
    return store.create_channel(db, base)


def make_recommendation(contract, channel_id, subject="O porto de Cartago", key=None):
    result = contract.submit_recommendation(channel_id, valid_recommendation(subject=subject), key or f"rec-{channel_id}-{subject}", "agente")
    return result["recommendation"]


def ready_job(contract, db, channel=None, simulated=True, authorize=True):
    channel = channel or make_channel(db)
    recommendation = make_recommendation(contract, channel["id"])
    job = contract.start_production(channel["id"], recommendation["id"], f"start-{channel['id']}", "agente", simulated)["job"]
    if authorize:
        contract.authorize_job(job["id"], channel["id"])
    return channel, job


# --- Cadastro e configurações ------------------------------------------------------------------

def test_create_read_update_channel_with_strategic_context(db):
    channel = make_channel(db, niche="História", positioning="Humor seco", avoid=["política"], topic_backlog=["Tema 1", "Tema 1 ", " "])
    assert channel["id"].startswith("chn_") and channel["is_demo"] is False
    assert channel["topic_backlog"] == ["Tema 1"], "remove repetidos e vazios"
    updated = store.update_channel(db, channel["id"], {"audience": "Jovens", "auto_production": "off", "language": "es"})
    assert updated["audience"] == "Jovens" and updated["automation"]["auto_production"] == "off" and updated["language"] == "es"
    assert updated["positioning"] == "Humor seco", "não apaga o que não foi enviado"


@pytest.mark.parametrize("fields,code", [
    ({"name": "  "}, "invalid_field"),
    ({"name": "x", "youtube_channel_id": "abc"}, "invalid_field"),
    ({"name": "x", "language": "português"}, "invalid_field"),
    ({"name": "x", "formats": ["reels"]}, "invalid_field"),
    ({"name": "x", "formats": []}, "invalid_field"),
    ({"name": "x", "auto_production": "publicar"}, "invalid_field"),
    ({"name": "x", "cadence_per_week": -1}, "invalid_field"),
    ({"name": "x", "is_demo": True}, "unknown_field"),
    ({"name": "x", "id": "outro"}, "unknown_field"),
])
def test_invalid_channel_fields_are_rejected(db, fields, code):
    with pytest.raises(StudioError) as caught:
        store.create_channel(db, fields)
    assert caught.value.code == code


def test_publishing_cannot_be_enabled(db):
    channel = make_channel(db)
    assert channel["automation"]["publishing"] == "desativada"
    with pytest.raises(StudioError):
        store.update_channel(db, channel["id"], {"auto_publishing": "on"})
    with pytest.raises(StudioError):
        store.update_channel(db, channel["id"], {"publishing": "on"})


def test_youtube_id_is_unique_between_channels(db):
    youtube_id = "UC" + "a" * 22
    make_channel(db, youtube_channel_id=youtube_id)
    with pytest.raises(StudioError) as caught:
        make_channel(db, name="Outro", youtube_channel_id=youtube_id)
    assert caught.value.code == "duplicate_channel"


def test_removal_requires_exact_name_and_no_active_jobs(db, contract):
    channel, job = ready_job(contract, db)
    with pytest.raises(StudioError) as wrong:
        store.delete_channel(db, channel["id"], "nome errado")
    assert wrong.value.code == "confirmation_mismatch"
    with pytest.raises(StudioError) as active:
        store.delete_channel(db, channel["id"], channel["name"])
    assert active.value.code == "channel_has_active_jobs"
    contract.cancel_job(job["id"], channel["id"])
    store.delete_channel(db, channel["id"], channel["name"])
    assert db.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM production_jobs").fetchone()[0] == 0, "remove em cascata"


# --- Separação entre canais ---------------------------------------------------------------------

def test_channels_do_not_see_each_others_data(db, contract):
    a, b = make_channel(db, name="A"), make_channel(db, name="B")
    competitor = store.add_competitor(db, a["id"], "Rival", None, "")
    video = store.add_history(db, a["id"], title="Vídeo de A", format="long", published_on="2026-01-01", url=None, views=10, result_notes="")
    entry = store.add_calendar(db, a["id"], scheduled_on="2026-12-01", title="Plano de A", format="long")
    recommendation = make_recommendation(contract, a["id"])

    assert store.list_competitors(db, b["id"]) == []
    assert store.list_history(db, b["id"]) == []
    assert store.list_recommendations(db, b["id"]) == []
    assert store.list_calendar(db, b["id"], "2026-01-01", "2027-01-01") == []
    context = contract.get_channel_context(b["id"], "agente")
    assert "Vídeo de A" not in json.dumps(context, ensure_ascii=False) and "Rival" not in json.dumps(context, ensure_ascii=False)

    for table, item in (("competitors", competitor), ("video_history", video), ("calendar_entries", entry)):
        with pytest.raises(StudioError):
            store.remove_scoped(db, table, b["id"], item["id"])
    with pytest.raises(StudioError):
        store.update_calendar(db, b["id"], entry["id"], status="cancelado")
    with pytest.raises(StudioError):
        store.set_recommendation_status(db, b["id"], recommendation["id"], "descartada")
    with pytest.raises(StudioError) as caught:
        contract.start_production(b["id"], recommendation["id"], "k-cross", "agente")
    assert caught.value.code == "recommendation_not_in_channel"
    with pytest.raises(StudioError):
        store.add_calendar(db, b["id"], scheduled_on="2026-12-01", title="x", format="long", recommendation_id=recommendation["id"])
    assert len(store.list_competitors(db, a["id"])) == 1 and len(store.list_history(db, a["id"])) == 1


def test_human_job_actions_check_channel(db, contract):
    channel, job = ready_job(contract, db, authorize=False)
    other = make_channel(db, name="Outro")
    with pytest.raises(StudioError) as caught:
        contract.authorize_job(job["id"], other["id"])
    assert caught.value.code == "job_not_found"
    with pytest.raises(StudioError):
        contract.get_job(job["id"], other["id"])
    assert contract.list_jobs(other["id"])["jobs"] == []


# --- Persistência --------------------------------------------------------------------------------

def test_data_persists_between_connections(settings, db):
    channel = make_channel(db, name="Persistente")
    db.close()
    again = store.open_studio(settings)
    assert store.get_channel(again, channel["id"])["name"] == "Persistente"
    again.close()


def test_studio_is_independent_from_mode_and_demo_reset(tmp_path):
    demo_settings = Settings(mode="demo", data_dir=tmp_path)
    live_settings = Settings(mode="live", data_dir=tmp_path)
    assert demo_settings.studio_db_path == live_settings.studio_db_path != demo_settings.db_path
    studio = store.open_studio(demo_settings)
    channel = make_channel(studio, name="Meu canal real")
    research = connect(demo_settings.db_path)
    migrate(research)
    research_demo.seed_demo(research, NOW)
    research_demo.reset_demo(research, NOW)
    research.close()
    studio.close()
    studio = store.open_studio(live_settings)
    assert store.get_channel(studio, channel["id"])["name"] == "Meu canal real"
    studio.close()


def test_demo_seed_is_labelled_and_does_not_return_after_removal(db):
    assert store.seed_demo_once(db, NOW) is True
    channels = store.list_channels(db)
    assert len(channels) == 3 and all(c["is_demo"] for c in channels)
    assert all("fict" in c["name"] for c in channels)
    assert {row["source"] for row in db.execute("SELECT source FROM video_history")} == {"demo"}
    target = channels[0]
    store.delete_channel(db, target["id"], target["name"])
    assert store.seed_demo_once(db, NOW) is False
    assert len(store.list_channels(db)) == 2


def test_migrations_are_idempotent(settings, db):
    assert migrate(db, store.MIGRATIONS) == []


# --- Contrato: idempotência ------------------------------------------------------------------------

def test_same_key_and_content_replays_without_duplicating(db, contract):
    channel = make_channel(db)
    recommendation = make_recommendation(contract, channel["id"])
    first = contract.start_production(channel["id"], recommendation["id"], "chave-1", "agente")
    second = contract.start_production(channel["id"], recommendation["id"], "chave-1", "agente")
    assert first["job"]["id"] == second["job"]["id"]
    assert first["replayed"] is False and second["replayed"] is True
    assert db.execute("SELECT COUNT(*) FROM production_jobs").fetchone()[0] == 1


def test_same_key_with_other_content_is_refused(db, contract):
    channel = make_channel(db)
    recommendation = make_recommendation(contract, channel["id"])
    contract.start_production(channel["id"], recommendation["id"], "chave-1", "agente", True)
    with pytest.raises(StudioError) as caught:
        contract.start_production(channel["id"], recommendation["id"], "chave-1", "agente", False)
    assert caught.value.code == "idempotency_conflict"


def test_missing_key_is_refused(db, contract):
    channel = make_channel(db)
    recommendation = make_recommendation(contract, channel["id"])
    with pytest.raises(StudioError) as caught:
        contract.start_production(channel["id"], recommendation["id"], "", "agente")
    assert caught.value.code == "idempotency_key_required"


def test_failed_operation_rolls_back_and_key_stays_free(db, contract):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a1", "c1")["lease_token"]
    with pytest.raises(StudioError):
        contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://ok"}, {"kind": "invalido", "path": "simulado://x"}], "d1")
    assert db.execute("SELECT COUNT(*) FROM job_artifacts").fetchone()[0] == 0, "entrega parcial é desfeita"
    assert contract.get_job(job["id"])["job"]["state"] == "running"
    done = contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://ok"}], "d2")
    assert done["job"]["state"] == "delivered"


def test_duplicate_agent_recommendation_is_refused_with_new_key(db, contract):
    channel = make_channel(db)
    make_recommendation(contract, channel["id"], key="k1")
    with pytest.raises(StudioError) as caught:
        make_recommendation(contract, channel["id"], key="k2")
    assert caught.value.code == "duplicate_recommendation"


# --- Contrato: autorização e automação -------------------------------------------------------------

def test_agent_cannot_claim_before_owner_authorizes(db, contract):
    channel, job = ready_job(contract, db, authorize=False)
    assert job["state"] == "awaiting_authorization"
    with pytest.raises(StudioError) as caught:
        contract.claim_job(job["id"], "a1", "c1")
    assert caught.value.code == "not_authorized"
    contract.authorize_job(job["id"], channel["id"])
    assert contract.claim_job(job["id"], "a1", "c2")["job"]["state"] == "running"


def test_real_job_always_needs_owner_even_in_auto_mode(db, contract):
    channel = make_channel(db, auto_production="auto_simulated")
    simulated = contract.start_production(channel["id"], make_recommendation(contract, channel["id"], "Tema um")["id"], "k1", "agente", True)["job"]
    real = contract.start_production(channel["id"], make_recommendation(contract, channel["id"], "Tema dois")["id"], "k2", "agente", False)["job"]
    assert simulated["state"] == "authorized" and real["state"] == "awaiting_authorization"


@pytest.mark.parametrize("field,action", [
    ("auto_production", lambda c, ch, rec: c.start_production(ch, rec, "k", "agente")),
    ("auto_briefing", lambda c, ch, rec: c.get_next_briefing(ch, "agente")),
    ("auto_research", lambda c, ch, rec: c.submit_recommendation(ch, valid_recommendation(subject="Outro tema"), "k", "agente")),
])
def test_automation_controls_are_enforced_per_channel(db, contract, field, action):
    channel = make_channel(db)
    other = make_channel(db, name="Outro")
    recommendation = make_recommendation(contract, channel["id"])
    store.update_channel(db, channel["id"], {field: "off"})
    with pytest.raises(StudioError) as caught:
        action(contract, channel["id"], recommendation["id"])
    assert caught.value.code == "automation_off"
    assert contract.submit_recommendation(other["id"], valid_recommendation(), "k-outro", "agente"), "o outro canal segue ligado"


def test_package_automation_off_blocks_package(db, contract):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a1", "c1")["lease_token"]
    artifact = contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")["artifacts"][0]
    store.update_channel(db, channel["id"], {"auto_package": "off"})
    with pytest.raises(StudioError) as caught:
        contract.prepare_publish_package(job["id"], "T", "D", [], artifact["id"], "p1")
    assert caught.value.code == "automation_off"


# --- Contrato: falhas e recuperação ------------------------------------------------------------------

def test_expired_lease_returns_job_to_queue_and_old_token_is_fenced(db, contract, clock):
    channel, job = ready_job(contract, db)
    old = contract.claim_job(job["id"], "a1", "c1", lease_seconds=60)["lease_token"]
    clock.advance(seconds=61)
    with pytest.raises(StudioError) as expired:
        contract.update_progress(job["id"], old, 10, "x", "u1")
    assert expired.value.code == "lease_expired" and expired.value.retryable
    state = contract.get_job(job["id"])
    assert state["job"]["state"] == "authorized"
    assert any(e["kind"] == "recovery" for e in state["events"])
    new = contract.claim_job(job["id"], "a2", "c2")["lease_token"]
    assert new != old
    with pytest.raises(StudioError) as fenced:
        contract.update_progress(job["id"], old, 50, "agente antigo", "u2")
    assert fenced.value.code == "lease_lost"
    assert contract.get_job(job["id"])["job"]["progress"] == 0


def test_attempts_are_limited_and_owner_can_reopen(db, contract, clock):
    channel, job = ready_job(contract, db)
    for attempt in range(3):
        contract.claim_job(job["id"], "a", f"c{attempt}", lease_seconds=30)
        clock.advance(seconds=31)
        contract.recover_stale()
    state = contract.get_job(job["id"])["job"]
    assert state["state"] == "failed" and state["attempts"] == 3
    with pytest.raises(StudioError):
        contract.claim_job(job["id"], "a", "c-depois")
    contract.retry_job(job["id"], channel["id"])
    assert contract.claim_job(job["id"], "a", "c-reaberto")["job"]["attempts"] == 1


def test_heartbeat_keeps_lease_alive(db, contract, clock):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a", "c1", lease_seconds=60)["lease_token"]
    clock.advance(seconds=50)
    contract.update_progress(job["id"], token, 30, "etapa", "u1", lease_seconds=60)
    clock.advance(seconds=50)
    assert contract.recover_stale() == []
    assert contract.get_job(job["id"])["job"]["state"] == "running"


def test_retryable_failure_requeues_and_final_failure_waits_for_owner(db, contract):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    assert contract.report_failure(job["id"], token, "erro temporário", True, "f1")["will_retry"] is True
    token = contract.claim_job(job["id"], "a", "c2")["lease_token"]
    result = contract.report_failure(job["id"], token, "erro definitivo", False, "f2")
    assert result["will_retry"] is False and result["job"]["state"] == "failed"
    assert result["job"]["last_error"] == "erro definitivo"


def test_two_agents_cannot_claim_the_same_job(db, settings, clock):
    other_conn = store.open_studio(settings)
    first, second = Contract(db, settings, clock), Contract(other_conn, settings, clock)
    channel, job = ready_job(first, db)
    first.claim_job(job["id"], "a1", "c1")
    with pytest.raises(StudioError) as caught:
        second.claim_job(job["id"], "a2", "c2")
    assert caught.value.code == "job_not_claimable"
    other_conn.close()


def test_lease_token_is_not_exposed_by_read_operations(db, contract):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    assert token not in json.dumps(contract.get_job(job["id"]), default=str)
    assert token not in json.dumps(contract.list_jobs(), default=str)


def test_logs_remove_secrets(db, contract):
    channel, job = ready_job(contract, db)
    contract.log_event(job["id"], "error", "falhou com key=SEGREDO123 e Bearer abc.def", "l1", {"url": "https://x?key=OUTROSEGREDO"}, "a")
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    contract.report_failure(job["id"], token, "token refresh_token=ZZZ999 inválido", False, "f1")
    dump = "\n".join(db.iterdump())
    for secret in ("SEGREDO123", "abc.def", "OUTROSEGREDO", "ZZZ999"):
        assert secret not in dump.replace("idempotency", "")


def test_log_event_is_idempotent(db, contract):
    channel, job = ready_job(contract, db)
    contract.log_event(job["id"], "info", "uma vez", "l1")
    contract.log_event(job["id"], "info", "uma vez", "l1")
    assert db.execute("SELECT COUNT(*) FROM job_events WHERE message = 'uma vez'").fetchone()[0] == 1


# --- Contrato: entrega ----------------------------------------------------------------------------

def test_simulated_job_rejects_real_files(db, contract, tmp_path):
    channel, job = ready_job(contract, db)
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    real = tmp_path / "v.mp4"
    real.write_bytes(b"x")
    with pytest.raises(StudioError) as caught:
        contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": str(real)}], "d1")
    assert caught.value.code == "invalid_artifact"


def test_real_job_validates_root_existence_and_hash(db, settings, clock, tmp_path):
    root = tmp_path / "saida"
    root.mkdir()
    video = root / "v.mp4"
    video.write_bytes(b"conteudo")
    outside = tmp_path / "fora.mp4"
    outside.write_bytes(b"x")
    contract = Contract(db, dataclasses.replace(settings, artifact_roots=(str(root),)), clock)
    channel, job = ready_job(contract, db, simulated=False)
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    for path, code, key in ((str(outside), "artifact_outside_root", "d1"), (str(root / "nao.mp4"), "artifact_missing", "d2"), ("simulado://v", "invalid_artifact", "d3")):
        with pytest.raises(StudioError) as caught:
            contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": path}], key)
        assert caught.value.code == code
    stored = contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": str(video)}], "d4")["artifacts"][0]
    assert stored["sha256"] == hashlib.sha256(b"conteudo").hexdigest() and stored["size_bytes"] == 8 and stored["simulated"] is False


def test_real_delivery_requires_configured_root(db, contract, tmp_path):
    channel, job = ready_job(contract, db, simulated=False)
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    with pytest.raises(StudioError) as caught:
        contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": str(tmp_path / "x")}], "d1")
    assert caught.value.code == "artifact_root_not_configured"


# --- Contrato: pacote, sem publicação ------------------------------------------------------------------

def test_package_stops_at_human_review_and_never_publishes(db, contract):
    channel, job = ready_job(contract, db)
    store.add_calendar(db, channel["id"], scheduled_on="2026-12-01", title="x", format="long", recommendation_id=job["recommendation_id"])
    db.execute("UPDATE calendar_entries SET job_id = ?", (job["id"],))
    db.commit()
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    artifact = contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")["artifacts"][0]
    result = contract.prepare_publish_package(job["id"], "Título", "Descrição", ["a"], artifact["id"], "p1")
    assert result["published"] is False
    assert result["package"]["state"] == "ready_for_human_review"
    assert any("manualmente" in item for item in result["package"]["checklist"])
    state = contract.get_job(job["id"])["job"]["state"]
    assert state == "package_ready"
    assert db.execute("SELECT status FROM calendar_entries").fetchone()["status"] == "pronto_para_revisao"
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE publish_packages SET state = 'published'")
    db.rollback()


def test_package_requires_delivered_job_and_own_artifact(db, contract):
    channel, job = ready_job(contract, db)
    with pytest.raises(StudioError) as early:
        contract.prepare_publish_package(job["id"], "T", "D", [], "art_x", "p0")
    assert early.value.code == "job_not_delivered"
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")
    with pytest.raises(StudioError) as foreign:
        contract.prepare_publish_package(job["id"], "T", "D", [], "art_de_outra_tarefa", "p1")
    assert foreign.value.code == "artifact_not_in_job"


def test_contract_has_no_publish_or_owner_operations_as_agent_tools():
    code = (BACKEND_DIR / "app" / "studio" / "mcp_server.py").read_text(encoding="utf-8")
    tools = [line.split("def ")[1].split("(")[0] for line, previous in zip(code.splitlines()[1:], code.splitlines()) if "@server.tool()" in previous]
    assert len(tools) == 17
    for forbidden in ("publish", "upload", "insert", "authorize", "cancel", "retry"):
        assert not [t for t in tools if forbidden in t and t != "prepare_publish_package"], forbidden


# --- Simulador -----------------------------------------------------------------------------------

def test_simulator_walks_the_contract_to_review_package_without_files(db, contract, tmp_path):
    channel, job = ready_job(contract, db)
    states = []
    for _ in range(8):
        states.append(simulator.simulate_step(contract, job["id"], channel["id"])["job"]["state"])
    assert states[0] == "running" and states[-1] == "package_ready"
    final = contract.get_job(job["id"])
    assert final["job"]["simulated"] is True and final["job"]["progress"] == 100
    assert final["job"]["state_label"] == "PRONTO PARA REVISÃO"
    assert all(a["simulated"] for a in final["artifacts"])
    real = [a for a in final["artifacts"] if not a["path"].startswith("simulado://")]
    assert len(real) == 1 and real[0]["sha256"] and real[0]["path"].endswith("resultado_teste.txt"), "só um arquivo de texto de teste"
    assert final["package"]["state"] == "ready_for_human_review"
    with pytest.raises(StudioError) as caught:
        simulator.simulate_step(contract, job["id"], channel["id"])
    assert caught.value.code == "nothing_to_simulate"


def test_simulator_failure_then_recovery(db, contract):
    channel, job = ready_job(contract, db)
    simulator.simulate_step(contract, job["id"], channel["id"])
    simulator.simulate_step(contract, job["id"], channel["id"])
    failed = simulator.simulate_failure(contract, job["id"], channel["id"])
    assert failed["job"]["state"] == "authorized" and failed["job"]["last_error"]
    resumed = simulator.simulate_step(contract, job["id"], channel["id"])
    assert resumed["job"]["state"] == "running" and resumed["job"]["attempts"] == 2


def test_simulator_refuses_real_jobs(db, contract):
    channel, job = ready_job(contract, db, simulated=False)
    with pytest.raises(StudioError) as caught:
        simulator.simulate_step(contract, job["id"], channel["id"])
    assert caught.value.code == "not_simulated"


# --- Inteligência por canal ----------------------------------------------------------------------------

@pytest.fixture
def research(settings):
    conn = connect(settings.db_path)
    migrate(conn)
    research_demo.seed_demo(conn, NOW)
    yield conn
    conn.close()


REQUIRED_FIELDS = ("subject", "justification", "sources", "titles", "thumbnail_idea", "hook", "format", "duration_seconds", "target_audience", "editorial_priority")


def test_demo_channel_crosses_fictional_research_and_labels_it(db, research, settings):
    store.seed_demo_once(db, NOW)
    created = recommend.generate(db, research, settings, "chn_demo_cronicas")["created"]
    assert created
    metric = [r for r in created if r["data_basis"] == "demo_metrics"]
    assert metric, "deve cruzar com a pesquisa fictícia"
    for item in metric:
        assert "fictícios" in item["justification"] and all(s["fictional"] for s in item["sources"])
    for item in created:
        for field in REQUIRED_FIELDS:
            assert item[field], field
        assert len(item["titles"]) == 3
        assert item["format"] in {"long", "short"}


def test_real_channel_never_uses_fictional_data_or_scores(db, research, settings):
    channel = make_channel(db, name="Meu canal real", keywords=["roma", "cartago"], topic_backlog=["O porto de Cartago"], positioning="Histórias curtas")
    created = recommend.generate(db, research, settings, channel["id"])["created"]
    assert created
    for item in created:
        assert item["data_basis"] == "editorial"
        assert "pontuação" not in item["justification"].lower()
        assert not any(s["fictional"] for s in item["sources"])
        assert not any(s["kind"] in {"demo", "pesquisa"} for s in item["sources"])


def test_live_restricted_real_channel_is_editorial_only_even_with_searches(db, tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path)
    research = connect(settings.db_path)
    migrate(research)
    research.execute("INSERT INTO searches (query, language, executed_at) VALUES ('roma antiga', 'pt', '2026-11-01T00:00:00Z')")
    research.commit()
    channel = make_channel(db, keywords=["roma"], topic_backlog=["Roma imperial"])
    created = recommend.generate(db, research, settings, channel["id"])["created"]
    assert created and all(r["data_basis"] == "editorial" for r in created)
    assert any(s["kind"] == "pesquisa" and "roma antiga" in s["label"] and not s["fictional"] for r in created for s in r["sources"])
    research.close()


def test_live_approved_real_channel_labels_metrics_as_own(db, tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path, compliance=APPROVED)
    research = connect(settings.db_path)
    migrate(research)
    research_demo.seed_demo(research, NOW)  # Base de teste: só importa a origem do rótulo.
    channel = make_channel(db, keywords=["roma", "vikings", "samurais"], formats=["long", "short"])
    created = recommend.generate(db, research, settings, channel["id"])["created"]
    metric = [r for r in created if r["data_basis"] == "approved_metrics"]
    assert metric and all("não pelo YouTube" in r["justification"] for r in metric)
    research.close()


def test_generation_is_idempotent_and_respects_avoid_list_and_history(db, research, settings):
    channel = make_channel(db, keywords=["roma", "política", "egito"], avoid=["política"], topic_backlog=["Tema A", "Política de Roma"])
    store.add_history(db, channel["id"], title="Egito em 5 minutos", format="long", published_on="2026-01-01", url=None, views=None, result_notes="")
    first = recommend.generate(db, research, settings, channel["id"])["created"]
    subjects = {r["subject"] for r in first}
    assert "Tema A" in subjects and "Roma" in subjects
    assert "Política" not in subjects and "Política de Roma" not in subjects, "tema evitado"
    assert "Egito" not in subjects, "já coberto no histórico"
    assert recommend.generate(db, research, settings, channel["id"])["created"] == []


def test_recommendations_are_specific_to_each_channel(db, research, settings):
    a = make_channel(db, name="A", topic_backlog=["Tema exclusivo de A"], audience="Público de A")
    b = make_channel(db, name="B", topic_backlog=["Tema exclusivo de B"], audience="Público de B", language="es")
    recommend.generate(db, research, settings, a["id"])
    recommend.generate(db, research, settings, b["id"])
    subjects_a = {r["subject"] for r in store.list_recommendations(db, a["id"])}
    items_b = store.list_recommendations(db, b["id"])
    assert "Tema exclusivo de B" not in subjects_a
    assert {r["target_audience"] for r in items_b} == {"Público de B"}
    assert any("la historia" in r["titles"][0] for r in items_b), "respeita o idioma do canal"


@pytest.mark.parametrize("change", [
    {"titles": ["um", "dois"]}, {"titles": ["um", "dois", "três", "quatro"]}, {"sources": []}, {"format": "reels"},
    {"editorial_priority": "urgente"}, {"score": 99}, {"predicted_views": 100000}, {"sources": [{"label": "x", "url": "javascript:alert(1)"}]},
])
def test_agent_recommendation_validation_rejects_scores_and_bad_data(db, contract, change):
    channel = make_channel(db)
    with pytest.raises(StudioError) as caught:
        contract.submit_recommendation(channel["id"], valid_recommendation(**change), "k1", "agente")
    assert caught.value.code == "invalid_payload"


def test_agent_recommendation_respects_profile(db, contract):
    channel = make_channel(db, formats=["short"], avoid=["guerra"])
    with pytest.raises(StudioError) as format_error:
        contract.submit_recommendation(channel["id"], valid_recommendation(format="long"), "k1", "a")
    assert format_error.value.code == "format_not_in_profile"
    with pytest.raises(StudioError) as avoided:
        contract.submit_recommendation(channel["id"], valid_recommendation(format="short", subject="A guerra de Troia"), "k2", "a")
    assert avoided.value.code == "subject_avoided"


def test_agent_sources_are_marked_unverified(db, contract):
    channel = make_channel(db)
    item = make_recommendation(contract, channel["id"])
    assert item["sources"][0]["verified"] is False and item["origin"] == "agente"


def test_briefing_prefers_owner_accepted_and_labels_fiction(db, contract):
    channel = make_channel(db)
    assert contract.get_next_briefing(channel["id"], "a")["briefing"] is None
    make_recommendation(contract, channel["id"], "Primeiro tema")
    second = make_recommendation(contract, channel["id"], "Segundo tema")
    store.set_recommendation_status(db, channel["id"], second["id"], "aceita")
    result = contract.get_next_briefing(channel["id"], "a")
    assert result["briefing"]["recommendation_id"] == second["id"] and result["briefing"]["accepted_by_owner"] is True
    assert result["briefing"]["fictional"] is False
    assert "Não publicar." in result["constraints"]
    store.seed_demo_once(db, NOW)
    Contract(db, contract.settings).submit_recommendation("chn_demo_rotas", valid_recommendation(), "k9", "a")
    assert contract.get_next_briefing("chn_demo_rotas", "a")["briefing"]["fictional"] is True


# --- Estado das integrações -----------------------------------------------------------------------------

def test_youtube_auth_status_paths(db, tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path)
    store.seed_demo_once(db, NOW)
    assert status.youtube_auth_status(store.get_channel(db, "chn_demo_rotas"), settings)["state"] == "demo"
    channel = make_channel(db)
    assert status.youtube_auth_status(channel, settings)["state"] == "not_linked"
    linked = make_channel(db, name="L", youtube_channel_id="UC" + "b" * 22)
    assert status.youtube_auth_status(linked, settings)["state"] == "oauth_not_configured"
    configured = dataclasses.replace(settings, oauth_client_secrets="x.json")
    assert status.youtube_auth_status(linked, configured)["state"] == "not_authorized"
    live = connect(settings.live_db_path)
    migrate(live)
    live.execute("INSERT INTO channels (id, title, text_refreshed_at, created_at) VALUES (?, 't', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')", (linked["youtube_channel_id"],))
    live.execute("INSERT INTO oauth_channels VALUES (?, 's', '2020-01-01T00:00:00Z', '2020-01-01T00:00:00Z')", (linked["youtube_channel_id"],))
    live.commit()
    assert status.youtube_auth_status(linked, configured)["state"] == "check_overdue"
    live.execute("UPDATE oauth_channels SET last_authorization_check_at = '2099-01-01T00:00:00Z'")
    live.commit()
    assert status.youtube_auth_status(linked, configured)["state"] == "authorized"
    live.close()


def test_claude_status_reports_activity_without_calling_anything(db, contract):
    channel = make_channel(db)
    assert status.claude_status(db, channel["id"])["simulated_only"] is None
    contract.get_channel_context(channel["id"], "agente_simulado")
    assert status.claude_status(db, channel["id"])["simulated_only"] is True
    contract.get_channel_context(channel["id"], "claude-code")
    assert status.claude_status(db, channel["id"])["simulated_only"] is False


# --- API do dashboard ------------------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path)
    main.app.dependency_overrides[main.settings_dep] = lambda: settings
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_api_multichannel_flow_from_registration_to_package(api):
    overview = api.get("/api/studio/overview").json()
    assert len(overview["channels"]) == 3 and all(c["is_demo"] for c in overview["channels"])
    created = api.post("/api/studio/channels", json={"fields": {"name": "Canal novo", "language": "pt", "keywords": ["roma"], "topic_backlog": ["Roma à noite"], "formats": ["long"]}})
    assert created.status_code == 201
    channel_id = created.json()["id"]
    assert api.patch(f"/api/studio/channels/{channel_id}", json={"fields": {"audience": "Adultos", "niche": "História"}}).json()["niche"] == "História"
    assert api.post(f"/api/studio/channels/{channel_id}/competitors", json={"name": "Rival"}).status_code == 201
    assert api.post(f"/api/studio/channels/{channel_id}/history", json={"title": "Vídeo antigo", "format": "long", "published_on": "2026-01-01", "views": 100}).status_code == 201
    generated = api.post(f"/api/studio/channels/{channel_id}/recommendations/generate").json()["created"]
    assert generated and all(r["data_basis"] == "editorial" for r in generated)
    recommendation = next(r for r in generated if r["subject"] == "Roma à noite")
    assert api.post(f"/api/studio/channels/{channel_id}/recommendations/{recommendation['id']}/status", json={"status": "aceita"}).status_code == 200
    assert api.post(f"/api/studio/channels/{channel_id}/calendar", json={"scheduled_on": "2030-01-10", "title": "Roma à noite", "format": "long", "recommendation_id": recommendation["id"]}).status_code == 201
    job = api.post(f"/api/studio/channels/{channel_id}/recommendations/{recommendation['id']}/produce", json={"simulated": True}).json()["job"]
    assert job["state"] == "awaiting_authorization"
    assert api.post(f"/api/studio/channels/{channel_id}/jobs/{job['id']}/simulate-step").status_code == 409, "sem autorização não anda"
    assert api.post(f"/api/studio/channels/{channel_id}/jobs/{job['id']}/authorize").status_code == 200
    for _ in range(8):
        final = api.post(f"/api/studio/channels/{channel_id}/jobs/{job['id']}/simulate-step")
        assert final.status_code == 200
    assert final.json()["job"]["state"] == "package_ready"
    detail = api.get(f"/api/studio/channels/{channel_id}").json()
    assert detail["packages_ready"] == 1 and detail["competitors"][0]["name"] == "Rival" and detail["history"][0]["views"] == 100
    assert detail["youtube_auth"]["state"] == "not_linked"
    entries = api.get("/api/studio/calendar", params={"start": "2030-01-01", "end": "2030-01-31", "channel_id": channel_id}).json()["entries"]
    assert entries[0]["status"] == "pronto_para_revisao"


def test_cancelled_recommendation_can_be_sent_again_with_new_key(db, contract):
    channel, job = ready_job(contract, db)
    contract.cancel_job(job["id"], channel["id"])
    recommendation = store.list_recommendations(db, channel["id"])[0]
    assert recommendation["status"] == "aceita"
    assert "updated_at" in recommendation, "a interface usa este campo para compor a chave do formulário"
    again = contract.start_production(channel["id"], recommendation["id"], f"ui:{recommendation['id']}:novo", "dono_local")
    assert again["replayed"] is False and again["job"]["id"] != job["id"]


def test_demo_activity_is_seeded_once_labelled_and_only_on_fictional_channels(api, tmp_path):
    overview = api.get("/api/studio/overview").json()
    assert overview["jobs"], "a fila de demonstração não começa vazia"
    assert all(job["simulated"] for job in overview["jobs"])
    assert all(job["channel_is_demo"] for job in overview["jobs"])
    assert all(channel["open_recommendations"] >= 0 for channel in overview["channels"])
    assert any(channel["open_recommendations"] > 0 for channel in overview["channels"])
    first_count = len(overview["jobs"])
    real = api.post("/api/studio/channels", json={"fields": {"name": "Canal real", "keywords": ["roma"]}}).json()
    assert api.get(f"/api/studio/channels/{real['id']}/recommendations").json()["items"] == [], "canal novo não herda nada"
    assert len(api.get("/api/studio/overview").json()["jobs"]) == first_count, "não recria a cada acesso"
    # Depois de removidos, os fictícios não voltam.
    for channel in overview["channels"]:
        for job in api.get("/api/studio/jobs", params={"channel_id": channel["id"]}).json()["jobs"]:
            api.post(f"/api/studio/channels/{channel['id']}/jobs/{job['id']}/cancel")
        assert api.post(f"/api/studio/channels/{channel['id']}/delete", json={"confirm_name": channel["name"]}).status_code == 200
    remaining = api.get("/api/studio/overview").json()
    assert [c["name"] for c in remaining["channels"]] == ["Canal real"] and remaining["jobs"] == []


def test_titles_read_naturally_with_any_subject(db, research, settings):
    channel = make_channel(db, keywords=["vikings"], topic_backlog=["O último dia de Cartago"], tone="Direto")
    created = {r["subject"]: r for r in recommend.generate(db, research, settings, channel["id"])["created"]}
    assert created["O último dia de Cartago"]["titles"][0] == "O último dia de Cartago: a história pouco contada"
    assert "Vikings" in created, "assunto começa com maiúscula"
    assert created["Vikings"]["thumbnail_idea"].endswith("Tom: Direto.")
    assert " de O " not in " ".join(created["O último dia de Cartago"]["titles"])


def test_api_errors_are_structured_and_unknown_action_is_refused(api):
    missing = api.get("/api/studio/channels/nao-existe")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "channel_not_found"
    channel_id = api.post("/api/studio/channels", json={"fields": {"name": "X"}}).json()["id"]
    assert api.post(f"/api/studio/channels/{channel_id}/jobs/job_x/publish").status_code == 404
    assert api.post("/api/studio/channels", json={"fields": {"name": ""}}).status_code == 400
    assert api.post(f"/api/studio/channels/{channel_id}/delete", json={"confirm_name": "errado"}).status_code == 400
    assert api.post(f"/api/studio/channels/{channel_id}/delete", json={"confirm_name": "X"}).status_code == 200


def test_api_existing_endpoints_still_work_with_studio(api):
    assert api.get("/api/overview?format=short").status_code == 200
    assert api.get("/api/system").json()["policy"]["record_status"] == "not_requested"


# --- Agente de verdade pelo protocolo MCP, com dados simulados -----------------------------------------------

def test_agent_runs_full_contract_over_mcp_stdio(tmp_path):
    """Sobe o servidor MCP real em subprocesso. O agente é este teste: simula o Claude Code."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "YTI_DATA_DIR": str(tmp_path), "YTI_MODE": "demo", "PYTHONPATH": str(BACKEND_DIR)}
    server = StdioServerParameters(command=sys.executable, args=["-m", "app.studio.mcp_server"], env=env, cwd=str(BACKEND_DIR))

    async def scenario():
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert "get_next_briefing" in names and not {"authorize_job", "publish", "videos_insert", "cancel_job"} & names

                async def call(name, **arguments):
                    result = await session.call_tool(name, arguments)
                    return json.loads(result.content[0].text)

                channels = (await call("list_channels"))["data"]["channels"]
                channel_id = next(c["id"] for c in channels if c["id"] == "chn_demo_rotas")
                assert channels[0]["is_demo"] is True
                context = await call("get_channel_context", channel_id=channel_id, agent_id="agente-teste")
                assert context["data"]["fictional"] is True
                submitted = await call("submit_recommendation", channel_id=channel_id, recommendation=valid_recommendation(), idempotency_key="r1", agent_id="agente-teste")
                assert submitted["ok"], submitted
                recommendation_id = submitted["data"]["recommendation"]["id"]
                briefing = await call("get_next_briefing", channel_id=channel_id, agent_id="agente-teste")
                assert briefing["data"]["briefing"]["recommendation_id"] == recommendation_id

                started = await call("start_production", channel_id=channel_id, recommendation_id=recommendation_id, idempotency_key="s1", agent_id="agente-teste")
                job_id = started["data"]["job"]["id"]
                blocked = await call("claim_job", job_id=job_id, agent_id="agente-teste", idempotency_key="c1")
                assert blocked["ok"] is False and blocked["error"]["code"] == "not_authorized"

                # Autorização humana: fora do MCP, direto no estúdio, como faria a interface.
                settings = Settings(mode="demo", data_dir=tmp_path)
                conn = store.open_studio(settings)
                Contract(conn, settings).authorize_job(job_id, channel_id)
                conn.close()

                claim = await call("claim_job", job_id=job_id, agent_id="agente-teste", idempotency_key="c2")
                token = claim["data"]["lease_token"]
                repeated = await call("claim_job", job_id=job_id, agent_id="agente-teste", idempotency_key="c2")
                assert repeated["data"]["replayed"] is True and repeated["data"]["lease_token"] == token
                assert (await call("update_progress", job_id=job_id, lease_token=token, progress=50, step="Render", idempotency_key="u1"))["ok"]
                assert (await call("log_event", job_id=job_id, level="warning", message="Aviso de teste", idempotency_key="l1", agent_id="agente-teste"))["ok"]
                delivered = await call("deliver_artifacts", job_id=job_id, lease_token=token, artifacts=[{"kind": "video", "path": "simulado://v.mp4"}], idempotency_key="d1")
                artifact_id = delivered["data"]["artifacts"][0]["id"]
                package = await call("prepare_publish_package", job_id=job_id, title="Título", description="Descrição", tags=["x"], video_artifact_id=artifact_id, idempotency_key="p1", agent_id="agente-teste")
                assert package["data"]["published"] is False
                final = await call("get_job", job_id=job_id)
                assert final["data"]["job"]["state"] == "package_ready"
                assert any(e["message"] == "Aviso de teste" for e in final["data"]["events"])

    asyncio.run(scenario())
    # Os estados continuam lá depois que o processo do servidor termina.
    conn = store.open_studio(Settings(mode="demo", data_dir=tmp_path))
    assert conn.execute("SELECT state FROM production_jobs").fetchone()["state"] == "package_ready"
    conn.close()
