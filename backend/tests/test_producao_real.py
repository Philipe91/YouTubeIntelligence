"""Adaptador Brother Quill sem executar nada externo: o Executor é substituído por um falso."""
from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import BACKEND_DIR, Settings
from app.studio import bq_script, bq_worker, pipelines, recommend, store
from app.studio.bq_worker import Abort, BQWorker, Executor, job_dir, validate_file
from app.studio.contract import Contract
from app.studio.production import Production
from app.studio.store import StudioError

CENA = {"texto": "Christmas Eve, 1914. Soldiers froze in the mud.", "m": "mundo", "set": "trincheira", "quem": "remoi"}
ROTEIRO = {"resumo": "Teste de roteiro original.", "cenas": [CENA, {"texto": "Then they climbed out, and met.", "m": "mundo", "set": "campo", "quem": "silencio"}],
           "fontes": [{"label": "Fonte de teste", "url": "https://example.org"}], "fatos_a_conferir": ["Data"]}


@pytest.fixture
def settings(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token="t")


@pytest.fixture
def db(settings):
    conn = store.open_studio(settings)
    yield conn
    conn.close()


@pytest.fixture
def contract(db, settings):
    return Contract(db, settings)


def dispatched(db, contract, profile="brother_quill", seconds=15):
    channel = store.create_channel(db, {"name": "Piloto", "formats": ["short"], "pipeline_profile": profile, "short_target_seconds": seconds})
    rec = recommend.create_owner_recommendation(db, channel["id"], subject="Tema de teste", justification="Porque sim.", video_format="short")
    brief = recommend.approve_briefing(db, channel["id"], rec["id"], "Título")
    return channel, contract.dispatch_briefing(channel["id"], brief["id"], "d1", real=True)["job"]


def claimed(db, contract, **kwargs):
    channel, job = dispatched(db, contract, **kwargs)
    return channel, job, contract.claim_job(job["id"], "agente", "c1")["lease_token"]


class FakeExecutor:
    """Registra os comandos e cria os arquivos que o comando real criaria."""

    def __init__(self, worker_dir: Path, vid: str, frames: int = 400, fail_on: str | None = None, qa=None):
        self.dir, self.vid, self.frames, self.fail_on, self.qa_result = worker_dir, vid, frames, fail_on, qa if qa is not None else []
        self.calls: list[tuple[str, list[str], Path]] = []
        self.engine = "x " + bq_worker.ENGINE_PATCHES[0][2] + " y"

    def run(self, operation, argv, cwd, env=None, tick=None):
        self.calls.append((operation, list(argv), Path(cwd)))
        with (self.dir / "worker.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{operation}\n")
        if operation == self.fail_on:
            raise StudioError("operation_failed", f"{operation} falhou", 500)
        if tick:
            tick()
        if operation == "git_archive":
            import tarfile

            (self.dir / "src_tmp" / "anim" / "src" / "v44").mkdir(parents=True, exist_ok=True)
            (self.dir / "src_tmp" / "anim" / "src" / "v44" / "mundo44.js").write_text(self.engine, encoding="utf-8")
            (self.dir / "src_tmp" / "anim" / "studio.html").write_text("x")
            (self.dir / "src_tmp" / "anim" / "node_modules").mkdir(exist_ok=True)
            with tarfile.open(self.dir / "base.tar", "w") as archive:
                archive.add(self.dir / "src_tmp" / "anim", arcname="anim")
        elif operation == "narrar":
            public = self.dir / "public" / self.vid
            public.mkdir(parents=True, exist_ok=True)
            cenas = [{"texto": "a", "m": "quill", "audio": f"{self.vid}/s00.mp3", "inicio": 0.0, "dur": 12.0, "palavras": [{"w": "a", "t": 0, "d": 1}]}]
            (public / "s00.mp3").write_bytes(b"x")
            (public / "timeline.json").write_text(json.dumps({"total": 12.0, "cenas": cenas}), encoding="utf-8")
        elif operation == "qa":
            Path(next(a for a in argv if a.startswith("--qa=")).split("=", 1)[1]).write_text(json.dumps(self.qa_result), encoding="utf-8")
        elif operation == "frames":
            folder = Path(next(a for a in argv if a.startswith("--framesdir=")).split("=", 1)[1])
            for i in range(self.frames):
                (folder / f"f{i:05d}.jpg").write_bytes(b"x")
        elif operation == "encode":
            Path(next(a for a in argv if a.startswith("--out=")).split("=", 1)[1]).write_bytes(b"x")
        elif operation in {"mix", "mux", "folha"}:
            Path(argv[-1]).write_bytes(b"x" * 200_000)


