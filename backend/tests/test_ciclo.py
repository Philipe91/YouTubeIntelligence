"""Briefing, execuções, arquivos de teste, alertas, adaptadores e isolamento."""
from __future__ import annotations

import ast
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import BACKEND_DIR, Settings
from app.db import connect, migrate
from app.studio import pipelines, recommend, simulator, store
from app.studio.contract import Contract
from app.studio.store import StudioError

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


class Clock:
    now = NOW

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


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
    return Clock()


@pytest.fixture
def contract(db, settings, clock):
    return Contract(db, settings, clock)


def channel(db, name="Canal A", **fields):
    return store.create_channel(db, {"name": name, "formats": ["long", "short"], "audience": "Adultos", "tone": "Direto", **fields})


def owner_rec(db, channel_id, subject="A ponte de barcos de Xerxes"):
    return recommend.create_owner_recommendation(db, channel_id, subject=subject, justification="Tema ligado ao perfil.", video_format="long")


def dispatched(db, contract, channel_id, subject="A ponte de barcos de Xerxes", key=None):
    rec = recommend.generate_titles(db, channel_id, owner_rec(db, channel_id, subject)["id"])
    brief = recommend.approve_briefing(db, channel_id, rec["id"], rec["titles"][1])
    return rec, brief, contract.dispatch_briefing(channel_id, brief["id"], key or f"d-{rec['id']}")["job"]


# --- Recomendação, títulos, briefing ------------------------------------------------------------

def test_owner_recommendation_starts_without_titles_then_gets_three(db):
    ch = channel(db)
    rec = owner_rec(db, ch["id"])
    assert rec["origin"] == "dono" and rec["titles"] == [] and rec["data_basis"] == "editorial"
    done = recommend.generate_titles(db, ch["id"], rec["id"])
    assert len(done["titles"]) == 3 and all("ponte de barcos de Xerxes" in title for title in done["titles"])


@pytest.mark.parametrize("fields,code", [
    ({"subject": "", "justification": "x", "video_format": "long"}, "invalid_field"),
    ({"subject": "Tema", "justification": " ", "video_format": "long"}, "invalid_field"),
    ({"subject": "Tema", "justification": "x", "video_format": "reels"}, "format_not_in_profile"),
    ({"subject": "Tema", "justification": "x", "video_format": "long", "priority": "urgente"}, "invalid_field"),
    ({"subject": "Tema", "justification": "x", "video_format": "long", "duration_seconds": -1}, "invalid_field"),
])
def test_owner_recommendation_validation(db, fields, code):
    with pytest.raises(StudioError) as caught:
        recommend.create_owner_recommendation(db, channel(db)["id"], **fields)
    assert caught.value.code == code


def test_owner_recommendation_respects_avoid_list_and_duplicates(db):
    ch = channel(db, avoid=["guerra"])
    with pytest.raises(StudioError) as avoided:
        owner_rec(db, ch["id"], "A guerra de Troia")
    assert avoided.value.code == "subject_avoided"
    owner_rec(db, ch["id"])
    with pytest.raises(StudioError) as duplicate:
        owner_rec(db, ch["id"])
    assert duplicate.value.code == "duplicate_recommendation"


def test_briefing_is_structured_and_uses_chosen_title(db):
    ch = channel(db, positioning="Histórias curtas", avoid=["política"])
    rec = recommend.generate_titles(db, ch["id"], owner_rec(db, ch["id"])["id"])
    brief = recommend.approve_briefing(db, ch["id"], rec["id"], rec["titles"][2])
    payload = brief["payload"]
    assert brief["chosen_title"] == rec["titles"][2] and payload["chosen_title"] == rec["titles"][2]
    assert brief["approved_by"] == "dono_local"
    assert [s["section"] for s in payload["outline"]][0] == "Gancho" and payload["outline"]
    assert payload["tone"] == "Direto" and payload["avoid"] == ["política"] and "Não publicar." in payload["constraints"]
    assert payload["fictional"] is False
    assert store.list_recommendations(db, ch["id"], "aceita")[0]["id"] == rec["id"]


