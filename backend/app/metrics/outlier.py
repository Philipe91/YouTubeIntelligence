"""IDR: desempenho relativo a vídeos do mesmo canal, formato e idade."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from .core import VideoSeries, br_dec, br_int, hours_between, interpolate_views_at_time, mad, median, regime_changes_between


@dataclass(frozen=True)
class OutlierResult:
    status: str  # ok | insufficient_sample | too_young | no_views | unknown_format
    idr: float | None = None
    robust_z: float | None = None
    band: str | None = None
    confidence: str | None = None
    sample_size: int = 0
    measured_peers: int = 0
    band_peers: int = 0
    peer_median_views: float | None = None
    target_views: int | None = None
    age_hours: float | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def views_at_age(series: VideoSeries, age_hours: float, config: dict[str, Any]) -> float | None:
    """Views do par na idade pedida, medidas ou interpoladas. Nunca extrapola."""
    snapshots = series.valid_snapshots()
    if not snapshots:
        return None
    best = min(snapshots, key=lambda s: abs(hours_between(series.published_at, s.captured_at) - age_hours))
    best_age = hours_between(series.published_at, best.captured_at)
    if age_hours > 0 and abs(best_age - age_hours) / age_hours <= config["age_tolerance"]:
        return float(best.views)
    moment = series.published_at + _hours(age_hours)
    max_gap = max(config["max_gap_floor_hours"], config["max_gap_factor"] * age_hours)
    return interpolate_views_at_time(snapshots, moment, max_gap)


def _hours(value: float):
    from datetime import timedelta

    return timedelta(hours=value)


def _band(idr: float, config: dict[str, Any]) -> str:
    if idr >= config["band_extreme"]:
        return "extremo"
    if idr >= config["band_high"]:
        return "muito_acima"
    if idr >= config["band_above"]:
        return "acima"
    if idr >= config["band_below"]:
        return "tipico"
    return "abaixo"


def compute_outlier(target: VideoSeries, peers: list[VideoSeries], config: dict[str, Any]) -> OutlierResult:
    if target.format not in {"short", "long", "live"}:
        return OutlierResult("unknown_format", explanation="Formato desconhecido: sem comparação.")
    snapshots = target.valid_snapshots()
    if not snapshots:
        return OutlierResult("no_views", explanation="O vídeo não tem contagem de views disponível.")
    latest = snapshots[-1]
    age = hours_between(target.published_at, latest.captured_at)
    if age < config["min_age_hours"]:
        return OutlierResult(
            "too_young", target_views=latest.views, age_hours=age,
            explanation=f"Vídeo com {br_dec(age)} h. O mínimo para comparar é {br_int(config['min_age_hours'])} h.",
        )

    measured: list[float] = []
    banded: list[float] = []
    warnings: set[str] = set()
    for peer in peers:
        if peer.video_id == target.video_id or peer.format != target.format:
            continue
        if peer.channel_id != target.channel_id:
            continue
        value = views_at_age(peer, age, config)
        if value is not None:
            measured.append(value)
            when = peer.published_at + _hours(age)
            _note_regime(warnings, when, latest.captured_at, target.format)
            continue
        peer_snapshots = peer.valid_snapshots()
        if peer_snapshots:
            peer_age = hours_between(peer.published_at, peer_snapshots[-1].captured_at)
            if age / config["band_factor"] <= peer_age <= age * config["band_factor"]:
                banded.append(float(peer_snapshots[-1].views))
                _note_regime(warnings, peer_snapshots[-1].captured_at, latest.captured_at, target.format)

    values = measured + banded
    n = len(values)
    if n < config["min_sample"]:
        return OutlierResult(
            "insufficient_sample", sample_size=n, measured_peers=len(measured), band_peers=len(banded),
            target_views=latest.views, age_hours=age,
            explanation=f"Só {n} vídeos comparáveis. O mínimo é {config['min_sample']}.",
        )

    center = median(values)
    idr = latest.views / center if center > 0 else None
    logs = [math.log1p(value) for value in values]
    spread = mad(logs)
    z = None
    if spread > 0:
        z = (math.log1p(latest.views) - median(logs)) / (1.4826 * spread)
    else:
        warnings.add("dispersao_zero")

    measured_share = len(measured) / n
    if n >= config["high_sample"] and measured_share >= config["high_measured_share"]:
        confidence = "alta"
    elif n >= config["medium_sample"]:
        confidence = "media"
    else:
        confidence = "baixa"

    if idr is None:
        warnings.add("mediana_zero")
        explanation = f"A mediana de {n} vídeos comparáveis é zero: razão indefinida."
    else:
        explanation = (
            f"{br_int(latest.views)} views em {br_int(age)} h ÷ mediana de {br_int(center)} views em {n} vídeos do mesmo "
            f"canal e formato na mesma idade ({len(measured)} medidos, {len(banded)} por faixa de idade)."
        )

    return OutlierResult(
        "ok", idr=idr, robust_z=z, band=_band(idr, config) if idr is not None else None,
        confidence=confidence, sample_size=n, measured_peers=len(measured), band_peers=len(banded),
        peer_median_views=center, target_views=latest.views, age_hours=age,
        warnings=tuple(sorted(warnings)), explanation=explanation,
    )


def _note_regime(warnings: set[str], first, second, video_format: str) -> None:
    start, end = sorted((first, second))
    if regime_changes_between(start, end, video_format):
        warnings.add("pares_em_regimes_de_contagem_diferentes")
