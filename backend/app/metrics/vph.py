"""VPH observado (entre snapshots) e média histórica. São coisas diferentes."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .core import Snapshot, VideoSeries, hours_between, regime_changes_between


@dataclass(frozen=True)
class VphInterval:
    start: datetime
    end: datetime
    hours: float
    delta_views: int
    vph: float | None
    flags: tuple[str, ...] = field(default_factory=tuple)


def observed_intervals(series: VideoSeries, config: dict[str, Any]) -> list[VphInterval]:
    """VPH observado = diferença de views / horas entre snapshots consecutivos."""
    snapshots = series.valid_snapshots()
    intervals: list[VphInterval] = []
    for left, right in zip(snapshots, snapshots[1:]):
        intervals.append(_interval(left, right, series.format, config))
    return intervals


def _interval(left: Snapshot, right: Snapshot, video_format: str, config: dict[str, Any]) -> VphInterval:
    hours = hours_between(left.captured_at, right.captured_at)
    delta = right.views - left.views
    flags: list[str] = []
    value: float | None = None
    if hours < config["min_interval_hours"]:
        flags.append("intervalo_curto")
    elif delta < 0:
        # O YouTube pode corrigir contagens para baixo; não é velocidade negativa.
        flags.append("contagem_diminuiu")
    else:
        value = delta / hours
    if hours > config["coarse_interval_hours"]:
        flags.append("intervalo_longo")
    if regime_changes_between(left.captured_at, right.captured_at, video_format):
        flags.append("cruza_mudanca_de_contagem")
    return VphInterval(left.captured_at, right.captured_at, hours, delta, value, tuple(flags))


def latest_observed(series: VideoSeries, config: dict[str, Any]) -> VphInterval | None:
    """Último intervalo com valor, ou None se não houver dois snapshots válidos."""
    for interval in reversed(observed_intervals(series, config)):
        if interval.vph is not None:
            return interval
    return None


def historical_average(views: int | None, published_at: datetime, as_of: datetime) -> float | None:
    """Média desde a publicação (views / idade). Não representa velocidade recente."""
    if views is None:
        return None
    age = hours_between(published_at, as_of)
    if age <= 0:
        return None
    return views / age