def test_briefing_accepts_custom_title_and_rejects_invalid(db):
    ch = channel(db)
    rec = owner_rec(db, ch["id"])
    with pytest.raises(StudioError) as empty:
        recommend.approve_briefing(db, ch["id"], rec["id"], "  ")
    assert empty.value.code == "title_required"
    with pytest.raises(StudioError):
        recommend.approve_briefing(db, ch["id"], rec["id"], "x" * 101)
    assert recommend.approve_briefing(db, ch["id"], rec["id"], "Meu título")["chosen_title"] == "Meu título"


def test_reapproving_replaces_briefing_and_can_create_calendar_entry(db):
    ch = channel(db)
    rec = owner_rec(db, ch["id"])
    first = recommend.approve_briefing(db, ch["id"], rec["id"], "Título A")
    second = recommend.approve_briefing(db, ch["id"], rec["id"], "Título B", planned_on="2030-01-10")
    assert first["id"] == second["id"] and second["chosen_title"] == "Título B"
    assert db.execute("SELECT COUNT(*) FROM briefings").fetchone()[0] == 1
    entry = store.list_calendar(db, ch["id"], "2030-01-01", "2030-01-31")[0]
    assert entry["title"] == "Título B" and entry["recommendation_id"] == rec["id"]


def test_reapproving_with_date_updates_calendar_instead_of_duplicating(db):
    ch = channel(db)
    rec = owner_rec(db, ch["id"])
    recommend.approve_briefing(db, ch["id"], rec["id"], "Título A", planned_on="2030-01-10")
    recommend.approve_briefing(db, ch["id"], rec["id"], "Título B", planned_on="2030-01-20")
    recommend.approve_briefing(db, ch["id"], rec["id"], "Título C")
    entries = store.list_calendar(db, ch["id"], "2030-01-01", "2030-12-31")
    assert [(e["title"], e["scheduled_on"]) for e in entries] == [("Título C", "2030-01-20")]


def test_package_response_tells_the_agent_the_final_state(db, contract):
    ch = channel(db)
    _, _, job = dispatched(db, contract, ch["id"])
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    video = contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")["artifacts"][0]
    result = contract.prepare_publish_package(job["id"], "T", "D", [], video["id"], "p1")
    assert result["job"]["state"] == "package_ready" and result["job"]["state_label"] == "PRONTO PARA REVISÃO"


def test_fictional_channel_briefing_is_marked_fictional(db):
    store.seed_demo_once(db, NOW)
    rec = owner_rec(db, "chn_demo_cronicas")
    assert recommend.approve_briefing(db, "chn_demo_cronicas", rec["id"], "T")["payload"]["fictional"] is True


# --- Disponibilizar ao agente ----------------------------------------------------------------------

def test_dispatch_makes_task_available_with_briefing(db, contract):
    ch = channel(db)
    rec, brief, job = dispatched(db, contract, ch["id"])
    assert job["state"] == "authorized" and job["title"] == rec["titles"][1] and job["authorized_by"] == "dono_local"
    assert job["simulated"] is True
    tasks = contract.list_available_tasks(ch["id"], "agente")["tasks"]
    assert [t["job_id"] for t in tasks] == [job["id"]] and tasks[0]["has_briefing"]
    claim = contract.claim_job(job["id"], "agente", "c1")
    assert claim["briefing"]["chosen_title"] == rec["titles"][1]
    assert contract.list_available_tasks(ch["id"])["tasks"] == [], "assumida, sai da lista"


def test_double_click_on_dispatch_does_not_duplicate(db, contract):
    ch = channel(db)
    rec = owner_rec(db, ch["id"])
    brief = recommend.approve_briefing(db, ch["id"], rec["id"], "T")
    first = contract.dispatch_briefing(ch["id"], brief["id"], "mesma")
    again = contract.dispatch_briefing(ch["id"], brief["id"], "mesma")
    assert again["replayed"] and again["job"]["id"] == first["job"]["id"]
    with pytest.raises(StudioError) as other:
        contract.dispatch_briefing(ch["id"], brief["id"], "outra-chave")
    assert other.value.code == "recommendation_unavailable", "não cria segunda execução do mesmo briefing"
    assert db.execute("SELECT COUNT(*) FROM production_jobs").fetchone()[0] == 1


