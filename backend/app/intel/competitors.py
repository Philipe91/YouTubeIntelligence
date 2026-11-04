"""Competitor Intelligence: lista própria por canal, com fontes e sem ranking fora do regime aprovado.

A referência vira um ID de canal no banco do estúdio. Título, inscritos e vídeos ficam no banco de pesquisa,
sujeitos à retenção. A política proíbe apresentar comparações como rivalidade ou conflito: o texto na tela
fala em referência editorial.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlparse

from .. import collector, services
from ..config import Settings
from ..db import from_iso, to_iso
from ..metrics.editorial import EditorialVideo, editorial_profile
from ..metrics.text import terms
from ..policy import BLOCK_REASON, ORIGIN_NOTE, policy_state
from ..studio import recommend, store
from ..studio.store import StudioError, new_id
from . import explorer
from .common import ClientFactory, default_client, require_channel, youtube_errors

CHANNEL_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
HANDLE = re.compile(r"^@[0-9A-Za-z._-]{3,30}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
MAX_COLLECT = 50
CALENDAR_DAYS = 90


def parse_reference(text: str) -> str:
    """Aceita ID, @handle ou URL do YouTube. Devolve o ID ou o @handle."""
    value = (text or "").strip()
    if CHANNEL_ID.match(value) or HANDLE.match(value):
        return value
    if value.startswith(("youtube.com/", "www.youtube.com/", "m.youtube.com/")):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise StudioError("invalid_reference", "Use o link do canal no YouTube, o @nome ou o ID que começa com UC.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "channel" and CHANNEL_ID.match(parts[1]):
        return parts[1]
    if parts and HANDLE.match(parts[0]):
        return parts[0]
    raise StudioError("invalid_reference", "Este link não identifica um canal. Abra a página do canal e copie o endereço com @nome ou /channel/UC...")


def _demo_channel(conn: sqlite3.Connection, reference: str) -> str:
    row = conn.execute("SELECT id FROM channels WHERE id = ? OR handle = ?", (reference, reference)).fetchone()
    if row is None:
        raise StudioError("demo_reference", "No modo demonstração, só canais fictícios podem ser associados. Nenhuma busca real é feita.", 409)
    return row["id"]


def _research_id(conn: sqlite3.Connection, settings: Settings, competitor: dict) -> str | None:
    ref = competitor.get("youtube_ref")
    if ref:
        row = conn.execute("SELECT id FROM channels WHERE id = ? OR handle = ?", (ref, ref)).fetchone()
        if row:
            return row["id"]
    if settings.mode == "demo":
        row = conn.execute("SELECT id FROM channels WHERE title = ?", (competitor["name"],)).fetchone()
        return row["id"] if row else None
    return None


def _fetch(conn: sqlite3.Connection, settings: Settings, factory: ClientFactory, reference: str, now: datetime) -> str:
    client = factory(settings, conn)
    try:
        with youtube_errors():
            research_id = collector.add_channel(client, conn, reference, now)
            collector.collect_channel_videos(client, conn, settings, research_id, now, max_videos=MAX_COLLECT)
    finally:
        client.close()
    return research_id


def _find(studio: sqlite3.Connection, channel_id: str, competitor_id: str) -> dict:
    row = studio.execute("SELECT * FROM competitors WHERE id = ? AND channel_id = ?", (competitor_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("not_found", "Concorrente não encontrado neste canal.", 404)
    return dict(row)


def add(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, reference: str, name: str, notes: str, now: datetime,
        factory: ClientFactory = default_client) -> dict:
    require_channel(studio, settings, channel_id)
    parsed = parse_reference(reference)
    research_id = _demo_channel(conn, parsed) if settings.mode == "demo" else _fetch(conn, settings, factory, parsed, now)
    if studio.execute("SELECT 1 FROM competitors WHERE channel_id = ? AND youtube_ref = ?", (channel_id, research_id)).fetchone():
        raise StudioError("duplicate_competitor", "Este canal já está na lista.", 409)
    # O nome é seu, ou a própria referência: título da API não fica no banco do estúdio.
    return store.add_competitor(studio, channel_id, name.strip() or parsed, research_id, notes)


def link(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, competitor_id: str, reference: str, now: datetime,
         factory: ClientFactory = default_client) -> dict:
    require_channel(studio, settings, channel_id)
    _find(studio, channel_id, competitor_id)
    parsed = parse_reference(reference)
    research_id = _demo_channel(conn, parsed) if settings.mode == "demo" else _fetch(conn, settings, factory, parsed, now)
    studio.execute("UPDATE competitors SET youtube_ref = ? WHERE id = ?", (research_id, competitor_id))
    studio.commit()
    return _find(studio, channel_id, competitor_id)


def refresh(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, competitor_id: str, now: datetime,
            factory: ClientFactory = default_client) -> dict:
    competitor = _find(studio, channel_id, competitor_id)
    if settings.mode == "demo":
        raise StudioError("demo_reference", "No modo demonstração não há coleta real para atualizar.", 409)
    research_id = _research_id(conn, settings, competitor) or competitor.get("youtube_ref")
    if not research_id:
        raise StudioError("not_linked", "Vincule este concorrente a um canal do YouTube antes de atualizar.", 409)
    _fetch(conn, settings, factory, research_id, now)
    return {"refreshed": research_id}


def _videos(conn: sqlite3.Connection, research_id: str) -> list[sqlite3.Row]:
    return conn.execute(services.VIDEO_SELECT + " WHERE v.channel_id = ? ORDER BY v.published_at DESC", (research_id,)).fetchall()


def _editorial(conn: sqlite3.Connection, settings: Settings, rows: list[sqlite3.Row]) -> dict:
    analysis = services.analyze(conn, settings)
    videos = [EditorialVideo(r["id"], r["title"], r["format"], from_iso(r["published_at"]), r["duration_seconds"], analysis.outliers[r["id"]].idr) for r in rows]
    return {fmt: editorial_profile(videos, fmt).to_dict() for fmt in ("short", "long")}


def _title_patterns(rows: list[sqlite3.Row]) -> list[dict]:
    counts = Counter(explorer.title_features(r["title"])["approach_label"] for r in rows)
    return [{"pattern": label, "videos": count} for label, count in counts.most_common()]


def _recurring_subjects(rows: list[sqlite3.Row]) -> list[dict]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(terms(row["title"]))
    return [{"term": term, "videos": count} for term, count in counts.most_common(12) if count >= 2]


def _summary(conn: sqlite3.Connection, settings: Settings, competitor: dict, subscribers: dict, now: datetime) -> dict:
    research_id = _research_id(conn, settings, competitor)
    base = {"id": competitor["id"], "name": competitor["name"], "notes": competitor["notes"], "youtube_ref": competitor["youtube_ref"], "research_id": research_id, "linked": bool(research_id)}
    if not research_id:
        return {**base, "channel": None, "videos_collected": 0, "last_published_at": None, "recent_days_uploads": []}
    channel = conn.execute("SELECT * FROM channels WHERE id = ?", (research_id,)).fetchone()
    rows = _videos(conn, research_id)
    count = subscribers.get(research_id)
    return {
        **base,
        "channel": {
            "title": channel["title"], "handle": channel["handle"], "country": channel["country"], "source_url": services.channel_url(research_id),
            "subscribers": (services.metric(count, "measured", "channels.list") if count is not None
                            else services.metric(None, "unavailable", "channels.list", "O canal oculta os inscritos ou ainda não foi medido.")),
            "text_refreshed_at": channel["text_refreshed_at"],
        },
        "videos_collected": len(rows), "last_published_at": rows[0]["published_at"] if rows else None,
        "recent_days_uploads": [r["published_at"][:10] for r in rows if now - from_iso(r["published_at"]) <= timedelta(days=CALENDAR_DAYS)],
    }


def overview(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, now: datetime) -> dict:
    channel = store.get_channel(studio, channel_id)
    usable = channel["is_demo"] == (settings.mode == "demo")
    state = policy_state(settings)
    subscribers = services._latest_subscribers(conn)
    items = [_summary(conn, settings, c, subscribers, now) if usable else {"id": c["id"], "name": c["name"], "notes": c["notes"], "youtube_ref": c["youtube_ref"], "research_id": None, "linked": False, "channel": None, "videos_collected": 0, "last_published_at": None, "recent_days_uploads": []}
             for c in store.list_competitors(studio, channel_id)]
    comparison = None
    if usable and state.derived_allowed:
        comparison = []
        for item in items:
            if item["linked"]:
                profile = _editorial(conn, settings, _videos(conn, item["research_id"]))
                comparison.append({"name": item["channel"]["title"], "research_id": item["research_id"], "formats": {
                    fmt: {key: profile[fmt][key] for key in ("sample_size", "uploads_per_week", "median_duration_seconds", "question_title_share", "top_weekday")} for fmt in profile
                }})
    return {
        "channel": {"id": channel["id"], "name": channel["name"], "is_demo": channel["is_demo"]}, "usable": usable, "items": items, "comparison": comparison,
        "comparison_blocked": not state.derived_allowed, "reason": None if state.derived_allowed else BLOCK_REASON, "origin_note": ORIGIN_NOTE if state.derived_allowed else None,
        "fictional": settings.mode == "demo" and usable, "has_api_key": bool(settings.youtube_api_key), "mode": settings.mode,
        "demo_options": _demo_options(conn, items) if settings.mode == "demo" and usable else [],
    }


def _demo_options(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    used = {item["research_id"] for item in items}
    return [{"id": r["id"], "title": r["title"]} for r in conn.execute("SELECT id, title FROM channels WHERE is_own = 0 ORDER BY title") if r["id"] not in used]


def detail(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, competitor_id: str, now: datetime, limit: int = 20, offset: int = 0) -> dict:
    channel = store.get_channel(studio, channel_id)
    usable = channel["is_demo"] == (settings.mode == "demo")
    competitor = _find(studio, channel_id, competitor_id)
    summary = _summary(conn, settings, competitor, services._latest_subscribers(conn), now) if usable else None
    if not summary or not summary["linked"]:
        return {"competitor": competitor, "linked": False, "summary": summary, "usable": usable}
    rows = _videos(conn, summary["research_id"])
    analysis = services.analyze(conn, settings)
    allowed = policy_state(settings).derived_allowed
    calendar: dict[str, list[dict]] = {}
    for row in rows:
        if now - from_iso(row["published_at"]) <= timedelta(days=CALENDAR_DAYS):
            calendar.setdefault(row["published_at"][:10], []).append({"id": row["id"], "title": row["title"], "format": row["format"]})
    return {
        "competitor": competitor, "linked": True, "usable": True, "summary": summary, "fictional": settings.mode == "demo",
        "videos": {"total": len(rows), "limit": limit, "offset": offset, "items": [services._video_row(r, analysis, settings) for r in rows[offset:offset + limit]]},
        "calendar": [{"day": day, "videos": calendar[day]} for day in sorted(calendar, reverse=True)], "calendar_days": CALENDAR_DAYS,
        "editorial": _editorial(conn, settings, rows) if allowed else None, "title_patterns": _title_patterns(rows) if allowed else [],
        "recurring_subjects": _recurring_subjects(rows) if allowed else [], "patterns_blocked": not allowed, "reason": None if allowed else BLOCK_REASON,
        "origin_note": ORIGIN_NOTE if allowed else None, "study_ids": explorer.study_ids(conn, channel_id),
    }


def report(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, now: datetime) -> tuple[str, str]:
    """Relatório em Markdown, com links das fontes. Sem aprovação, traz só dados crus."""
    data = overview(conn, studio, settings, channel_id, now)
    lines = [f"# Referências editoriais: {data['channel']['name']}", "", f"Gerado em {to_iso(now)}."]
    if data["fictional"]:
        lines += ["", "**Dados fictícios de demonstração. Nenhum canal aqui existe.**"]
    if not data["comparison_blocked"]:
        lines += ["", f"Métricas calculadas por este aplicativo. {ORIGIN_NOTE}"]
    else:
        lines += ["", "Só dados crus: comparações e padrões dependem de aprovação do Google."]
    for item in data["items"]:
        lines += ["", f"## {_md(item['channel']['title'] if item['channel'] else item['name'])}"]
        if item["notes"]:
            lines.append(f"Sua nota: {_md(item['notes'])}")
        if not item["linked"]:
            lines.append("Sem vínculo com um canal do YouTube.")
            continue
        source = item["channel"]["source_url"]
        lines.append(f"Fonte: {source}" if source else "Fonte: canal fictício, sem página no YouTube.")
        subs = item["channel"]["subscribers"]["value"]
        lines.append(f"Inscritos: {subs if subs is not None else 'indisponível'}. Vídeos coletados: {item['videos_collected']}.")
        lines += ["", "Vídeos recentes:"]
        for row in _videos(conn, item["research_id"])[:5]:
            url = services.video_url(row["id"])
            lines.append(f"- {row['published_at'][:10]}: {_md(row['title'])}" + (f" ({url})" if url else ""))
    opportunities = list_opportunities(conn, channel_id)
    if opportunities:
        lines += ["", "## Oportunidades registradas"]
        lines += [f"- {_md(o['title'])}: {_md(o['note'])}" if o["note"] else f"- {_md(o['title'])}" for o in opportunities if o["status"] == "aberta"]
    return "\n".join(lines) + "\n", f"referencias_{channel_id}.md"


def _md(text: str) -> str:
    """Texto externo não vira link nem marcação no relatório."""
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", " ".join(str(text).split()))


# --- Oportunidades editoriais ---------------------------------------------------------------------

def list_opportunities(conn: sqlite3.Connection, channel_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT o.*, v.title AS video_title FROM editorial_opportunities o LEFT JOIN videos v ON v.id = o.video_id
           WHERE o.managed_channel_id = ? ORDER BY CASE o.status WHEN 'aberta' THEN 0 ELSE 1 END, o.created_at DESC""", (channel_id,)
    ).fetchall()
    return [{**dict(r), "source_url": services.video_url(r["video_id"]) if r["video_id"] else None} for r in rows]


