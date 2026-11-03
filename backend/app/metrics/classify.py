"""Classificação de formato e leitura de duração ISO 8601."""
from __future__ import annotations

import re

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: str | None) -> int | None:
    """Converte PT1H2M3S em segundos. Retorna None se ausente ou inválida."""
    if not value:
        return None
    match = _DURATION.match(value)
    if not match or value in {"P", "PT"}:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def classify_format(
    duration_seconds: int | None,
    short_max_seconds: int,
    analytics_content_type: str | None = None,
    live_broadcast_content: str | None = None,
    has_live_details: bool = False,
    published_at: str | None = None,
    short_cutoff: str | None = None,
    legacy_short_max_seconds: int = 60,
) -> tuple[str, str]:
    """Retorna (formato, origem). A origem indica se a informação é confirmada ou estimada.

    Regra do YouTube (support.google.com/youtube/answer/15424877): vídeos quadrados ou verticais de
    até 3 min são Shorts se enviados desde 15/10/2024; envios anteriores acima de 1 min seguem longos.
    A Data API não informa a proporção, então um vídeo 16:9 curto ainda pode ser contado como Short.
    """
    if analytics_content_type == "SHORTS":
        return "short", "analytics"
    if analytics_content_type == "VIDEO_ON_DEMAND":
        return "long", "analytics"
    if analytics_content_type == "LIVE_STREAM":
        return "live", "analytics"
    if has_live_details or live_broadcast_content in {"live", "upcoming"}:
        return "live", "broadcast"
    if duration_seconds is None or duration_seconds == 0:
        return "unknown", "missing"
    # A Data API não informa se é Short: isto é uma estimativa por duração e data de envio.
    limit = short_max_seconds
    if published_at and short_cutoff and published_at[:10] < short_cutoff:
        limit = legacy_short_max_seconds
    return ("short" if duration_seconds <= limit else "long"), "duration"
