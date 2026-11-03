"""Aceleração: compara a velocidade em duas janelas sucessivas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

from .core import VideoSeries, br_dec, interpolate_views_at_time, regime_changes_between


@dataclass(frozen=True)
class AccelerationResult:
    status: str  # acelerando | estavel | desacelerando | emergente | dados_insuficientes
    recent_vph: float | None = None
    previous_vph: float | None = None
    ratio: float | None = None
    window_hours: float = 0.0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_acceleration(series: VideoSeries, config: dict[str, Any]) -> AccelerationResult:
    window = float(config["window_hours"])
    snapshots = series.valid_snapshots()
    if len(snapshots) < 3:
        return AccelerationResult(
            "dados_insuficientes", window_hours=window,
            explanation=f"{len(snapshots)} snapshots. São necessários ao menos 3 cobrindo duas janelas de {window:.0f} h.",
        )
    end = snapshots[-1].captured_at
    middle = end - timedelta(hours=window)
    start = end - timedelta(hours=2 * window)
    max_gap = window * config["max_gap_factor"]
    views_start = interpolate_views_at_time(snapshots, start, max_gap)
    views_middle = interpolate_views_at_time(snapshots, middle, max_gap)
    views_end = float(snapshots[-1].views)
    if views_start is None or views_middle is None:
        return AccelerationResult(
            "dados_insuficientes", window_hours=window,
            explanation=f"Os snapshots não cobrem as duas últimas janelas de {window:.0f} h.",
        )
    if regime_changes_between(start, end, series.format):
        return AccelerationResult(
            "dados_insuficientes", window_hours=window, warnings=("cruza_mudanca_de_contagem",),
            explanation="As janelas cruzam uma mudança na contagem de views: a comparação não é válida.",
        )
    if views_middle < views_start or views_end < views_middle:
        return AccelerationResult(
            "dados_insuficientes", window_hours=window, warnings=("contagem_diminuiu",),
            explanation="A contagem diminuiu dentro das janelas, então a velocidade não é confiável.",
        )

    recent = (views_end - views_middle) / window
    previous = (views_middle - views_start) / window
    base = {"recent_vph": recent, "previous_vph": previous, "window_hours": window}
    if previous == 0:
        if recent >= config["min_recent_vph"]:
            return AccelerationResult(
                "emergente", **base,
                explanation=f"Sem views na janela anterior e {br_dec(recent)} views/h na mais recente.",
            )
        return AccelerationResult("estavel", **base, explanation="Sem movimento relevante nas duas janelas.")

    ratio = recent / previous
    if recent < config["min_recent_vph"]:
        status = "estavel"
    elif ratio >= config["ratio_up"]:
        status = "acelerando"
    elif ratio <= config["ratio_down"]:
        status = "desacelerando"
    else:
        status = "estavel"
    return AccelerationResult(
        status, ratio=ratio, **base,
        explanation=f"{br_dec(recent)} views/h nas últimas {window:.0f} h, contra {br_dec(previous)} views/h nas {window:.0f} h anteriores.",
    )