def add_opportunity(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, title: str, note: str, video_id: str | None, now: datetime) -> dict:
    require_channel(studio, settings, channel_id)
    text = " ".join(title.split())
    if not 3 <= len(text) <= 200:
        raise StudioError("invalid_field", "Descreva a oportunidade em 3 a 200 caracteres.")
    if video_id and conn.execute("SELECT 1 FROM videos WHERE id = ?", (video_id,)).fetchone() is None:
        raise StudioError("video_not_found", "Vídeo não encontrado na base.", 404)
    identifier = new_id("opp")
    conn.execute("INSERT INTO editorial_opportunities (id, managed_channel_id, title, note, video_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (identifier, channel_id, text, note.strip()[:1000], video_id or None, to_iso(now), to_iso(now)))
    conn.commit()
    return {"id": identifier}


def _opportunity(conn: sqlite3.Connection, channel_id: str, opportunity_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM editorial_opportunities WHERE id = ? AND managed_channel_id = ?", (opportunity_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("not_found", "Oportunidade não encontrada neste canal.", 404)
    return row


def discard_opportunity(conn: sqlite3.Connection, channel_id: str, opportunity_id: str, now: datetime) -> None:
    _opportunity(conn, channel_id, opportunity_id)
    conn.execute("UPDATE editorial_opportunities SET status = 'descartada', updated_at = ? WHERE id = ?", (to_iso(now), opportunity_id))
    conn.commit()


def opportunity_to_idea(conn: sqlite3.Connection, studio: sqlite3.Connection, channel_id: str, opportunity_id: str, video_format: str, now: datetime) -> dict:
    row = _opportunity(conn, channel_id, opportunity_id)
    if row["status"] != "aberta":
        raise StudioError("opportunity_closed", "Esta oportunidade já foi tratada.", 409)
    idea = recommend.create_owner_recommendation(studio, channel_id, subject=row["title"], justification=row["note"] or "Oportunidade registrada por você ao estudar referências.", video_format=video_format)
    # Toda ideia nasce com as três opções de título.
    idea = recommend.generate_titles(studio, channel_id, idea["id"])
    conn.execute("UPDATE editorial_opportunities SET status = 'virou_ideia', recommendation_id = ?, updated_at = ? WHERE id = ?", (idea["id"], to_iso(now), opportunity_id))
    conn.commit()
    return idea

