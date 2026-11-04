"""Produção real pelo contrato: roteiro, início do worker, validação e revisão humana."""
from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ..config import BACKEND_DIR
from ..db import to_iso, utcnow
from .bq_script import validate_script
from .bq_worker import STAGES, free_ram_gb, job_dir, store_validation, validate_file
from .contract import Contract
from .pipelines import real_adapter_for
from .store import StudioError, get_channel

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
BREAKAWAY = 0x01000000  # CREATE_BREAKAWAY_FROM_JOB


def spawn_worker(job_id: str, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        def start(flags: int) -> subprocess.Popen:
            return subprocess.Popen([sys.executable, "-m", "app.studio.bq_worker", job_id], cwd=BACKEND_DIR, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                    creationflags=flags, close_fds=True, env=_env())
        try:
            # O worker precisa sobreviver ao fim da sessão do agente, que fecha o servidor MCP.
            return start(DETACHED | BREAKAWAY).pid
        except OSError:
            return start(DETACHED).pid


def _env() -> dict[str, str]:
    import os

    return {**os.environ, "PYTHONPATH": str(BACKEND_DIR), "PYTHONUTF8": "1"}


class Production:
    def __init__(self, contract: Contract, spawn: Callable[[str, Path], int] = spawn_worker, ram: Callable[[], float] = free_ram_gb):
        self.contract, self.conn, self.settings = contract, contract.conn, contract.settings
        self.spawn, self.ram = spawn, ram

    def _real_job(self, job_id: str):
        job = self.contract._job(job_id)
        if job["simulated"]:
            raise StudioError("not_real_job", "Esta operação é só para tarefa real.", 409)
        return job

    def _adapter(self, job) -> str:
        channel = get_channel(self.conn, job["channel_id"])
        adapter = real_adapter_for(channel["pipeline_profile"])
        execution = self.settings.execution
        if not execution["real_execution_enabled"]:
            raise StudioError("real_execution_disabled", "A execução real está desligada em execucao.toml.", 403)
        if adapter is None or adapter not in execution["allowed_adapters"]:
            raise StudioError("adapter_not_allowed", "O perfil deste canal não tem adaptador permitido.", 403)
        return adapter

    def submit_script(self, job_id: str, lease_token: str, script: dict, idempotency_key: str, agent_id: str) -> dict:
        clean = validate_script(script)

        def action() -> dict:
            job = self._real_job(job_id)
            self.contract._require_lease(job, lease_token)
            self.conn.execute(
                "INSERT OR REPLACE INTO job_scripts (job_id, payload_json, submitted_by, submitted_at) VALUES (?, ?, ?, ?)",
                (job_id, json.dumps(clean, ensure_ascii=False), agent_id[:100], to_iso(utcnow())),
            )
            words = sum(len(cena["texto"].split()) for cena in clean["cenas"])
            self.contract._event(job_id, "info", "state", f"Roteiro recebido de {agent_id[:100]}: {len(clean['cenas'])} cenas, {words} palavras.")
            return {"accepted": True, "scenes": len(clean["cenas"]), "words": words}

        return self.contract._idempotent("submit_script", idempotency_key, {"job": job_id, "script": clean}, action)

    def start_run(self, job_id: str, lease_token: str, idempotency_key: str) -> dict:
        """Inicia o worker em processo próprio e devolve na hora. Acompanhe com get_job."""
        job = self._real_job(job_id)
        adapter = self._adapter(job)
        self.contract._require_lease(job, lease_token)
        if self.conn.execute("SELECT 1 FROM job_scripts WHERE job_id = ?", (job_id,)).fetchone() is None:
            raise StudioError("script_required", "Envie o roteiro com submit_script antes.", 409)
        others = self.conn.execute(
            """SELECT DISTINCT s.job_id FROM job_stages s JOIN production_jobs j ON j.id = s.job_id
               WHERE s.status = 'em_andamento' AND j.state = 'running' AND s.job_id != ?""", (job_id,)).fetchall()
        if others:
            raise StudioError("another_run_active", "Outra produção real está em andamento. Só uma por vez.", 409, retryable=True)
        floor = self.settings.execution["min_free_ram_gb_to_start"]
        free = self.ram()
        if free < floor:
            raise StudioError("low_memory", f"Memória livre em {free:.1f} GB. O mínimo para iniciar é {floor} GB.", 409, retryable=True)

        def action() -> dict:
            current = self.contract._job(job_id)
            self.contract._require_lease(current, lease_token)
            for position, (stage, label) in enumerate(STAGES):
                self.conn.execute(
                    """INSERT INTO job_stages (job_id, stage, position, label, status) VALUES (?, ?, ?, ?, 'pendente')
                       ON CONFLICT(job_id, stage) DO UPDATE SET status = 'pendente', detail = '', started_at = NULL, ended_at = NULL""",
                    (job_id, stage, position, label),
                )
            self.contract._event(job_id, "info", "state", f"Execução real iniciada com {adapter}. Memória livre: {free:.1f} GB.")
            return {"started": True, "adapter": adapter, "free_ram_gb": round(free, 1)}

        result = self.contract._idempotent("start_run", idempotency_key, {"job": job_id}, action)
        if not result["replayed"]:
            result["pid"] = self.spawn(job_id, job_dir(self.settings, job_id) / "saida_worker.log")
        return result

    def validate_video(self, job_id: str, agent_id: str) -> dict:
        """Confere o arquivo final no disco. O resultado não vem da palavra do worker."""
        job = self._real_job(job_id)
        if job["state"] not in {"delivered", "package_ready"}:
            raise StudioError("job_not_delivered", f"A tarefa está em '{job['state']}'.", 409)
        report = validate_file(self.settings, job_id, job_dir(self.settings, job_id) / "final.mp4")
        store_validation(self.conn, job_id, report, agent_id[:100])
        self.contract._touch(agent_id, job["channel_id"], "validate_video")
        self.conn.commit()
        return report

    def review(self, channel_id: str, job_id: str, decision: str, note: str) -> dict:
        """Ação humana, pelo painel. Não publica nada."""
        if decision not in {"aprovado", "ajustes"}:
            raise StudioError("invalid_field", "Decisão inválida.", 422)
        job = self.contract._job(job_id, channel_id)
        if job["state"] != "package_ready":
            raise StudioError("job_not_ready", "A tarefa ainda não está pronta para revisão.", 409)
        stamp = to_iso(utcnow())
        self.contract._set_job(job_id, review_status=decision, review_note=note.strip()[:1000], reviewed_at=stamp)
        self.contract._event(job_id, "info", "state", f"Revisão do dono: {decision}. Nada foi publicado.")
        self.conn.commit()
        return {"review_status": decision, "published": False}


def real_dispatch_check(contract: Contract, channel_id: str, duration_seconds: int) -> None:
    """Confere o que é preciso antes de o dono liberar uma tarefa real."""
    channel = get_channel(contract.conn, channel_id)
    execution = contract.settings.execution
    adapter = real_adapter_for(channel["pipeline_profile"])
    if not execution["real_execution_enabled"]:
        raise StudioError("real_execution_disabled", "A execução real está desligada em execucao.toml.", 403)
    if adapter is None or adapter not in execution["allowed_adapters"]:
        raise StudioError("adapter_not_allowed", "O perfil deste canal não tem adaptador permitido.", 403)
    if duration_seconds > execution["max_video_seconds"]:
        raise StudioError("video_too_long", f"O limite atual é de {execution['max_video_seconds']} s.", 422)
