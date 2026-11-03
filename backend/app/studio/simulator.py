"""Agente simulado: percorre o contrato sem renderizar nada e sem gerar arquivos.

Cada chamada avança uma etapa, de propósito leve. Recusa tarefas reais.
"""
from __future__ import annotations

import json

from .contract import SIMULATED_PREFIX, Contract
from .store import StudioError

AGENT_ID = "agente_simulado"
STEPS = [(20, "Roteiro"), (40, "Narração"), (60, "Animação"), (80, "Render"), (100, "Revisão de qualidade")]


def _require_simulated(contract: Contract, job_id: str, channel_id: str):
    contract.recover_stale()
    job = contract._job(job_id, channel_id)
    if not job["simulated"]:
        raise StudioError("not_simulated", "O simulador não atua em tarefas reais.", 409)
    return job


def simulate_step(contract: Contract, job_id: str, channel_id: str) -> dict:
    job = _require_simulated(contract, job_id, channel_id)
    attempt = job["attempts"]
    if job["state"] == "authorized":
        contract.claim_job(job_id, AGENT_ID, f"sim:{job_id}:claim:{attempt + 1}")
        return contract.get_job(job_id)
    if job["state"] == "running":
        token = job["lease_token"]
        following = next((step for step in STEPS if step[0] > job["progress"]), None)
        if following:
            contract.update_progress(job_id, token, following[0], following[1], f"sim:{job_id}:{attempt}:{following[0]}")
            return contract.get_job(job_id)
        contract.deliver_artifacts(job_id, token, [
            {"kind": job["format"] if job["format"] in {"short"} else "video", "path": f"{SIMULATED_PREFIX}{job_id}/video.mp4", "label": "Vídeo simulado"},
            {"kind": "thumbnail", "path": f"{SIMULATED_PREFIX}{job_id}/thumbnail.png", "label": "Thumbnail simulada"},
        ], f"sim:{job_id}:{attempt}:deliver")
        return contract.get_job(job_id)
    if job["state"] == "delivered":
        rows = contract.conn.execute("SELECT id, kind FROM job_artifacts WHERE job_id = ?", (job_id,)).fetchall()
        video = next(r["id"] for r in rows if r["kind"] in {"video", "short"})
        thumb = next((r["id"] for r in rows if r["kind"] == "thumbnail"), None)
        recommendation = contract.conn.execute("SELECT titles_json, justification FROM recommendations WHERE id = ?", (job["recommendation_id"],)).fetchone()
        title = json.loads(recommendation["titles_json"])[0] if recommendation else job["title"]
        contract.prepare_publish_package(job_id, title[:100], "Descrição simulada para revisão. Nada será enviado ao YouTube.", ["simulacao"], video,
                                         f"sim:{job_id}:{attempt}:package", thumbnail_artifact_id=thumb, agent_id=AGENT_ID)
        return contract.get_job(job_id)
    raise StudioError("nothing_to_simulate", f"Não há etapa a simular com a tarefa em '{job['state']}'.", 409)


def simulate_failure(contract: Contract, job_id: str, channel_id: str) -> dict:
    """Falha com nova tentativa, para ver a recuperação funcionando."""
    job = _require_simulated(contract, job_id, channel_id)
    if job["state"] != "running":
        raise StudioError("job_not_running", "Só uma tarefa em execução pode falhar.", 409)
    contract.report_failure(job_id, job["lease_token"], "Falha simulada na etapa atual.", True, f"sim:{job_id}:{job['attempts']}:fail")
    return contract.get_job(job_id)