def test_dispatch_respects_automation_and_channel(db, contract):
    a, b = channel(db, "A"), channel(db, "B")
    rec = owner_rec(db, a["id"])
    brief = recommend.approve_briefing(db, a["id"], rec["id"], "T")
    with pytest.raises(StudioError) as cross:
        contract.dispatch_briefing(b["id"], brief["id"], "k1")
    assert cross.value.code == "briefing_not_in_channel"
    store.update_channel(db, a["id"], {"auto_production": "off"})
    with pytest.raises(StudioError) as off:
        contract.dispatch_briefing(a["id"], brief["id"], "k2")
    assert off.value.code == "automation_off"


def test_after_cancel_can_dispatch_again(db, contract):
    ch = channel(db)
    rec, brief, job = dispatched(db, contract, ch["id"])
    contract.cancel_job(job["id"], ch["id"])
    again = contract.dispatch_briefing(ch["id"], brief["id"], "nova-chave")
    assert again["job"]["id"] != job["id"] and again["job"]["state"] == "authorized"


# --- Arquivo de teste ------------------------------------------------------------------------------

def test_test_result_file_is_written_only_in_job_sandbox_and_hash_verified(db, contract, settings):
    ch = channel(db)
    _, _, job = dispatched(db, contract, ch["id"])
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    result = contract.write_test_result(job["id"], token, "conteúdo com key=SEGREDO1", "w1")
    path = Path(result["path"])
    assert path.is_file() and path.is_relative_to(Path(settings.data_dir).resolve() / "artefatos_teste" / job["id"])
    text = path.read_text(encoding="utf-8")
    assert text.startswith("ARQUIVO DE TESTE") and "SEGREDO1" not in text
    assert result["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not list(path.parent.glob("*.tmp"))
    artifact = contract.deliver_artifacts(job["id"], token, [{"kind": "other", "path": result["path"]}], "d1")["artifacts"][0]
    assert artifact["sha256"] == result["sha256"]


def test_test_result_refused_for_real_job_and_stale_token(db, contract):
    ch = channel(db)
    real = contract.start_production(ch["id"], owner_rec(db, ch["id"], "Tema real")["id"], "s1", "a", False)["job"]
    contract.authorize_job(real["id"], ch["id"])
    token = contract.claim_job(real["id"], "a", "c1")["lease_token"]
    with pytest.raises(StudioError) as caught:
        contract.write_test_result(real["id"], token, "x", "w1")
    assert caught.value.code == "not_simulated"
    _, _, job = dispatched(db, contract, ch["id"])
    contract.claim_job(job["id"], "a", "c2")
    with pytest.raises(StudioError) as stale:
        contract.write_test_result(job["id"], "token-falso", "x", "w2")
    assert stale.value.code == "lease_lost"


def test_simulated_job_cannot_deliver_files_from_other_places(db, contract, tmp_path):
    ch = channel(db)
    _, _, first = dispatched(db, contract, ch["id"], "Tema um")
    _, _, second = dispatched(db, contract, ch["id"], "Tema dois")
    token_a = contract.claim_job(first["id"], "a", "c1")["lease_token"]
    token_b = contract.claim_job(second["id"], "b", "c2")["lease_token"]
    other_job_file = contract.write_test_result(second["id"], token_b, "de outra tarefa", "w2")["path"]
    outside = tmp_path / "fora.txt"
    outside.write_text("x")
    escape = str(Path(contract._sandbox(first["id"])) / ".." / ".." / "fora.txt")
    for path in (other_job_file, str(outside), escape, r"D:\projetos\BROTHER QUILL\CONTINUAR_AQUI.md"):
        with pytest.raises(StudioError) as caught:
            contract.deliver_artifacts(first["id"], token_a, [{"kind": "other", "path": path}], f"d-{path}")
        assert caught.value.code == "invalid_artifact", path


def test_artifact_download_verifies_ownership_virtual_missing_and_tampering(db, contract):
    ch, other = channel(db, "A"), channel(db, "B")
    _, _, job = dispatched(db, contract, ch["id"])
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    path = contract.write_test_result(job["id"], token, "ok", "w1")["path"]
    items = contract.deliver_artifacts(job["id"], token, [{"kind": "other", "path": path}, {"kind": "video", "path": "simulado://v.mp4"}], "d1")["artifacts"]
    real, virtual = items
    assert contract.artifact_file(ch["id"], job["id"], real["id"])[0] == Path(path)
    with pytest.raises(StudioError):
        contract.artifact_file(other["id"], job["id"], real["id"])
    with pytest.raises(StudioError) as virtual_error:
        contract.artifact_file(ch["id"], job["id"], virtual["id"])
    assert virtual_error.value.code == "artifact_virtual"
    Path(path).write_text("alterado", encoding="utf-8")
    with pytest.raises(StudioError) as changed:
        contract.artifact_file(ch["id"], job["id"], real["id"])
    assert changed.value.code == "artifact_changed"
    Path(path).unlink()
    with pytest.raises(StudioError) as missing:
        contract.artifact_file(ch["id"], job["id"], real["id"])
    assert missing.value.code == "artifact_missing"


# --- Histórico de execuções e alertas ---------------------------------------------------------------

def test_attempt_history_records_failure_expiry_and_delivery(db, contract, clock):
    ch = channel(db)
    _, _, job = dispatched(db, contract, ch["id"])
    token = contract.claim_job(job["id"], "agente-1", "c1")["lease_token"]
    contract.report_failure(job["id"], token, "erro temporário", True, "f1")
    contract.claim_job(job["id"], "agente-2", "c2", lease_seconds=30)
    clock.advance(seconds=31)
    contract.recover_stale()
    token = contract.claim_job(job["id"], "agente-3", "c3")["lease_token"]
    contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")
    history = contract.get_job(job["id"])["attempt_history"]
    assert [(a["number"], a["agent_id"], a["outcome"]) for a in history] == [
        (1, "agente-1", "falhou"), (2, "agente-2", "prazo_vencido"), (3, "agente-3", "entregue")]
    assert history[0]["error"] == "erro temporário" and all(a["ended_at"] for a in history)


def test_alerts_are_per_channel_and_can_be_acknowledged(db, contract):
    a, b = channel(db, "A"), channel(db, "B")
    _, _, job = dispatched(db, contract, a["id"])
    token = contract.claim_job(job["id"], "x", "c1")["lease_token"]
    contract.report_failure(job["id"], token, "falhou feio", True, "f1")
    alerts = contract.channel_cockpit(a["id"])["alerts"]
    assert [x["message"] for x in alerts] == ["falhou feio"]
    assert contract.channel_cockpit(b["id"])["alerts"] == []
    with pytest.raises(StudioError):
        contract.acknowledge_alert(b["id"], alerts[0]["id"])
    contract.acknowledge_alert(a["id"], alerts[0]["id"])
    assert contract.channel_cockpit(a["id"])["alerts"] == []


def test_cockpit_never_mixes_channels(db, contract):
    a, b = channel(db, "A"), channel(db, "B")
    _, _, job = dispatched(db, contract, a["id"])
    token = contract.claim_job(job["id"], "x", "c1")["lease_token"]
    contract.deliver_artifacts(job["id"], token, [{"kind": "video", "path": "simulado://v"}], "d1")
    seen = contract.channel_cockpit(a["id"])
    assert seen["current_job"]["id"] == job["id"] and seen["attempts"] and seen["artifacts"]
    empty = contract.channel_cockpit(b["id"])
    assert empty["current_job"] is None and empty["attempts"] == [] and empty["artifacts"] == []


def test_state_survives_new_connection_and_process_style_reopen(settings, db, clock):
    contract = Contract(db, settings, clock)
    ch = channel(db)
    _, _, job = dispatched(db, contract, ch["id"])
    token = contract.claim_job(job["id"], "a", "c1")["lease_token"]
    contract.update_progress(job["id"], token, 40, "Narração", "u1")
    db.close()
    fresh = store.open_studio(settings)
    reopened = Contract(fresh, settings, clock)
    state = reopened.get_job(job["id"])
    assert state["job"]["state"] == "running" and state["job"]["progress"] == 40 and state["job"]["step"] == "Narração"
    reopened.update_progress(job["id"], token, 60, "Animação", "u2")
    assert reopened.update_progress(job["id"], token, 60, "Animação", "u2")["replayed"] is True
    fresh.close()


# --- Adaptadores ------------------------------------------------------------------------------------

def test_all_profiles_cover_every_stage_with_known_adapter():
    for name, profile in pipelines.load_profiles().items():
        assert profile["label"]
        for key, _, _ in pipelines.STAGES:
            assert profile["stages"][key]["adapter"] in pipelines.ADAPTERS, (name, key)


def test_simulated_profile_can_execute_and_only_simulates():
    plan = pipelines.plan_for("simulado", "job", "chn")
    assert plan["ready_to_execute"] is True and all(s["simulated"] for s in plan["stages"])
    assert pipelines.adapter_for("simulado", "roteiro").run(pipelines.StageRequest("j", "c", "roteiro")).simulated is True


@pytest.mark.parametrize("profile", ["viral_replicator", "money_printer"])
def test_real_profiles_only_describe_and_never_execute(profile):
    plan = pipelines.plan_for(profile, "job", "chn")
    assert plan["ready_to_execute"] is False and plan["real_execution_enabled"] is False
    assert all(not stage["can_execute"] and stage["blocked_reason"] for stage in plan["stages"])
    for key, _, _ in pipelines.STAGES:
        with pytest.raises(StudioError) as caught:
            pipelines.adapter_for(profile, key).run(pipelines.StageRequest("j", "c", key))
        assert caught.value.code in {"pipeline_execution_disabled", "pipeline_stage_undefined"}


def test_adapter_module_cannot_launch_processes():
    source = (BACKEND_DIR / "app" / "studio" / "pipelines.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert not imported & {"subprocess", "os", "shutil", "multiprocessing", "asyncio"}, imported


def test_unknown_profile_is_refused(db):
    with pytest.raises(StudioError):
        pipelines.adapter_for("nao-existe", "roteiro")
    with pytest.raises(StudioError):
        store.update_channel(db, channel(db)["id"], {"pipeline_profile": "nao-existe"})


def test_channel_can_choose_profile_but_simulator_stays_simulated(db, contract):
    ch = channel(db, pipeline_profile="brother_quill")
    assert ch["pipeline_profile"] == "brother_quill"
    _, _, job = dispatched(db, contract, ch["id"])
    for _ in range(8):
        state = simulator.simulate_step(contract, job["id"], ch["id"])
    assert state["job"]["state"] == "package_ready"


# --- Migração do estúdio -----------------------------------------------------------------------------

def test_studio_migration_preserves_recommendations_and_jobs(tmp_path):
    import shutil

    old = tmp_path / "antigas"
    old.mkdir()
    shutil.copy(store.MIGRATIONS / "001_studio.sql", old)
    conn = connect(tmp_path / "s.sqlite")
    migrate(conn, old)
    stamp = "2026-10-01T00:00:00Z"
    conn.execute("INSERT INTO managed_channels (id, name, created_at, updated_at) VALUES ('c', 'n', ?, ?)", (stamp, stamp))
    conn.execute("""INSERT INTO recommendations (id, channel_id, dedupe_key, subject, justification, sources_json, titles_json, thumbnail_idea, hook,
                    format, duration_seconds, target_audience, editorial_priority, data_basis, origin, created_at, updated_at)
                    VALUES ('r', 'c', 'k', 's', 'j', '[]', '[]', 't', 'h', 'long', 60, 'a', 'alta', 'editorial', 'regras', ?, ?)""", (stamp, stamp))
    conn.execute("""INSERT INTO production_jobs (id, channel_id, recommendation_id, title, format, simulated, state, requested_by, created_at, updated_at)
                    VALUES ('j', 'c', 'r', 't', 'long', 1, 'running', 'a', ?, ?)""", (stamp, stamp))
    conn.execute("INSERT INTO job_events (job_id, at, level, kind, message) VALUES ('j', ?, 'info', 'state', 'm')", (stamp,))
    conn.commit()
    assert migrate(conn, store.MIGRATIONS) == ["002_briefing_execucoes.sql", "003_producao_real.sql", "004_inteligencia.sql", "005_titulos.sql"]
    assert conn.execute("SELECT recommendation_id FROM production_jobs").fetchone()[0] == "r", "recriar a tabela não pode soltar a tarefa"
    assert conn.execute("SELECT COUNT(*) FROM job_events").fetchone()[0] == 1
    assert conn.execute("SELECT pipeline_profile FROM managed_channels").fetchone()[0] == "simulado"
    conn.close()


# --- API ----------------------------------------------------------------------------------------------

@pytest.fixture
def api(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path, api_token="teste")
    main.app.dependency_overrides[main.settings_dep] = lambda: settings
    yield TestClient(main.app, base_url="http://127.0.0.1", headers={"X-YTI-Token": "teste"})
    main.app.dependency_overrides.clear()


def test_api_full_owner_flow_and_file_download(api):
    base = "/api/studio/channels/chn_demo_rotas"
    rec = api.post(f"{base}/recommendations", json={"subject": "Tema de teste", "justification": "Por quê", "format": "long"}).json()
    titled = api.post(f"{base}/recommendations/{rec['id']}/titles").json()
    brief = api.post(f"{base}/recommendations/{rec['id']}/briefing", json={"chosen_title": titled["titles"][0], "planned_on": "2030-05-05"}).json()
    job = api.post(f"{base}/briefings/{brief['id']}/dispatch", json={"idempotency_key": "ui-1"}).json()["job"]
    assert job["state_label"] == "NA FILA"
    for _ in range(8):
        state = api.post(f"{base}/jobs/{job['id']}/simulate-step").json()
    assert state["job"]["state_label"] == "PRONTO PARA REVISÃO"
    cockpit = api.get(f"{base}/cockpit").json()
    files = {a["kind"]: a for a in cockpit["artifacts"] if a["job_id"] == job["id"]}
    assert files["other"]["downloadable"] and not files["video"]["downloadable"]
    response = api.get(f"{base}/jobs/{job['id']}/artifacts/{files['other']['id']}")
    assert response.status_code == 200 and response.content.startswith("ARQUIVO DE TESTE".encode())
    assert response.headers["x-content-type-options"] == "nosniff" and response.headers["content-type"] == "application/octet-stream"
    assert "attachment" in response.headers["content-disposition"]
    assert api.get(f"{base}/jobs/{job['id']}/artifacts/{files['video']['id']}").status_code == 404
    assert api.get(f"/api/studio/channels/chn_demo_cronicas/jobs/{job['id']}/artifacts/{files['other']['id']}").status_code == 404
    assert any(e["title"] == titled["titles"][0] and e["status"] == "pronto_para_revisao" for e in api.get("/api/studio/calendar", params={"start": "2030-05-01", "end": "2030-05-31"}).json()["entries"])


def test_api_cockpit_and_pipeline_endpoints(api):
    base = "/api/studio/channels/chn_demo_cronicas"
    cockpit = api.get(f"{base}/cockpit").json()
    assert cockpit["next_recommendation"] and cockpit["current_job"]["state"] == "awaiting_authorization"
    assert "upcoming" in cockpit and "alerts" in cockpit
    pipeline = api.get(f"{base}/pipeline").json()
    assert pipeline["plan"]["profile"] == "simulado" and {o["id"] for o in pipeline["options"]} >= {"simulado", "brother_quill"}
    assert api.get("/api/studio/channels/nao-existe/cockpit").status_code == 404


def test_api_real_channel_uses_no_fictional_basis_in_owner_flow(api):
    channel_id = api.post("/api/studio/channels", json={"fields": {"name": "Real", "formats": ["long"]}}).json()["id"]
    rec = api.post(f"/api/studio/channels/{channel_id}/recommendations", json={"subject": "Tema real", "justification": "Por quê", "format": "long"}).json()
    assert rec["data_basis"] == "editorial" and rec["sources"][0]["fictional"] is False
    brief = api.post(f"/api/studio/channels/{channel_id}/recommendations/{rec['id']}/briefing", json={"chosen_title": "Título"}).json()
    assert brief["payload"]["fictional"] is False and "score" not in json.dumps(brief).lower()


def test_no_endpoint_or_tool_publishes():
    routes = list(main.app.openapi()["paths"])
    assert "/api/studio/overview" in routes, "a lista precisa incluir as rotas do estúdio"
    assert not [path for path in routes if "publish" in path or "upload" in path]
    source = "".join(path.read_text(encoding="utf-8") for path in (BACKEND_DIR / "app").rglob("*.py"))
    assert "videos.insert" not in source and "youtube/upload" not in source
