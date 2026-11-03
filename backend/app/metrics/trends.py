"""Tendências: termos cujos vídeos estão ganhando velocidade em vários canais."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .text import terms


@dataclass(frozen=True)
class TrendInput:
    video_id: str
    channel_id: str
    title: str
    format: str
    status: str
    recent_vph: float | None
    previous_vph: float | None


@dataclass(frozen=True)
class TrendTerm:
    term: str
    format: str
    videos: int
    channels: int
    accelerating: int
    accelerating_share: float
    recent_vph_sum: float
    previous_vph_sum: float
    velocity_ratio: float | None
    video_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_trends(items: list[TrendInput], config: dict[str, Any]) -> list[TrendTerm]:
    """Só entram vídeos com aceleração calculada. Formatos ficam separados."""
    buckets: dict[tuple[str, str], list[TrendInput]] = {}
    for item in items:
        if item.recent_vph is None or item.previous_vph is None:
            continue
        for term in terms(item.title):
            buckets.setdefault((term, item.format), []).append(item)

    results: list[TrendTerm] = []
    for (term, video_format), group in buckets.items():
        channels = {item.channel_id for item in group}
        if len(group) < config["min_videos"] or len(channels) < config["min_channels"]:
            continue
        rising = sum(1 for item in group if item.status in {"acelerando", "emergente"})
        if rising == 0:
            continue
        recent = sum(item.recent_vph for item in group)
        previous = sum(item.previous_vph for item in group)
        results.append(TrendTerm(
            term=term, format=video_format, videos=len(group), channels=len(channels), accelerating=rising,
            accelerating_share=rising / len(group), recent_vph_sum=recent, previous_vph_sum=previous,
            velocity_ratio=recent / previous if previous > 0 else None,
            video_ids=tuple(sorted(item.video_id for item in group)),
        ))
    results.sort(key=lambda t: (-t.accelerating_share, -(t.velocity_ratio or 0), -t.videos, t.term))
    return _drop_redundant(results)[: config["max_terms"]]


def _drop_redundant(items: list[TrendTerm]) -> list[TrendTerm]:
    """Remove uma palavra quando um par que a contém cobre exatamente os mesmos vídeos."""
    pairs = [item for item in items if " " in item.term]
    kept = []
    for item in items:
        redundant = " " not in item.term and any(
            pair.format == item.format and pair.video_ids == item.video_ids and item.term in pair.term.split()
            for pair in pairs
        )
        if not redundant:
            kept.append(item)
    return kept
