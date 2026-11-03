"""Tipos e funções estatísticas compartilhadas."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property

# Mudanças na contagem de views divulgadas pelo YouTube (data, formatos afetados, descrição).
COUNT_REGIME_CHANGES: tuple[tuple[datetime, frozenset[str], str], ...] = (
    (datetime(2025, 3, 31, tzinfo=UTC), frozenset({"short"}),
     "Shorts passaram a contar cada início ou repetição (31/03/2025)"),
    (datetime(2026, 8, 24, tzinfo=UTC), frozenset({"short", "long", "live"}),
     "Views passaram a contar no início da reprodução em todos os formatos (24/08/2026)"),
)


@dataclass(frozen=True)
class Snapshot:
    captured_at: datetime
    views: int | None


@dataclass(frozen=True)
class VideoSeries:
    video_id: str
    channel_id: str
    format: str
    published_at: datetime
    snapshots: tuple[Snapshot, ...] = field(default_factory=tuple)

    @cached_property
    def _valid(self) -> list[Snapshot]:
        return sorted((s for s in self.snapshots if s.views is not None), key=lambda s: s.captured_at)

    def valid_snapshots(self) -> list[Snapshot]:
        """Snapshots com views conhecidas, em ordem cronológica."""
        return self._valid


def br_int(value: float) -> str:
    """1234567 -> 1.234.567"""
    return f"{value:,.0f}".replace(",", ".")


def br_dec(value: float) -> str:
    """60.74 -> 60,7"""
    return f"{value:,.1f}".replace(",", "§").replace(".", ",").replace("§", ".")


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("mediana de lista vazia")
    return float(statistics.median(values))


def mad(values: list[float]) -> float:
    """Desvio absoluto mediano."""
    center = median(values)
    return median([abs(value - center) for value in values])


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def regime_changes_between(start: datetime, end: datetime, video_format: str) -> list[str]:
    return [
        description
        for moment, formats, description in COUNT_REGIME_CHANGES
        if video_format in formats and start < moment <= end
    ]


def interpolate_views_at_time(
    snapshots: list[Snapshot], moment: datetime, max_gap_hours: float
) -> float | None:
    """Views em `moment`, sem extrapolar. Exige snapshots dos dois lados dentro do limite."""
    if not snapshots or moment < snapshots[0].captured_at or moment > snapshots[-1].captured_at:
        return None
    for left, right in zip(snapshots, snapshots[1:]):
        if left.captured_at <= moment <= right.captured_at:
            gap = hours_between(left.captured_at, right.captured_at)
            if gap > max_gap_hours:
                return None
            if gap == 0:
                return float(right.views)
            weight = hours_between(left.captured_at, moment) / gap
            return left.views + (right.views - left.views) * weight
    return float(snapshots[-1].views) if snapshots[-1].captured_at == moment else None
