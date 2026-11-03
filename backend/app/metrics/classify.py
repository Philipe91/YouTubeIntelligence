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
) -> tuple[str, str]:
    """Retorna (formato, origem). A origem indica se a informação é confirmada ou estimada."""
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
    # A Data API não informa se é Short: isto é uma estimativa por duração.
    return ("short" if duration_seconds <= short_max_seconds else "long"), "duration"
