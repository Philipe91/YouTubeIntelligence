"""Outlier Explorer: procura vídeos fora da curva e guarda os que merecem estudo.

Valores crus aparecem sempre. O IDR e a leitura de títulos só existem com a política liberada: sem ela,
a lista segue útil, ordenada por valores públicos, e nenhum score é calculado para a tela.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from .. import services
from ..config import Settings
from ..db import to_iso
from ..metrics.text import tokens
from ..policy import BLOCK_REASON, ORIGIN_NOTE, policy_state
from ..studio.store import StudioError
from .common import require_channel

MAX_COMPARE = 6
SORTS_RAW = {"views", "recent"}
SORTS_DERIVED = {"idr", "vph"}
ORIGINS = {"explorer", "competidor", "pesquisa"}
OPENERS = {
    "lista": re.compile(r"^\d+\s"),
    "revelacao": re.compile(r"^(a verdade|o que ninguém|o que ninguem|the truth|la verdad|what nobody)", re.I),
    "explicacao": re.compile(r"(explicad|explained|em \d+ minutos|in \d+ minutes|en \d+ minutos)", re.I),
    "como_era": re.compile(r"^(como era|what was|how was|cómo era|como foi)", re.I),
    "causa": re.compile(r"^(por que|por quê|why|por qué|porque)", re.I),
}
APPROACH_LABEL = {
    "lista": "Lista numerada", "revelacao": "Promete revelar algo", "explicacao": "Explicação direta",
    "como_era": "Reconstrói uma época", "causa": "Parte de uma causa", "pergunta": "Abre com pergunta", "narrativa": "Afirmação ou narrativa",
}


def search(conn: sqlite3.Connection, settings: Settings, *, q: str | None = None, days: int | None = None, video_format: str = "long",
           sort: str = "views", only_above: bool = False, min_views: int | None = None, limit: int = 25, offset: int = 0) -> dict:
    allowed = policy_state(settings).derived_allowed
    notes: list[str] = []
    if sort not in SORTS_RAW | SORTS_DERIVED:
        raise StudioError("invalid_field", "Ordenação inválida.")
    if video_format not in {"short", "long", "indeterminate"}:
        raise StudioError("invalid_field", "Formato inválido.")
    if not allowed and sort in SORTS_DERIVED:
        sort = "views"
        notes.append("A ordenação por IDR e VPH está bloqueada: a lista usa as views públicas.")
    if not allowed and only_above:
        only_above = False
        notes.append("O filtro por vídeos acima do típico está bloqueado: a lista mostra todos.")
    data = services.list_videos(conn, settings, video_format=video_format, q=q or None, days=days, sort=sort, limit=5000, outliers_only=only_above)
    items = data["items"]
    if min_views is not None:
        items = [item for item in items if (item["views"]["value"] or 0) >= min_views]
    return {
        "total": len(items), "limit": limit, "offset": offset, "items": items[offset:offset + limit], "sort": sort, "notes": notes,
        "derived_allowed": allowed, "blocked_reason": None if allowed else BLOCK_REASON, "origin_note": ORIGIN_NOTE if allowed else None,
        "fictional": settings.mode == "demo",
    }


def _require_video(conn: sqlite3.Connection, video_id: str) -> None:
    if conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone() is None:
        raise StudioError("video_not_found", "Vídeo não encontrado na base.", 404)


def add_study(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, video_id: str, now: datetime,
              origin: str = "explorer", note: str = "") -> dict:
    require_channel(studio, settings, channel_id)
    if origin not in ORIGINS:
        raise StudioError("invalid_field", "Origem inválida.")
    _require_video(conn, video_id)
    conn.execute(
        "INSERT INTO study_videos (managed_channel_id, video_id, origin, note, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(managed_channel_id, video_id) DO UPDATE SET note = CASE WHEN excluded.note = '' THEN study_videos.note ELSE excluded.note END",
        (channel_id, video_id, origin, note.strip()[:1000], to_iso(now)),
    )
    conn.commit()
    return {"channel_id": channel_id, "video_id": video_id}


def update_study_note(conn: sqlite3.Connection, channel_id: str, video_id: str, note: str) -> None:
    cursor = conn.execute("UPDATE study_videos SET note = ? WHERE managed_channel_id = ? AND video_id = ?", (note.strip()[:1000], channel_id, video_id))
    conn.commit()
    if cursor.rowcount == 0:
        raise StudioError("not_found", "Vídeo não está na lista de estudo deste canal.", 404)


def remove_study(conn: sqlite3.Connection, channel_id: str, video_id: str) -> None:
    cursor = conn.execute("DELETE FROM study_videos WHERE managed_channel_id = ? AND video_id = ?", (channel_id, video_id))
    conn.commit()
    if cursor.rowcount == 0:
        raise StudioError("not_found", "Vídeo não está na lista de estudo deste canal.", 404)


def study_ids(conn: sqlite3.Connection, channel_id: str | None) -> list[str]:
    if not channel_id:
        return []
    return [r["video_id"] for r in conn.execute("SELECT video_id FROM study_videos WHERE managed_channel_id = ?", (channel_id,))]


def _snapshot_edges(conn: sqlite3.Connection, video_id: str) -> dict:
    rows = conn.execute("SELECT captured_at, view_count FROM snapshots WHERE video_id = ? AND view_count IS NOT NULL ORDER BY captured_at", (video_id,)).fetchall()
    if not rows:
        return {"count": 0, "first_at": None, "first_views": None, "last_at": None, "last_views": None}
    return {"count": len(rows), "first_at": rows[0]["captured_at"], "first_views": rows[0]["view_count"], "last_at": rows[-1]["captured_at"], "last_views": rows[-1]["view_count"]}


def list_study(conn: sqlite3.Connection, settings: Settings, channel_id: str, *, origin: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    """Histórico dos vídeos monitorados para o canal. Mostra a primeira e a última medição, sem calcular nada."""
    where, params = "managed_channel_id = ?", [channel_id]
    if origin:
        where += " AND origin = ?"
        params.append(origin)
    total = conn.execute(f"SELECT COUNT(*) AS n FROM study_videos WHERE {where}", params).fetchone()["n"]
    rows = conn.execute(f"SELECT * FROM study_videos WHERE {where} ORDER BY created_at DESC, video_id LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    analysis = services.analyze(conn, settings)
    items = []
    for row in rows:
        video = conn.execute(services.VIDEO_SELECT + " WHERE v.id = ?", (row["video_id"],)).fetchone()
        if video:
            items.append({"video": services._video_row(video, analysis, settings), "note": row["note"], "origin": row["origin"], "added_at": row["created_at"],
                          "snapshots": _snapshot_edges(conn, row["video_id"])})
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def title_features(title: str) -> dict:
    """Leitura simples do título, por regras. É uma classificação deste aplicativo, não do YouTube."""
    words = title.split()
    approach = "pergunta" if title.rstrip().endswith("?") else next((name for name, pattern in OPENERS.items() if pattern.search(title)), "narrativa")
    return {"characters": len(title), "words": len(words), "has_number": any(ch.isdigit() for ch in title), "is_question": "?" in title,
            "approach": approach, "approach_label": APPROACH_LABEL[approach], "caps_words": sum(1 for w in words if len(w) > 2 and w.isupper())}


def compare_videos(conn: sqlite3.Connection, settings: Settings, channel_id: str, ids: list[str]) -> dict:
    """Comparação editorial de títulos. Sem ranking e sem declarar vencedor."""
    unique = list(dict.fromkeys(ids))
    if not 2 <= len(unique) <= MAX_COMPARE:
        raise StudioError("invalid_field", f"Escolha de 2 a {MAX_COMPARE} vídeos.")
    allowed_ids = set(study_ids(conn, channel_id))
    if set(unique) - allowed_ids:
        raise StudioError("not_in_study", "Só dá para comparar vídeos da lista de estudo deste canal.", 404)
    allowed = policy_state(settings).derived_allowed
    analysis = services.analyze(conn, settings)
    columns = []
    for video_id in unique:
        row = conn.execute(services.VIDEO_SELECT + " WHERE v.id = ?", (video_id,)).fetchone()
        note = conn.execute("SELECT note FROM study_videos WHERE managed_channel_id = ? AND video_id = ?", (channel_id, video_id)).fetchone()
        if row:
            columns.append({"video": services._video_row(row, analysis, settings), "note": note["note"] if note else "",
                            "features": title_features(row["title"]) if allowed else None})
    shared: list[str] = []
    if allowed and len(columns) >= 2:
        common = set(tokens(columns[0]["video"]["title"]))
        for column in columns[1:]:
            common &= set(tokens(column["video"]["title"]))
        shared = sorted(common)
    return {"columns": columns, "features_blocked": not allowed, "reason": None if allowed else BLOCK_REASON, "shared_words": shared,
            "note": "Compare a abordagem e escreva suas notas. A leitura por regras não indica qual título é melhor."}
