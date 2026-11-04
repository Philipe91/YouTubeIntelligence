"""Classificação de formato e leitura de duração ISO 8601."""
from __future__ import annotations

import re

_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_UNKNOWN_RATIO = 4 / 3


def parse_duration(value: str | None) -> int | None:
    """Converte PT1H2M3S em segundos. Retorna None se ausente ou inválida."""
    if not value:
        return None
    match = _DURATION.match(value)
    if not match or value in {"P", "PT"}:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _positive(value: object) -> int | None:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def classify_format(
    duration_seconds: int | None,
    short_max_seconds: int,
    analytics_content_type: str | None = None,
    live_broadcast_content: str | None = None,
    has_live_details: bool = False,
    published_at: str | None = None,
    short_cutoff: str | None = None,
    legacy_short_max_seconds: int = 60,
    embed_width: object = None,
    embed_height: object = None,
) -> tuple[str, str]:
    """Retorna (formato, origem). Sem dados que confirmem, o formato é "indeterminate".

    Regra do YouTube (support.google.com/youtube/answer/15424877): vídeos quadrados ou verticais de
    até 3 min são Shorts se enviados desde 15/10/2024; envios anteriores acima de 1 min seguem longos.

    A Data API não informa a proporção do vídeo. O sinal disponível é o tamanho do player embutido,
    e a documentação avisa que ele cai em 4:3 quando a proporção é desconhecida: 4:3 não confirma nada.
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

    limit = short_max_seconds
    if published_at and short_cutoff and published_at[:10] < short_cutoff:
        limit = legacy_short_max_seconds
    if duration_seconds > limit:
        return "long", "duration"

    width, height = _positive(embed_width), _positive(embed_height)
    if width is None or height is None:
        return "indeterminate", "duration"
    ratio = width / height
    if ratio <= 1:
        return "short", "aspect_ratio"
    if abs(ratio - _UNKNOWN_RATIO) < 0.02:
        return "indeterminate", "duration"
    return "long", "aspect_ratio"
