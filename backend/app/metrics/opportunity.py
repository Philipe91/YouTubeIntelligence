"""Ranking experimental de oportunidades. Indicadores separados, com justificativa."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .core import br_int, median
from .text import tokens


@dataclass(frozen=True)
class SampleVideo:
    video_id: str
    channel_id: str
    views: int | None
    age_days: float
    subscribers: int | None
    snapshot_count: int
    format: str


@dataclass(frozen=True)
class OpportunityInput:
    topic: str
    format: str
    videos: tuple[SampleVideo, ...]
    context_vocabulary: tuple[str, ...]
    total_results_approx: int | None = None


@dataclass(frozen=True)
class Opportunity:
    topic: str
    format: str
    demand: float | None
    competition: float | None
    relevance: float
    confidence: float
    score: float | None
    status: str  # ok | amostra_insuficiente
    sample_size: int
    distinct_channels: int
    median_views_per_day: float | None
    median_subscribers: float | None
    recent_share: float | None
    total_results_approx: int | None
    competition_parts: dict[str, float] = field(default_factory=dict)
    justification: tuple[str, ...] = ()
    video_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _log_scale(value: float, anchor: float) -> float:
    """0 a 100 em escala log; `anchor` corresponde a 100."""
    if value <= 0:
        return 0.0
    return min(100.0, 100.0 * math.log10(1 + value) / math.log10(1 + anchor))


def relevance_score(topic: str, vocabulary: tuple[str, ...]) -> float:
    """Parcela das palavras do tema presentes no vocabulário do nicho ou do canal."""
    topic_tokens = set(tokens(topic))
    if not topic_tokens:
        return 0.0
    known = set()
    for entry in vocabulary:
        known.update(tokens(entry))
    return 100.0 * len(topic_tokens & known) / len(topic_tokens)


def compute_opportunity(data: OpportunityInput, config: dict[str, Any]) -> Opportunity:
    """Vídeos de outro formato são ignorados, e nunca entram no mesmo cálculo."""
    sample = [v for v in data.videos if v.format == data.format and v.views is not None and v.age_days > 0]
    n = len(sample)
    relevance = relevance_score(data.topic, data.context_vocabulary)
    channels = {v.channel_id for v in sample}

    views_per_day = median([v.views / v.age_days for v in sample]) if sample else None
    demand = _log_scale(views_per_day, config["demand_anchor_views_per_day"]) if views_per_day is not None else None

    subs = [float(v.subscribers) for v in sample if v.subscribers is not None]
    median_subs = median(subs) if subs else None
    recent_share = sum(1 for v in sample if v.age_days <= config["recent_days"]) / n if n else None

    parts: list[tuple[str, float, float]] = []
    if median_subs is not None:
        parts.append(("porte_dos_canais", _log_scale(median_subs, config["competition_anchor_subscribers"]),
                      config["competition_weight_authority"]))
    if recent_share is not None:
        parts.append(("oferta_recente", 100.0 * recent_share, config["competition_weight_supply"]))
    if data.total_results_approx is not None:
        parts.append(("resultados_aproximados", _log_scale(data.total_results_approx, config["saturation_anchor_results"]),
                      config["competition_weight_saturation"]))
    # Componente ausente sai da conta, e os pesos restantes são redistribuídos.
    total_weight = sum(weight for _, _, weight in parts)
    competition = sum(value * weight for _, value, weight in parts) / total_weight if total_weight else None

    confidence = _confidence(sample, channels, config)
    can_score = demand is not None and competition is not None and confidence >= config["min_confidence"]
    score = None
    if can_score:
        score = (config["weight_demand"] * demand
                 + config["weight_competition"] * (100.0 - competition)
                 + config["weight_relevance"] * relevance)

    return Opportunity(
        topic=data.topic, format=data.format, demand=demand, competition=competition, relevance=relevance,
        confidence=confidence, score=score, status="ok" if can_score else "amostra_insuficiente",
        sample_size=n, distinct_channels=len(channels), median_views_per_day=views_per_day,
        median_subscribers=median_subs, recent_share=recent_share, total_results_approx=data.total_results_approx,
        competition_parts={name: value for name, value, _ in parts},
        justification=_justify(n, len(channels), views_per_day, median_subs, recent_share, relevance, confidence, can_score, config),
        video_ids=tuple(v.video_id for v in sample),
    )


def _confidence(sample: list[SampleVideo], channels: set[str], config: dict[str, Any]) -> float:
    if not sample:
        return 0.0
    size = min(1.0, len(sample) / config["confidence_full_sample"])
    diversity = min(1.0, len(channels) / config["confidence_full_channels"])
    tracked = sum(1 for v in sample if v.snapshot_count >= 2) / len(sample)
    return 100.0 * (0.4 * size + 0.3 * diversity + 0.3 * tracked)


def _justify(n, channels, views_per_day, median_subs, recent_share, relevance, confidence, can_score, config) -> tuple[str, ...]:
    lines: list[str] = []
    if n == 0:
        return ("Nenhum vídeo com views disponíveis neste formato.",)
    lines.append(f"Amostra de {n} vídeos de {channels} canais.")
    if views_per_day is not None:
        lines.append(f"Mediana de {br_int(views_per_day)} views por dia na amostra (proxy de demanda, não é volume de busca).")
    if median_subs is not None:
        lines.append(f"Canais da amostra têm mediana de {br_int(median_subs)} inscritos.")
    else:
        lines.append("Inscritos indisponíveis na amostra: porte dos canais fora da conta.")
    if recent_share is not None:
        lines.append(f"{recent_share * 100:.0f}% da amostra saiu nos últimos {config['recent_days']} dias.")
    lines.append(f"{relevance:.0f}% das palavras do tema estão no vocabulário do nicho ou do canal.")
    if not can_score:
        lines.append(f"Confiança {confidence:.0f} abaixo do mínimo de {config['min_confidence']:.0f}: sem pontuação.")
    return tuple(lines)