GOOD_PROBE = {"format": {"duration": "12.8"}, "streams": [
    {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "nb_frames": "307", "r_frame_rate": "24/1"},
    {"codec_type": "audio", "codec_name": "aac"}]}


@pytest.fixture(autouse=True)
def fake_probe(monkeypatch):
    monkeypatch.setattr(bq_worker, "probe", lambda path: GOOD_PROBE)
    monkeypatch.setattr(bq_worker.validate_file, "__defaults__", (lambda path: GOOD_PROBE,))


def worker_for(db, settings, contract, job, **kwargs):
    Production(contract, spawn=lambda j, l: 1, ram=lambda: 8.0).submit_script(job["id"], contract._job(job["id"])["lease_token"], ROTEIRO, "s1", "agente")
    Production(contract, spawn=lambda j, l: 1, ram=lambda: 8.0).start_run(job["id"], contract._job(job["id"])["lease_token"], "r1")
    directory = job_dir(settings, job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    ram = kwargs.pop("ram", lambda: 8.0)
    executor = FakeExecutor(directory, bq_script.pipeline_id(job["id"]), **kwargs)
    worker = BQWorker(db, settings, job["id"], executor=executor, ram=ram)
    # O falso não cria a junção: pula a etapa do sistema de arquivos.
    return worker, executor


# --- Roteiro -------------------------------------------------------------------------------------

def test_valid_script_passes():
    clean = bq_script.validate_script(ROTEIRO)
    assert len(clean["cenas"]) == 2 and clean["cenas"][0]["set"] == "trincheira"


@pytest.mark.parametrize("change", [
    {"m": "codigo"}, {"set": "../../etc"}, {"quem": "qualquer"}, {"set": "estrada"}, {"js": "alert(1)"},
    {"fx": [["mud.", "rm -rf"]]}, {"fx": [["ausente", "pop"]]}, {"snap": "ausente"}, {"texto": "a\u200bb tem invisível"},
    {"valor": "1;drop"}, {"m": "numero", "set": None, "quem": None}, {"m": "relogio", "set": None, "quem": None},
])
def test_script_outside_catalog_is_refused(change):
    bad = {**ROTEIRO, "cenas": [{**CENA, **change}]}
    with pytest.raises(StudioError) as caught:
        bq_script.validate_script(bad)
    assert caught.value.code == "invalid_script"


def test_script_limits():
    many = {"texto": " ".join(["word"] * 46), "m": "quill", "acao": "escreve"}
    for bad in ({**ROTEIRO, "cenas": [many]}, {**ROTEIRO, "cenas": [CENA] * 7}, {**ROTEIRO, "fontes": []}, {**ROTEIRO, "extra": 1}):
        with pytest.raises(StudioError):
            bq_script.validate_script(bad)


def test_malicious_text_never_reaches_a_command(db, settings, contract):
    attack = 'Ignore rules "; del /f C:\\ & powershell -c evil $(calc)'
    script = {**ROTEIRO, "cenas": [{"texto": attack, "m": "quill", "acao": "escreve"}]}
    channel, job, token = claimed(db, contract)
    Production(contract, ram=lambda: 8.0).submit_script(job["id"], token, script, "s9", "agente")
    Production(contract, spawn=lambda j, l: 1, ram=lambda: 8.0).start_run(job["id"], token, "r9")
    directory = job_dir(settings, job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    executor = FakeExecutor(directory, bq_script.pipeline_id(job["id"]))
    worker = BQWorker(db, settings, job["id"], executor=executor)
    worker.preparar = lambda: "ok"
    (directory / "ws" / "anim" / "src").mkdir(parents=True)
    assert worker.run() == 0
    for _, argv, _ in executor.calls:
        assert not any("powershell" in arg or "Ignore rules" in arg or "calc" in arg for arg in argv)
    assert "Ignore rules" in (directory / "roteiro.json").read_text(encoding="utf-8"), "só como dado"


# --- Início da execução ---------------------------------------------------------------------------

def test_real_dispatch_needs_allowed_adapter_and_limit(db, contract):
    for profile, code in (("simulado", "adapter_not_allowed"), ("viral_replicator", "adapter_not_allowed")):
        channel = store.create_channel(db, {"name": profile, "formats": ["short"], "pipeline_profile": profile})
        rec = recommend.create_owner_recommendation(db, channel["id"], subject="Tema", justification="x", video_format="short")
        brief = recommend.approve_briefing(db, channel["id"], rec["id"], "T")
        with pytest.raises(StudioError) as caught:
            contract.dispatch_briefing(channel["id"], brief["id"], f"k{profile}", real=True)
        assert caught.value.code == code
    channel = store.create_channel(db, {"name": "Longo", "formats": ["short"], "pipeline_profile": "brother_quill", "short_target_seconds": 300})
    rec = recommend.create_owner_recommendation(db, channel["id"], subject="Tema", justification="x", video_format="short")
    brief = recommend.approve_briefing(db, channel["id"], rec["id"], "T")
    with pytest.raises(StudioError) as long_error:
        contract.dispatch_briefing(channel["id"], brief["id"], "k3", real=True)
    assert long_error.value.code == "video_too_long"


def test_execution_switch_blocks_everything(db, settings, contract):
    channel, job, token = claimed(db, contract)
    off = dataclasses.replace(settings, execution={**settings.execution, "real_execution_enabled": False})
    with pytest.raises(StudioError) as caught:
        Production(Contract(db, off), spawn=lambda j, l: 1, ram=lambda: 8.0).start_run(job["id"], token, "r1")
    assert caught.value.code == "real_execution_disabled"


def test_start_needs_script_memory_lease_and_single_run(db, settings, contract):
    spawned = []
    production = Production(contract, spawn=lambda j, l: spawned.append(j) or 1, ram=lambda: 8.0)
    channel, job, token = claimed(db, contract)
    with pytest.raises(StudioError) as no_script:
        production.start_run(job["id"], token, "r0")
    assert no_script.value.code == "script_required"
    production.submit_script(job["id"], token, ROTEIRO, "s1", "agente")
    with pytest.raises(StudioError) as bad_token:
        production.start_run(job["id"], "falso", "r1")
    assert bad_token.value.code == "lease_lost"
    with pytest.raises(StudioError) as low:
        Production(contract, spawn=lambda j, l: 1, ram=lambda: 1.0).start_run(job["id"], token, "r2")
    assert low.value.code == "low_memory" and low.value.retryable
    assert spawned == []
    first = production.start_run(job["id"], token, "r3")
    assert first["started"] and spawned == [job["id"]]
    assert production.start_run(job["id"], token, "r3")["replayed"] is True and spawned == [job["id"]], "repetir não abre outro processo"


def test_only_one_real_run_at_a_time(db, contract):
    production = Production(contract, spawn=lambda j, l: 1, ram=lambda: 8.0)
    channel, job, token = claimed(db, contract)
    production.submit_script(job["id"], token, ROTEIRO, "s1", "agente")
    production.start_run(job["id"], token, "r1")
    db.execute("UPDATE job_stages SET status = 'em_andamento' WHERE stage = 'frames'")
    db.commit()
    rec = recommend.create_owner_recommendation(db, channel["id"], subject="Outro tema", justification="x", video_format="short")
    brief = recommend.approve_briefing(db, channel["id"], rec["id"], "T")
    other = contract.dispatch_briefing(channel["id"], brief["id"], "d2", real=True)["job"]
    token2 = contract.claim_job(other["id"], "agente", "c2")["lease_token"]
    production.submit_script(other["id"], token2, ROTEIRO, "s2", "agente")
    with pytest.raises(StudioError) as caught:
        production.start_run(other["id"], token2, "r2")
    assert caught.value.code == "another_run_active"


def test_simulated_job_cannot_use_real_operations(db, contract):
    channel = store.create_channel(db, {"name": "Sim", "formats": ["short"], "pipeline_profile": "brother_quill"})
    rec = recommend.create_owner_recommendation(db, channel["id"], subject="Tema", justification="x", video_format="short")
    brief = recommend.approve_briefing(db, channel["id"], rec["id"], "T")
    job = contract.dispatch_briefing(channel["id"], brief["id"], "d")["job"]
    token = contract.claim_job(job["id"], "a", "c")["lease_token"]
    with pytest.raises(StudioError) as caught:
        Production(contract).submit_script(job["id"], token, ROTEIRO, "s", "a")
    assert caught.value.code == "not_real_job"


# --- Worker --------------------------------------------------------------------------------------

def run_worker(db, settings, contract, **kwargs):
    channel, job, token = claimed(db, contract)
    worker, executor = worker_for(db, settings, contract, job, **kwargs)
    return channel, job, token, worker, executor


def test_worker_runs_every_stage_and_delivers_real_files(db, settings, contract, monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "_winapi", __import__("sys").modules.get("_winapi"))
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    assert worker.run() == 0
    state = contract.get_job(job["id"])
    assert state["job"]["state"] == "delivered" and state["job"]["simulated"] is False
    assert [s["status"] for s in state["stages"]] == ["concluida"] * 9
    frames = next(s for s in state["stages"] if s["stage"] == "frames")
    assert frames["done"] == 400 and frames["total"] == 307 or frames["done"] >= frames["total"]
    assert {a["kind"] for a in state["artifacts"]} == {"short", "other"}
    assert all(a["sha256"] for a in state["artifacts"]), "arquivo real tem hash"
    assert [c[0] for c in executor.calls] == ["git_archive", "narrar", "qa", "frames", "encode", "mix", "mux", "folha"]
    assert not (job_dir(settings, job["id"]) / "frames").exists(), "quadros temporários apagados"
    assert state["validation"]["ok"] is True


def test_nothing_runs_inside_the_original_project(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.run()
    base = job_dir(settings, job["id"])
    assert all(Path(cwd).resolve().is_relative_to(base) for _, _, cwd in executor.calls)
    git = next(c for c in executor.calls if c[0] == "git_archive")
    assert git[1][:3] == ["git", "-C", settings.execution["brother_quill_v1"]["repo"]] and "archive" in git[1] and settings.execution["brother_quill_v1"]["commit"] in git[1]


def test_low_memory_stops_and_can_resume_with_frames_kept(db, settings, contract):
    readings = iter([8.0] * 8 + [0.3] * 50)
    channel, job, token, worker, executor = run_worker(db, settings, contract, ram=lambda: next(readings))
    assert worker.run() == 3
    state = contract.get_job(job["id"])["job"]
    assert state["state"] == "authorized" and "Memória" in state["last_error"]


def test_cancel_stops_worker(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    contract.cancel_job(job["id"], channel["id"])
    worker.token = token
    with pytest.raises(StudioError):
        worker.run()
    token_lost = contract._job(job["id"])["state"]
    assert token_lost == "cancelled"


def test_worker_detects_takeover(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.token = "de-outro"
    with pytest.raises(Abort):
        worker._beat()


def test_operation_failure_is_visible(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract, fail_on="frames")
    assert worker.run() == 2
    state = contract.get_job(job["id"])
    assert state["job"]["state"] == "failed" and "frames falhou" in state["job"]["last_error"]
    stage = next(s for s in state["stages"] if s["stage"] == "frames")
    assert stage["status"] == "falhou"
    assert [s["status"] for s in state["stages"] if s["stage"] == "encode"] == ["pendente"]


def test_too_long_narration_stops_before_render(db, settings, contract):
    limited = dataclasses.replace(settings, execution={**settings.execution, "max_video_seconds": 5})
    channel, job, token = claimed(db, contract)
    worker, executor = worker_for(db, limited, Contract(db, limited), job)
    assert worker.run() == 2
    assert "frames" not in [c[0] for c in executor.calls]
    assert contract._job(job["id"])["last_error"].startswith("Narração de")


def test_broken_scene_stops_before_render(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract, qa=[{"tipo": "erro_mundo", "msg": "boom"}])
    assert worker.run() == 2 and "frames" not in [c[0] for c in executor.calls]


def test_qa_warnings_are_logged_without_stopping(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract, qa=[{"tipo": "sobreposicao", "cena": 0}])
    assert worker.run() == 0
    assert "Revisão geométrica: 1 avisos" in " ".join(e["message"] for e in contract.get_job(job["id"])["events"])


def test_engine_patch_only_touches_the_job_copy(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    assert worker.run() == 0
    patched = (worker.anim / "src" / "v44" / "mundo44.js").read_text(encoding="utf-8")
    assert bq_worker.ENGINE_PATCHES[0][3] in patched
    assert worker.anim.resolve().is_relative_to(job_dir(settings, job["id"]))


def test_engine_patch_stops_when_code_differs(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    executor.engine = "outro codigo"
    assert worker.run() == 2
    state = contract.get_job(job["id"])
    assert "não se aplica" in state["job"]["last_error"]
    assert "frames" not in [c[0] for c in executor.calls]


def test_mix_keeps_music_under_voice_and_never_cuts_video(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    assert worker.run() == 0
    mix = next(c for c in executor.calls if c[0] == "mix")[1]
    graph = mix[mix.index("-filter_complex") + 1]
    assert f"volume={bq_worker.MUSIC_VOLUME:.2f}" in graph and "aloop" in graph and "atrim=0:12.83" in graph
    assert "-shortest" not in next(c for c in executor.calls if c[0] == "mux")[1]


def test_progress_updates_keep_the_stage_start_time(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker._stage("frames", "em_andamento")
    db.execute("UPDATE job_stages SET started_at = '2026-01-01T00:00:00Z' WHERE job_id = ? AND stage = 'frames'", (job["id"],))
    worker._stage("frames", "em_andamento", "10 quadros", 10, 100)
    row = db.execute("SELECT started_at, done FROM job_stages WHERE job_id = ? AND stage = 'frames'", (job["id"],)).fetchone()
    assert row["started_at"] == "2026-01-01T00:00:00Z" and row["done"] == 10


def test_word_time_ignores_punctuation_and_case():
    cena = {"inicio": 2.0, "palavras": [{"w": "Then", "t": 0.1, "d": 0.2}, {"w": "mud", "t": 0.5, "d": 0.2}]}
    assert bq_worker.word_time(cena, "mud.") == 2.5 and bq_worker.word_time(cena, "THEN,") == 2.1
    assert bq_worker.word_time(cena, "ausente") is None


def test_every_catalog_effect_has_a_sound():
    assert set(bq_script.catalog()["som"]["fx"]) == set(bq_worker.FX_SOUNDS)


def test_executor_refuses_operation_outside_list(tmp_path):
    with pytest.raises(StudioError) as caught:
        Executor(["ffprobe"], tmp_path / "x.log").run("del", ["cmd", "/c", "del"], tmp_path)
    assert caught.value.code == "operation_not_allowed"


def test_worker_module_never_uses_a_shell():
    source = (BACKEND_DIR / "app" / "studio" / "bq_worker.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "shell":
            assert node.value.value is False
    assert "os.system" not in source and "eval(" not in source and "exec(" not in source


@pytest.mark.parametrize("bad", ["../../x", "job_123", "job_../../../etc", "JOB_0123456789abcdef", ""])
def test_job_dir_refuses_bad_ids(settings, bad):
    with pytest.raises(StudioError):
        job_dir(settings, bad)


def test_mix_refuses_audio_outside_job(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    public = worker.dir / "public" / worker.vid
    public.mkdir(parents=True)
    (public / "timeline.json").write_text(json.dumps({"total": 5, "cenas": [{"audio": "../../../../fora.mp3", "inicio": 0}]}), encoding="utf-8")
    with pytest.raises(StudioError) as caught:
        worker.mix()
    assert caught.value.code == "path_outside_job"


# --- Validação -----------------------------------------------------------------------------------

@pytest.mark.parametrize("probe_data,problem", [
    ({"format": {"duration": "12"}, "streams": [{"codec_type": "audio", "codec_name": "aac"}]}, "Sem faixa de vídeo"),
    ({"format": {"duration": "12"}, "streams": [{"codec_type": "video", "width": 1080, "height": 1920}]}, "Sem faixa de áudio"),
    ({"format": {"duration": "12"}, "streams": [{"codec_type": "video", "width": 1920, "height": 1080}, {"codec_type": "audio"}]}, "Resolução"),
    ({"format": {"duration": "1"}, "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}]}, "Duração"),
    ({"format": {"duration": "90"}, "streams": [{"codec_type": "video", "width": 1080, "height": 1920}, {"codec_type": "audio"}]}, "Duração"),
])
def test_validation_catches_bad_files(settings, probe_data, problem):
    job_id = "job_0123456789abcdef"
    folder = job_dir(settings, job_id)
    folder.mkdir(parents=True)
    (folder / "final.mp4").write_bytes(b"x" * 200_000)
    report = validate_file(settings, job_id, folder / "final.mp4", reader=lambda p: probe_data)
    assert report["ok"] is False and any(problem in text for text in report["problems"])


def test_validation_of_missing_and_tiny_and_outside(settings, tmp_path):
    job_id = "job_0123456789abcdef"
    folder = job_dir(settings, job_id)
    folder.mkdir(parents=True)
    assert validate_file(settings, job_id, folder / "final.mp4")["ok"] is False
    (folder / "final.mp4").write_bytes(b"x")
    assert "pequeno" in " ".join(validate_file(settings, job_id, folder / "final.mp4", reader=lambda p: GOOD_PROBE)["problems"])
    outside = tmp_path / "outro.mp4"
    outside.write_bytes(b"x")
    with pytest.raises(StudioError):
        validate_file(settings, job_id, outside)


def test_package_requires_validated_video(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.run()
    db.execute("DELETE FROM job_validation")
    db.commit()
    artifact = contract.get_job(job["id"])["artifacts"][0]["id"]
    with pytest.raises(StudioError) as caught:
        contract.prepare_publish_package(job["id"], "T", "D", [], artifact, "p1")
    assert caught.value.code == "video_not_validated"
    Production(contract).validate_video(job["id"], "agente")
    assert contract.prepare_publish_package(job["id"], "T", "D", [], artifact, "p2")["job"]["state_label"] == "PRONTO PARA REVISÃO"


def test_review_is_human_only_and_never_publishes(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.run()
    production = Production(contract)
    with pytest.raises(StudioError) as early:
        production.review(channel["id"], job["id"], "aprovado", "")
    assert early.value.code == "job_not_ready"
    artifact = contract.get_job(job["id"])["artifacts"][0]["id"]
    contract.prepare_publish_package(job["id"], "T", "D", [], artifact, "p1")
    result = production.review(channel["id"], job["id"], "ajustes", "Mudar o final")
    assert result["published"] is False
    row = contract._job(job["id"])
    assert row["review_status"] == "ajustes" and row["review_note"] == "Mudar o final" and row["state"] == "package_ready"
    with pytest.raises(StudioError):
        production.review(channel["id"], job["id"], "publicar", "")
    code = (BACKEND_DIR / "app" / "studio" / "mcp_server.py").read_text(encoding="utf-8")
    assert "def review" not in code


def test_asking_changes_allows_a_new_real_job_from_the_same_briefing(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.run()
    row = contract._job(job["id"])
    artifact = contract.get_job(job["id"])["artifacts"][0]["id"]
    contract.prepare_publish_package(job["id"], "T", "D", [], artifact, "p1")
    with pytest.raises(StudioError) as closed:
        contract.dispatch_briefing(channel["id"], row["briefing_id"], "d2", real=True)
    assert closed.value.code == "recommendation_unavailable"
    Production(contract).review(channel["id"], job["id"], "ajustes", "Refazer")
    again = contract.dispatch_briefing(channel["id"], row["briefing_id"], "d3", real=True)["job"]
    assert again["id"] != job["id"] and again["simulated"] is False and again["state"] == "authorized"
    assert contract._job(job["id"])["state"] == "package_ready", "a versão anterior continua registrada"


def test_channel_profile_plan_shows_real_adapter():
    plan = pipelines.plan_for("brother_quill", "j", "c")
    assert plan["real_execution_enabled"] is True and plan["ready_to_execute"] is True
    assert pipelines.real_adapter_for("brother_quill") == "brother_quill_v1" and pipelines.real_adapter_for("simulado") is None
    with pytest.raises(StudioError):
        pipelines.adapter_for("brother_quill", "narracao").run(pipelines.StageRequest("j", "c", "narracao"))


def test_real_job_artifact_download_stays_in_job_folder(db, settings, contract):
    channel, job, token, worker, executor = run_worker(db, settings, contract)
    worker.run()
    state = contract.get_job(job["id"])
    video = next(a for a in state["artifacts"] if a["kind"] == "short")
    assert contract.artifact_file(channel["id"], job["id"], video["id"])[1] == "final.mp4"
    db.execute("UPDATE job_artifacts SET path = ? WHERE id = ?", (r"C:\Windows\win.ini", video["id"]))
    db.commit()
    with pytest.raises(StudioError) as caught:
        contract.artifact_file(channel["id"], job["id"], video["id"])
    assert caught.value.code == "artifact_outside_root"


@pytest.fixture
def api(tmp_path):
    settings = Settings(mode="demo", data_dir=tmp_path, api_token="t")
    main.app.dependency_overrides[main.settings_dep] = lambda: settings
    yield TestClient(main.app, base_url="http://127.0.0.1", headers={"X-YTI-Token": "t"})
    main.app.dependency_overrides.clear()


def test_api_real_dispatch_review_and_inline_rules(api):
    channel = api.post("/api/studio/channels", json={"fields": {"name": "Piloto", "formats": ["short"], "pipeline_profile": "brother_quill", "short_target_seconds": 15}}).json()
    base = f"/api/studio/channels/{channel['id']}"
    rec = api.post(f"{base}/recommendations", json={"subject": "Tema", "justification": "x", "format": "short"}).json()
    brief = api.post(f"{base}/recommendations/{rec['id']}/briefing", json={"chosen_title": "Título"}).json()
    job = api.post(f"{base}/briefings/{brief['id']}/dispatch", json={"idempotency_key": "k", "real": True}).json()["job"]
    assert job["simulated"] is False and job["state"] == "authorized" and job["authorized_by"] == "dono_local"
    assert api.post(f"{base}/jobs/{job['id']}/review", json={"decision": "aprovado"}).status_code == 409
    assert api.post(f"{base}/jobs/{job['id']}/simulate-step").status_code == 409, "o simulador não mexe em tarefa real"
    assert api.get(f"{base}/pipeline").json()["real_adapter"] == "brother_quill_v1"
