"""Research Center: pesquisa, histórico, salvos, comparação e exportação.

Modo demo: busca só nos dados fictícios, sem rede.
Modo real: usa a API oficial, com cota e cache. A pesquisa guarda IDs: o texto continua em
`videos` e `channels`, sujeito à retenção de 30 dias. Quem sai da base aparece como removido.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta

from .. import collector, services
from ..config import Settings
from ..db import to_iso
from ..metrics.text import tokens
from ..policy import policy_state
from ..studio.store import StudioError, new_id
from .common import ClientFactory, data_origin, default_client, loads, require_channel, to_csv, youtube_errors

KINDS = {
    "videos": "Vídeos por tema",
    "channels": "Canais por nicho",
    "recent": "Vídeos recentes",
    "emerging": "Canais pequenos em atividade",
}
ORDERS = {"relevance", "date", "viewCount"}
FORMATS = {"short", "long", "indeterminate"}
COUNTRY = re.compile(r"^[A-Z]{2}$")
LANGUAGE = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")
RECENT_DEFAULT_DAYS = 7
EMERGING_WINDOW_DAYS = 30
EMERGING_MAX_SUBSCRIBERS = 100_000
MAX_RESULTS = 50
FILTER_NOTES = {
    "language": "No YouTube, o idioma só orienta a relevância: resultados em outro idioma podem aparecer.",
    "country": "No YouTube, o país orienta a região da busca. Não garante que o canal seja de lá.",
    "format": "A API não tem filtro de Shorts. O formato é aplicado depois, sobre os vídeos devolvidos: a lista pode vir menor.",
}
FORMAT_ONLY_INDETERMINATE = "Vídeos curtos sem proporção conhecida ficam fora dos filtros de Short e de longo. Escolha o formato Indeterminado para vê-los."


def _clean_query(query: str) -> str:
    text = " ".join((query or "").split())
    if not 2 <= len(text) <= 120:
        raise StudioError("invalid_field", "A pesquisa precisa ter de 2 a 120 caracteres.")
    if not tokens(text):
        raise StudioError("invalid_field", "Use ao menos uma palavra com significado na pesquisa.")
    return text


def _filters(kind: str, language: str | None, country: str | None, days: int | None, video_format: str | None, order: str,
             max_subscribers: int | None) -> dict:
    if kind not in KINDS:
        raise StudioError("invalid_field", "Tipo de pesquisa desconhecido.")
    if order not in ORDERS:
        raise StudioError("invalid_field", "Ordenação inválida.")
    if video_format and video_format not in FORMATS:
        raise StudioError("invalid_field", "Formato inválido.")
    if days is not None and not 1 <= days <= 3650:
        raise StudioError("invalid_field", "Período inválido.")
    if kind == "recent":
        days = days or RECENT_DEFAULT_DAYS
    if kind == "emerging":
        days = days or EMERGING_WINDOW_DAYS
    language = (language or "").strip().lower() or None
    country = (country or "").strip().upper() or None
    if language and not LANGUAGE.match(language):
        raise StudioError("invalid_field", "Idioma inválido. Use um código como pt, en ou es.")
    if country and not COUNTRY.match(country):
        raise StudioError("invalid_field", "País inválido. Use a sigla de duas letras, como BR.")
    if max_subscribers is not None and max_subscribers < 1:
        raise StudioError("invalid_field", "O máximo de inscritos precisa ser positivo.")
    return {"language": language, "country": country, "days": days,
            "format": video_format or None, "order": "date" if kind == "recent" else order,
            "max_subscribers": (max_subscribers or EMERGING_MAX_SUBSCRIBERS) if kind == "emerging" else None}


def _matches(title: str, wanted: set[str], loose: bool = False) -> bool:
    """A descoberta em modo demo é solta: os termos de nicho são longos, e os vídeos fictícios, poucos."""
    return bool(wanted & set(tokens(title))) if loose else wanted <= set(tokens(title))


def _latest_views(analysis, video_id: str) -> int:
    valid = analysis.series[video_id].valid_snapshots()
    return valid[-1].views if valid else -1


def _local_videos(conn: sqlite3.Connection, settings: Settings, query: str, filters: dict, now: datetime) -> list[str]:
    wanted = set(tokens(query))
    clauses, params = [], []
    if filters["language"]:
        clauses.append("v.language = ?")
        params.append(filters["language"])
    if filters["country"]:
        clauses.append("COALESCE(v.country, c.country) = ?")
        params.append(filters["country"])
    if filters["format"]:
        clauses.append("v.format = ?")
        params.append(filters["format"])
    if filters["days"]:
        clauses.append("v.published_at >= ?")
        params.append(to_iso(now - timedelta(days=filters["days"])))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [r for r in conn.execute(services.VIDEO_SELECT + where, params) if _matches(r["title"], wanted, bool(filters.get("discovery")))]
    if filters["order"] == "viewCount":
        analysis = services.analyze(conn, settings)
        rows.sort(key=lambda r: _latest_views(analysis, r["id"]), reverse=True)
    else:
        rows.sort(key=lambda r: r["published_at"], reverse=True)
    return [r["id"] for r in rows[:MAX_RESULTS]]


def _subscribers(conn: sqlite3.Connection) -> dict[str, int | None]:
    return services._latest_subscribers(conn)


def _emerging_from(conn: sqlite3.Connection, video_ids: list[str], limit: int, sort_by_size: bool) -> list[str]:
    """Filtra pelo número público de inscritos, sem criar nota. Sem aprovação, mantém a ordem da busca: ordenar seria um ranking."""
    subscribers = _subscribers(conn)
    channel_ids: list[str] = []
    for video_id in video_ids:
        row = conn.execute("SELECT channel_id FROM videos WHERE id = ?", (video_id,)).fetchone()
        if row and row["channel_id"] not in channel_ids:
            channel_ids.append(row["channel_id"])
    known = [c for c in channel_ids if subscribers.get(c) is not None and subscribers[c] <= limit]
    if sort_by_size:
        known.sort(key=lambda c: subscribers[c])
    return known


def _local_channels(conn: sqlite3.Connection, query: str, filters: dict) -> list[str]:
    wanted = set(tokens(query))
    found: list[str] = []
    for row in conn.execute(
        """SELECT c.id, c.title, c.description, c.country, c.default_language, n.name AS niche FROM channels c
           LEFT JOIN niches n ON n.id = c.niche_id ORDER BY c.title"""
    ):
        if filters["language"] and row["default_language"] != filters["language"]:
            continue
        if filters["country"] and row["country"] != filters["country"]:
            continue
        own_text = f"{row['title']} {row['description'] or ''} {row['niche'] or ''}"
        titles = conn.execute("SELECT title FROM videos WHERE channel_id = ?", (row["id"],)).fetchall()
        loose = bool(filters.get("discovery"))
        if _matches(own_text, wanted, loose) or any(_matches(t["title"], wanted, loose) for t in titles):
            found.append(row["id"])
    return found[:MAX_RESULTS]


def _published_after(filters: dict, now: datetime) -> str | None:
    """Arredondado para o dia. Com a hora exata, cada clique seria um pedido novo e o cache nunca valeria."""
    if not filters["days"]:
        return None
    return to_iso((now - timedelta(days=filters["days"])).replace(hour=0, minute=0, second=0, microsecond=0))


def _search_language(language: str | None) -> str | None:
    """`relevanceLanguage` espera o código de duas letras: pt-br vira pt."""
    return language.split("-")[0] if language else None


def _live_videos(conn, settings, client, query: str, filters: dict, now: datetime) -> tuple[list[str], int | None]:
    with youtube_errors():
        result = collector.search_niche(client, conn, settings, query, now, language=_search_language(filters["language"]), country=filters["country"],
                                        published_after=_published_after(filters, now), order=filters["order"])
    rows = conn.execute(
        "SELECT v.id, v.format FROM search_results r JOIN videos v ON v.id = r.video_id WHERE r.search_id = ? ORDER BY r.rank",
        (result["search_id"],),
    ).fetchall()
    ids = [r["id"] for r in rows if not filters["format"] or r["format"] == filters["format"]]
    return ids, result["total_results_approx"]


def _live_channels(conn, client, query: str, filters: dict, now: datetime) -> tuple[list[str], int | None]:
    with youtube_errors():
        page = client.search_channels(query, _search_language(filters["language"]), filters["country"])
        ids = [item["id"]["channelId"] for item in page.get("items", []) if item.get("id", {}).get("channelId")]
        ids = list(dict.fromkeys(ids))
        found: list[str] = []
        if ids:
            for item in client.channels(ids=ids[:50]).get("items", []):
                collector.upsert_channel(conn, item, client.last_fetched_at or now)
                found.append(item["id"])
        conn.commit()
    # A ordem da API é a da relevância: preserva e ignora IDs que não voltaram.
    return [i for i in ids if i in found], page.get("pageInfo", {}).get("totalResults")


def _live_emerging(conn, settings, client, text: str, filters: dict, now: datetime) -> tuple[list[str], int | None]:
    # O filtro de formato não se aplica ao canal: a busca traz vídeos de qualquer formato.
    video_ids, total = _live_videos(conn, settings, client, text, {**filters, "format": None}, now)
    channels = [row["channel_id"] for row in conn.execute(
        f"SELECT DISTINCT channel_id FROM videos WHERE id IN ({', '.join('?' for _ in video_ids)})", video_ids)] if video_ids else []
    with youtube_errors():
        collector.refresh_channel_stats(client, conn, channels, now)
    return _emerging_from(conn, video_ids, filters["max_subscribers"], policy_state(settings).derived_allowed), total


def run_search(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, *, kind: str, query: str,
               channel_id: str | None, now: datetime, language: str | None = None, country: str | None = None, days: int | None = None,
               video_format: str | None = None, order: str = "relevance", max_subscribers: int | None = None,
               factory: ClientFactory = default_client, tags: dict | None = None, schedule_id: str | None = None) -> dict:
    require_channel(studio, settings, channel_id)
    text = _clean_query(query)
    filters = _filters(kind, language, country, days, video_format, order, max_subscribers)
    if tags:
        filters.update(tags)
    total: int | None = None
    if settings.mode == "demo":
        provenance: dict = {"source": "dados_ficticios", "api_calls": 0, "cache_hits": 0, "methods": [], "oldest_data_at": None, "newest_data_at": None, "warnings": []}
        if kind in {"videos", "recent"}:
            ids, item_type = _local_videos(conn, settings, text, filters, now), "video"
        elif kind == "channels":
            ids, item_type = _local_channels(conn, text, filters), "channel"
        else:
            ids, item_type = _emerging_from(conn, _local_videos(conn, settings, text, filters, now), filters["max_subscribers"], True), "channel"
    else:
        client = factory(settings, conn)
        try:
            if kind in {"videos", "recent"}:
                (ids, total), item_type = _live_videos(conn, settings, client, text, filters, now), "video"
            elif kind == "channels":
                (ids, total), item_type = _live_channels(conn, client, text, filters, now), "channel"
            else:
                (ids, total), item_type = _live_emerging(conn, settings, client, text, filters, now), "channel"
            provenance = client.provenance()
        finally:
            client.close()

    run_id = new_id("run")
    conn.execute(
        "INSERT INTO research_runs (id, managed_channel_id, kind, query, filters_json, data_origin, total_results_approx, result_count, executed_at, provenance_json, schedule_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, channel_id, kind, text, json.dumps(filters, ensure_ascii=False), data_origin(settings), total, len(ids), to_iso(now), json.dumps(provenance, ensure_ascii=False), schedule_id),
    )
    conn.executemany("INSERT INTO research_items (run_id, item_type, item_id, rank) VALUES (?, ?, ?, ?)",
                     [(run_id, item_type, item, rank + 1) for rank, item in enumerate(ids)])
    conn.commit()
    return get_run(conn, run_id)


def _run_view(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["filters"] = loads(data.pop("filters_json"), {})
    data["provenance"] = loads(data.pop("provenance_json", None), {})
    data["simulated"] = data["provenance"].get("source") == "api_simulada_teste"
    data["kind_label"] = KINDS[data["kind"]]
    data["fictional"] = data["data_origin"] == "demo"
    return data


def _load_run(conn: sqlite3.Connection, run_id: str, channel_id: str | None = None) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM research_runs WHERE id = ?", (run_id,)).fetchone()
    # Com canal informado, pesquisa de outro canal é tratada como inexistente.
    if row is None or (channel_id and row["managed_channel_id"] != channel_id):
        raise StudioError("run_not_found", "Pesquisa não encontrada.", 404)
    return row


def get_run(conn: sqlite3.Connection, run_id: str, channel_id: str | None = None) -> dict:
    return _run_view(_load_run(conn, run_id, channel_id))


def list_runs(conn: sqlite3.Connection, *, channel_id: str | None = None, saved: bool | None = None, limit: int = 30, offset: int = 0) -> dict:
    clauses, params = [], []
    if channel_id:
        clauses.append("managed_channel_id = ?")
        params.append(channel_id)
    if saved is True:
        clauses.append("saved_name IS NOT NULL")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    total = conn.execute(f"SELECT COUNT(*) AS n FROM research_runs{where}", params).fetchone()["n"]
    rows = conn.execute(f"SELECT * FROM research_runs{where} ORDER BY executed_at DESC, id DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [_run_view(r) for r in rows]}


def _channel_row(conn: sqlite3.Connection, settings: Settings, row: sqlite3.Row, subscribers: dict[str, int | None]) -> dict:
    count = subscribers.get(row["id"])
    last = conn.execute("SELECT MAX(published_at) AS last, COUNT(*) AS n FROM videos WHERE channel_id = ?", (row["id"],)).fetchone()
    return {
        "id": row["id"], "title": row["title"], "handle": row["handle"], "country": row["country"], "language": row["default_language"],
        "thumbnail_url": row["thumbnail_url"], "source_url": services.channel_url(row["id"]), "is_own": bool(row["is_own"]),
        "monitored": bool(row["monitored"]),
        "subscribers": (services.metric(count, "measured", "channels.list") if count is not None
                        else services.metric(None, "unavailable", "channels.list", "O canal oculta os inscritos ou ainda não foi medido.")),
        "videos_collected": last["n"], "last_published_at": last["last"], "text_refreshed_at": row["text_refreshed_at"],
    }


def run_items(conn: sqlite3.Connection, settings: Settings, run_id: str, *, channel_id: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    run = get_run(conn, run_id, channel_id)
    all_items = conn.execute("SELECT item_type, item_id FROM research_items WHERE run_id = ? ORDER BY rank", (run_id,)).fetchall()
    page = all_items[offset:offset + limit]
    videos, channels, removed = [], [], 0
    analysis = services.analyze(conn, settings) if any(i["item_type"] == "video" for i in page) else None
    subscribers = _subscribers(conn)
    for item in page:
        if item["item_type"] == "video":
            row = conn.execute(services.VIDEO_SELECT + " WHERE v.id = ?", (item["item_id"],)).fetchone()
            if row:
                videos.append(services._video_row(row, analysis, settings))
            else:
                removed += 1
        else:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (item["item_id"],)).fetchone()
            if row:
                channels.append(_channel_row(conn, settings, row, subscribers))
            else:
                removed += 1
    state = policy_state(settings)
    notes = [FILTER_NOTES[key] for key in ("language", "country", "format") if run["filters"].get(key) and not run["fictional"]]
    if run["filters"].get("format") in {"short", "long"} and not run["fictional"]:
        notes.append(FORMAT_ONLY_INDETERMINATE)
    notes.extend(run["provenance"].get("warnings", [])[:3])
    return {
        "run": run, "videos": videos, "channels": channels, "removed": removed, "total": len(all_items), "limit": limit, "offset": offset,
        "derived_allowed": state.derived_allowed, "filter_notes": notes,
        "search_volume": services.metric(None, "unavailable", "YouTube", "Nenhuma API pública do YouTube informa volume de busca."),
    }


def save_run(conn: sqlite3.Connection, run_id: str, name: str | None, channel_id: str | None = None) -> dict:
    _load_run(conn, run_id, channel_id)
    label = " ".join((name or "").split())[:120] or None
    conn.execute("UPDATE research_runs SET saved_name = ? WHERE id = ?", (label, run_id))
    conn.commit()
    return get_run(conn, run_id)


def delete_run(conn: sqlite3.Connection, run_id: str, channel_id: str | None = None) -> None:
    _load_run(conn, run_id, channel_id)
    conn.execute("DELETE FROM research_runs WHERE id = ?", (run_id,))
    conn.commit()


def rerun(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, run_id: str, now: datetime,
          factory: ClientFactory = default_client) -> dict:
    run = get_run(conn, run_id)
    filters = run["filters"]
    return run_search(conn, studio, settings, kind=run["kind"], query=run["query"], channel_id=run["managed_channel_id"], now=now,
                      language=filters.get("language"), country=filters.get("country"), days=filters.get("days"),
                      video_format=filters.get("format"), order=filters.get("order", "relevance"),
                      max_subscribers=filters.get("max_subscribers"), factory=factory,
                      tags={key: filters[key] for key in ("niche", "subniche", "discovery") if key in filters} or None)


def _item_titles(conn: sqlite3.Connection, run_id: str) -> dict[tuple[str, str], dict]:
    output: dict[tuple[str, str], dict] = {}
    for item in conn.execute("SELECT item_type, item_id, rank FROM research_items WHERE run_id = ? ORDER BY rank", (run_id,)):
        if item["item_type"] == "video":
            row = conn.execute("SELECT v.title, v.id, c.title AS channel FROM videos v JOIN channels c ON c.id = v.channel_id WHERE v.id = ?", (item["item_id"],)).fetchone()
            url = services.video_url(item["item_id"])
        else:
            row = conn.execute("SELECT title, id, handle AS channel FROM channels WHERE id = ?", (item["item_id"],)).fetchone()
            url = services.channel_url(item["item_id"])
        output[(item["item_type"], item["item_id"])] = {
            "type": item["item_type"], "id": item["item_id"], "rank": item["rank"], "url": url,
            "title": row["title"] if row else None, "channel": row["channel"] if row else None,
        }
    return output


def compare_runs(conn: sqlite3.Connection, first: str, second: str, channel_id: str | None = None) -> dict:
    """Mostra o que há em comum e o que é exclusivo. Só IDs, títulos e posições: nenhum cálculo sobre views."""
    run_a, run_b = get_run(conn, first, channel_id), get_run(conn, second, channel_id)
    if run_a["data_origin"] != run_b["data_origin"]:
        raise StudioError("mixed_data_origin", "Dados fictícios e reais não podem ser comparados.", 409)
    items_a, items_b = _item_titles(conn, first), _item_titles(conn, second)
    both = [{**items_a[key], "rank_b": items_b[key]["rank"]} for key in items_a if key in items_b]
    return {"a": run_a, "b": run_b, "both": both, "only_a": [v for k, v in items_a.items() if k not in items_b],
            "only_b": [v for k, v in items_b.items() if k not in items_a]}


def export_csv(conn: sqlite3.Connection, settings: Settings, run_id: str, channel_id: str | None = None) -> tuple[str, str]:
    """Só dados crus: nenhuma métrica calculada sai no arquivo."""
    run = get_run(conn, run_id, channel_id)
    rows = []
    for item in conn.execute("SELECT item_type, item_id, rank FROM research_items WHERE run_id = ? ORDER BY rank", (run_id,)).fetchall():
        if item["item_type"] == "video":
            row = conn.execute(services.VIDEO_SELECT + " WHERE v.id = ?", (item["item_id"],)).fetchone()
            if not row:
                continue
            snap = conn.execute("SELECT view_count, captured_at FROM snapshots WHERE video_id = ? ORDER BY captured_at DESC LIMIT 1", (row["id"],)).fetchone()
            rows.append(("video", item["rank"], row["id"], row["title"], row["channel_title"], row["published_at"], row["format"],
                         snap["view_count"] if snap else None, None, snap["captured_at"] if snap else None, services.video_url(row["id"]) or ""))
        else:
            row = conn.execute("SELECT * FROM channels WHERE id = ?", (item["item_id"],)).fetchone()
            if not row:
                continue
            snap = conn.execute("SELECT subscriber_count, captured_at FROM channel_snapshots WHERE channel_id = ? ORDER BY captured_at DESC LIMIT 1", (row["id"],)).fetchone()
            rows.append(("canal", item["rank"], row["id"], row["title"], row["handle"], None, None, None,
                         snap["subscriber_count"] if snap else None, snap["captured_at"] if snap else None, services.channel_url(row["id"]) or ""))
    header = ("tipo", "posicao", "id", "titulo", "canal", "publicado_em", "formato", "views", "inscritos", "medido_em", "link")
    body = to_csv(header, rows)
    origin = "ficticio" if run["fictional"] else "youtube"
    return body, f"pesquisa_{origin}_{run_id}.csv"


def growing_topics(conn: sqlite3.Connection, settings: Settings, query: str | None = None, video_format: str | None = None) -> dict:
    """Assuntos em crescimento. Reaproveita as tendências, com a mesma trava de política."""
    data = services.trends(conn, settings, video_format)
    if data.get("blocked") or not query:
        return data
    wanted = set(tokens(query))
    return {**data, "items": [item for item in data["items"] if wanted & set(tokens(item["term"]))]}


