"""Confere o formato das respostas da Data API, sem confiar que o Google sempre manda tudo.

Os campos obrigatórios abaixo foram conferidos contra o documento público de descoberta do Google
(revisão 20261102). Campos públicos que o canal pode ocultar, como inscritos e curtidas, não são
obrigatórios: viram "indisponível" na tela, nunca zero.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

REQUIRED: dict[str, tuple[str, ...]] = {
    "videos.list": ("id", "snippet.channelId", "snippet.title", "snippet.publishedAt"),
    "channels.list": ("id", "snippet.title"),
    "playlistItems.list": ("contentDetails.videoId",),
    "search.list": ("id",),
}
OPTIONAL_WATCH: dict[str, tuple[str, ...]] = {
    "videos.list": ("contentDetails.duration", "statistics.viewCount", "statistics.likeCount", "statistics.commentCount", "player.embedHeight", "snippet.thumbnails"),
    "channels.list": ("statistics.subscriberCount", "statistics.viewCount", "statistics.videoCount", "contentDetails.relatedPlaylists.uploads", "snippet.country"),
    "search.list": ("snippet.channelId", "snippet.publishedAt"),
    "playlistItems.list": (),
}


def _get(item: Any, path: str) -> Any:
    node = item
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@dataclass
class ShapeReport:
    fatal: str | None = None
    valid_items: list[dict] = field(default_factory=list)
    rejected: int = 0
    problems: list[str] = field(default_factory=list)
    availability: dict[str, int] = field(default_factory=dict)


def check_response(method: str, data: Any) -> ShapeReport:
    """`fatal` significa que a resposta inteira não serve. Item incompleto é só descartado e relatado."""
    report = ShapeReport()
    if not isinstance(data, dict):
        report.fatal = f"{method} devolveu algo que não é um objeto JSON."
        return report
    # A API omite `items` em algumas respostas vazias; lista ausente equivale a nenhum resultado.
    items = data.get("items", [])
    if not isinstance(items, list):
        report.fatal = f"{method} devolveu `items` em formato inesperado."
        return report
    required = REQUIRED.get(method, ())
    watched = OPTIONAL_WATCH.get(method, ())
    report.availability = {path: 0 for path in watched}
    for item in items:
        missing = [path for path in required if _get(item, path) in (None, "")]
        if missing:
            report.rejected += 1
            report.problems.append(f"{method}: item sem {', '.join(missing)}.")
            continue
        report.valid_items.append(item)
        for path in watched:
            if _get(item, path) not in (None, ""):
                report.availability[path] += 1
    return report
