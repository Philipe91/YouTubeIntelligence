"""Adaptadores de pipeline: o estúdio pede uma etapa sem saber quem a executa.

Hoje só o adaptador simulado roda. O adaptador de comando apenas descreve o que seria executado:
este módulo não importa subprocess, de propósito, e não grava nada nos projetos externos.
Ligar um pipeline real exige escrever um adaptador novo, revisado, com autorização do dono.
"""
from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from ..config import BACKEND_DIR
from .store import StudioError

STAGES: tuple[tuple[str, str, int], ...] = (
    ("roteiro", "Roteiro", 20),
    ("narracao", "Narração", 40),
    ("animacao", "Animação", 60),
    ("renderizacao", "Renderização", 80),
    ("thumbnail", "Thumbnail", 100),
)
DEFAULT_PROFILE = "simulado"
CONFIG_PATH = BACKEND_DIR / "config" / "pipelines.toml"


@dataclass(frozen=True)
class StageRequest:
    job_id: str
    channel_id: str
    stage: str
    briefing: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageResult:
    stage: str
    summary: str
    simulated: bool


@dataclass(frozen=True)
class StagePlan:
    stage: str
    adapter: str
    can_execute: bool
    simulated: bool
    project: str | None = None
    project_found: bool | None = None
    command_preview: str | None = None
    output: str | None = None
    heavy: bool = False
    requires: tuple[str, ...] = ()
    notes: str | None = None
    blocked_reason: str | None = None


class PipelineAdapter(Protocol):
    """O que um pipeline precisa oferecer para entrar no estúdio."""

    def plan(self, request: StageRequest) -> StagePlan: ...
    def run(self, request: StageRequest) -> StageResult: ...


class SimulatedAdapter:
    """Não renderiza, não chama serviços e termina na hora."""

    def plan(self, request: StageRequest) -> StagePlan:
        return StagePlan(stage=request.stage, adapter="simulado", can_execute=True, simulated=True,
                         notes="Sem custo: nenhum arquivo pesado é gerado.")

    def run(self, request: StageRequest) -> StageResult:
        return StageResult(stage=request.stage, summary=f"Etapa {request.stage} simulada.", simulated=True)


class DescribedCommandAdapter:
    """Descreve um comando externo. Executar é recusado nesta versão."""

    REASON = "A execução de pipelines reais não está ligada nesta versão."

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def plan(self, request: StageRequest) -> StagePlan:
        project = self.config.get("project")
        return StagePlan(
            stage=request.stage, adapter="comando", can_execute=False, simulated=False, project=project,
            project_found=Path(project).expanduser().exists() if project else None, command_preview=self.config.get("command"),
            output=self.config.get("output"), heavy=bool(self.config.get("heavy")), requires=tuple(self.config.get("requires", ())),
            notes=self.config.get("notes"), blocked_reason=self.REASON,
        )

    def run(self, request: StageRequest) -> StageResult:
        raise StudioError("pipeline_execution_disabled", self.REASON, 409)


class UndefinedAdapter:
    """Etapa sem caminho identificado no projeto."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def plan(self, request: StageRequest) -> StagePlan:
        project = self.config.get("project")
        return StagePlan(stage=request.stage, adapter="indefinido", can_execute=False, simulated=False, project=project,
                         project_found=Path(project).exists() if project else None, notes=self.config.get("notes"),
                         blocked_reason="Esta etapa ainda não tem um caminho definido neste projeto.")

    def run(self, request: StageRequest) -> StageResult:
        raise StudioError("pipeline_stage_undefined", "Esta etapa não tem pipeline definido.", 409)


class WorkerAdapter:
    """Etapa atendida por um worker real, listado em execucao.toml. Quem executa é o worker, não este módulo."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def plan(self, request: StageRequest) -> StagePlan:
        return StagePlan(stage=request.stage, adapter=self.config["adapter"], can_execute=True, simulated=False, project=self.config.get("project"),
                         project_found=Path(self.config["project"]).expanduser().exists() if self.config.get("project") else None,
                         command_preview=self.config.get("command"), output=self.config.get("output"), heavy=bool(self.config.get("heavy")),
                         requires=tuple(self.config.get("requires", ())), notes=self.config.get("notes"))

    def run(self, request: StageRequest) -> StageResult:
        raise StudioError("use_worker", "Esta etapa é executada pelo worker, com start_production_run.", 409)


ADAPTERS = {"simulado": lambda _: SimulatedAdapter(), "comando": DescribedCommandAdapter, "indefinido": UndefinedAdapter, "brother_quill_v1": WorkerAdapter}


def real_adapter_for(profile: str) -> str | None:
    """Nome do adaptador real do perfil, se houver."""
    stages = load_profiles().get(profile, {}).get("stages", {})
    names = {config["adapter"] for config in stages.values()} - {"simulado", "comando", "indefinido"}
    return next(iter(names)) if len(names) == 1 else None


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)["profiles"]


def adapter_for(profile: str, stage: str) -> PipelineAdapter:
    profiles = load_profiles()
    if profile not in profiles:
        raise StudioError("unknown_pipeline_profile", f"Perfil de pipeline desconhecido: {profile}.", 422)
    config = profiles[profile]["stages"].get(stage)
    if config is None:
        raise StudioError("unknown_pipeline_stage", f"Etapa desconhecida: {stage}.", 422)
    return ADAPTERS[config["adapter"]](config)


def profile_options() -> list[dict[str, str]]:
    return [{"id": key, "label": value["label"]} for key, value in load_profiles().items()]


def plan_for(profile: str, job_id: str, channel_id: str, briefing: dict[str, Any] | None = None) -> dict[str, Any]:
    stages = []
    for key, label, _ in STAGES:
        request = StageRequest(job_id, channel_id, key, briefing or {})
        stages.append({**asdict(adapter_for(profile, key).plan(request)), "label": label})
    required = [stage for stage in stages if stage["stage"] not in load_profiles()[profile].get("optional", [])]
    return {
        "profile": profile, "label": load_profiles()[profile]["label"], "stages": stages,
        "ready_to_execute": all(stage["can_execute"] for stage in required),
        "real_execution_enabled": real_adapter_for(profile) is not None,
    }
