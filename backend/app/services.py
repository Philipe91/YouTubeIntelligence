"""Consulta o banco, aplica as métricas e devolve valores com rótulo de procedência."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .connectors.quota import QuotaLedger
from .connectors.vidiq_mcp import DisabledVidiqProvider
from .db import from_iso, to_iso, utcnow
from .metrics.acceleration import AccelerationResult, compute_acceleration
from .metrics.core import COUNT_REGIME_CHANGES, Snapshot, VideoSeries, hours_between, median
from .metrics.editorial import EditorialVideo, editorial_profile
from .metrics.opportunity import Opportunity, OpportunityInput, SampleVideo, compute_opportunity
from .metrics.outlier import OutlierResult, compute_outlier, views_at_age
from .metrics.text import normalize
from .metrics.trends import TrendInput, compute_trends
from .metrics.vph import historical_average, latest_observed, observed_intervals
from .policy import BLOCK_REASON, ORIGIN_NOTE, policy_state


def metric(value: Any, kind: str, source: str, reason: str | None = None, as_of: str | None = None) -> dict:
    return {"value": value, "kind": kind, "source": source, "reason": reason, "as_of": as_of}


def blocked(source: str) -> dict:
    return metric(None, "blocked", source, BLOCK_REASON)


def video_url(video_id: str) -> str | None:
    return None if video_id.startswith("DEMO_") else f"https://www.youtube.com/watch?v={video_id}"


def channel_url(channel_id: str) -> str | None:
    return None if channel_id.startswith("DEMO_") else f"https://www.youtube.com/channel/{channel_id}"


@dataclass
class Analysis:
    series: dict[str, VideoSeries]
    outliers: dict[str, OutlierResult]
    accelerations: dict[str, AccelerationResult]


_analysis_cache: dict[tuple, Analysis] = {}


def _data_version(conn: sqlite3.Connection) -> tuple:
    row = conn.execute("SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS last FROM snapshots").fetchone()
    videos = conn.execute("SELECT COUNT(*) AS n FROM videos").fetchone()["n"]
    return (row["n"], row["last"], videos)


def load_series(conn: sqlite3.Connection) -> dict[str, VideoSeries]:
    points: dict[str, list[Snapshot]] = {}
    for row in conn.execute("SELECT video_id, captured_at, view_count FROM snapshots ORDER BY captured_at"):
        points.setdefault(row["video_id"], []).append(Snapshot(from_iso(row["captured_at"]), row["view_count"]))
    return {
        row["id"]: VideoSeries(row["id"], row["channel_id"], row["format"], from_iso(row["published_at"]),
                               tuple(points.get(row["id"], ())))
        for row in conn.execute("SELECT id, channel_id, format, published_at FROM videos")
    }


def analyze(conn: sqlite3.Connection, settings: Settings) -> Analysis:
    database_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    # Banco em memória (testes) não tem identidade estável: não entra no cache.
    key = (database_file, _data_version(conn), json.dumps(settings.scoring, sort_keys=True))
    if database_file and key in _analysis_cache:
        return _analysis_cache[key]
    series = load_series(conn)
    by_group: dict[tuple[str, str], list[VideoSeries]] = {}
    for item in series.values():
        by_group.setdefault((item.channel_id, item.format), []).append(item)
    outliers = {
        vid: compute_outlier(item, by_group[(item.channel_id, item.format)], settings.scoring["outlier"])
        for vid, item in series.items()
    }
    accelerations = {vid: compute_acceleration(item, settings.scoring["acceleration"]) for vid, item in series.items()}
    result = Analysis(series, outliers, accelerations)
    _analysis_cache.clear()
    _analysis_cache[key] = result
    return result


FORMAT_SOURCE_LABEL = {
    "analytics": ("measured", "YouTube Analytics (creatorContentType)"),
    "duration": ("estimated", "Estimado pela duração: a Data API não informa se é Short"),
    "broadcast": ("measured", "liveStreamingDetails"),
    "missing": ("unavailable", "Duração ausente"),
}


def _video_row(row: sqlite3.Row, analysis: Analysis, settings: Settings) -> dict:
    allowed = policy_state(settings).derived_allowed
    series = analysis.series[row["id"]]
    valid = series.valid_snapshots()
    latest = valid[-1] if valid else None
    as_of = to_iso(latest.captured_at) if latest else None
    views = (metric(latest.views, "measured", "videos.list", as_of=as_of) if latest
             else metric(None, "unavailable", "videos.list", "A API não retornou a contagem de views."))
    kind, source = FORMAT_SOURCE_LABEL[row["format_source"]]
    output: dict[str, Any] = {
        "id": row["id"], "title": row["title"], "channel_id": row["channel_id"], "channel_title": row["channel_title"],
        "published_at": row["published_at"], "duration_seconds": row["duration_seconds"], "language": row["language"],
        "country": row["country"] or row["channel_country"], "thumbnail_url": row["thumbnail_url"],
        "format": row["format"], "format_label": metric(row["format"], kind, source),
        "source_url": video_url(row["id"]), "views": views, "snapshot_count": len(valid),
        "age_hours": hours_between(series.published_at, latest.captured_at) if latest else None,
    }
    if not allowed:
        output.update(vph_observed=blocked("snapshots"), vph_average=blocked("views / idade"),
                      idr=blocked("IDR"), acceleration=None, outlier=None, derived_blocked=True)
        return output

    interval = latest_observed(series, settings.scoring["vph"])
    output["vph_observed"] = (
        metric(interval.vph, "calculated", "Δviews / Δhoras entre snapshots", as_of=to_iso(interval.end))
        if interval else metric(None, "unavailable", "snapshots", "Precisa de dois snapshots válidos.")
    )
    average = historical_average(latest.views, series.published_at, latest.captured_at) if latest else None
    output["vph_average"] = (metric(average, "calculated", "views / horas desde a publicação", as_of=as_of)
                             if average is not None else metric(None, "unavailable", "views / idade", "Sem views."))
    outlier = analysis.outliers[row["id"]]
    output["idr"] = (metric(outlier.idr, "calculated", "IDR próprio deste aplicativo", as_of=as_of)
                     if outlier.idr is not None else metric(None, "unavailable", "IDR próprio deste aplicativo", outlier.explanation))
    output["outlier"] = {
        "status": outlier.status, "band": outlier.band, "confidence": outlier.confidence,
        "sample_size": outlier.sample_size, "robust_z": outlier.robust_z, "warnings": list(outlier.warnings),
    }
    acceleration = analysis.accelerations[row["id"]]
    output["acceleration"] = {
        "status": acceleration.status, "ratio": acceleration.ratio, "recent_vph": acceleration.recent_vph,
        "previous_vph": acceleration.previous_vph,
    }
    output["derived_blocked"] = False
    return output


VIDEO_SELECT = """SELECT v.*, c.title AS channel_title, c.country AS channel_country, c.niche_id AS niche_id, c.is_own AS is_own
                  FROM videos v JOIN channels c ON c.id = v.channel_id"""


def list_videos(conn: sqlite3.Connection, settings: Settings, *, video_format: str | None = None, q: str | None = None,
                niche_id: int | None = None, language: str | None = None, country: str | None = None,
                channel_id: str | None = None, days: int | None = None, sort: str = "idr", limit: int = 100,
                outliers_only: bool = False) -> dict:
    clauses, params = [], []
    for column, value in (("v.format", video_format), ("c.niche_id", niche_id), ("v.language", language), ("v.channel_id", channel_id)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if country:
        clauses.append("COALESCE(v.country, c.country) = ?")
        params.append(country)
    if days:
        clauses.append("v.published_at >= ?")
        params.append(to_iso(utcnow() - timedelta(days=days)))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(VIDEO_SELECT + where, params).fetchall()
    if q:
        needle = normalize(q)
        rows = [row for row in rows if needle in normalize(row["title"])]
    analysis = analyze(conn, settings)
    items = [_video_row(row, analysis, settings) for row in rows]
    if outliers_only:
        items = [item for item in items if item["idr"]["value"] is not None and item["idr"]["value"] >= settings.scoring["outlier"]["band_above"]]

    def sort_key(item: dict):
        if sort == "views":
            return item["views"]["value"] or -1
        if sort == "vph":
            return item["vph_observed"]["value"] or -1
        if sort == "recent":
            return from_iso(item["published_at"]).timestamp()
        return item["idr"]["value"] or -1

    items.sort(key=sort_key, reverse=True)
    return {"total": len(items), "items": items[:limit]}


def video_detail(conn: sqlite3.Connection, settings: Settings, video_id: str) -> dict | None:
    row = conn.execute(VIDEO_SELECT + " WHERE v.id = ?", (video_id,)).fetchone()
    if row is None:
        return None
    analysis = analyze(conn, settings)
    series = analysis.series[video_id]
    output = _video_row(row, analysis, settings)
    output["description"] = row["description"]
    output["snapshots"] = [
        {"captured_at": to_iso(s.captured_at), "views": s.views,
         "age_hours": hours_between(series.published_at, s.captured_at)}
        for s in series.valid_snapshots()
    ]
    output["outlier_explanation"] = None
    output["acceleration_explanation"] = None
    output["intervals"] = []
    output["peer_curve"] = []
    if output["derived_blocked"]:
        return output
    output["outlier_explanation"] = analysis.outliers[video_id].explanation
    output["acceleration_explanation"] = analysis.accelerations[video_id].explanation
    output["intervals"] = [
        {"start": to_iso(i.start), "end": to_iso(i.end), "hours": i.hours, "delta_views": i.delta_views, "vph": i.vph, "flags": list(i.flags)}
        for i in observed_intervals(series, settings.scoring["vph"])
    ][-48:]
    output["peer_curve"] = _peer_curve(analysis, series, settings)
    return output


def _peer_curve(analysis: Analysis, series: VideoSeries, settings: Settings) -> list[dict]:
    """Mediana dos pares ao longo das idades do vídeo. Pontos sem amostra mínima ficam de fora."""
    config = settings.scoring["outlier"]
    peers = [p for p in analysis.series.values()
             if p.channel_id == series.channel_id and p.format == series.format and p.video_id != series.video_id]
    valid = series.valid_snapshots()
    if not valid:
        return []
    last_age = hours_between(series.published_at, valid[-1].captured_at)
    curve = []
    for step in range(1, 25):
        age = last_age * step / 24
        values = [v for v in (views_at_age(p, age, config) for p in peers) if v is not None]
        if len(values) >= config["min_sample"]:
            curve.append({"age_hours": age, "median_views": median(values), "sample": len(values)})
    return curve


def _latest_subscribers(conn: sqlite3.Connection) -> dict[str, int | None]:
    return {
        row["channel_id"]: row["subscriber_count"]
        for row in conn.execute(
            """SELECT cs.channel_id, cs.subscriber_count FROM channel_snapshots cs
               JOIN (SELECT channel_id, MAX(captured_at) AS last FROM channel_snapshots GROUP BY channel_id) m
                 ON m.channel_id = cs.channel_id AND m.last = cs.captured_at""")
    }


def list_channels(conn: sqlite3.Connection, settings: Settings) -> list[dict]:
    allowed = policy_state(settings).derived_allowed
    analysis = analyze(conn, settings)
    subscribers = _latest_subscribers(conn)
    rows = conn.execute(
        """SELECT c.*, n.name AS niche_name FROM channels c LEFT JOIN niches n ON n.id = c.niche_id
           WHERE c.monitored = 1 OR c.is_own = 1 ORDER BY c.is_own DESC, c.title"""
    ).fetchall()
    videos = conn.execute("SELECT id, channel_id, format FROM videos").fetchall()
    output = []
    for row in rows:
        mine = [v for v in videos if v["channel_id"] == row["id"]]
        per_format = {}
        for video_format in ("short", "long"):
            group = [v["id"] for v in mine if v["format"] == video_format]
            valid = [analysis.series[v].valid_snapshots() for v in group]
            views = [float(s[-1].views) for s in valid if s]
            scored = [analysis.outliers[v] for v in group if analysis.outliers[v].idr is not None]
            per_format[video_format] = {
                "videos": len(group),
                "median_views": median(views) if views and allowed else None,
                "outliers": sum(1 for o in scored if o.idr >= settings.scoring["outlier"]["band_above"]) if allowed else None,
                "scored": len(scored) if allowed else None,
            }
        count = subscribers.get(row["id"])
        output.append({
            "id": row["id"], "title": row["title"], "handle": row["handle"], "country": row["country"],
            "language": row["default_language"], "is_own": bool(row["is_own"]), "monitored": bool(row["monitored"]),
            "niche": row["niche_name"], "thumbnail_url": row["thumbnail_url"], "source_url": channel_url(row["id"]),
            "subscribers": (metric(count, "measured", "channels.list") if count is not None
                            else metric(None, "unavailable", "channels.list", "O canal oculta os inscritos.")),
            "formats": per_format, "derived_blocked": not allowed,
        })
    return output


def channel_detail(conn: sqlite3.Connection, settings: Settings, channel_id: str) -> dict | None:
    channel = next((c for c in list_channels(conn, settings) if c["id"] == channel_id), None)
    if channel is None:
        return None
    analysis = analyze(conn, settings)
    allowed = policy_state(settings).derived_allowed
    rows = conn.execute("SELECT * FROM videos WHERE channel_id = ?", (channel_id,)).fetchall()
    videos = [
        EditorialVideo(row["id"], row["title"], row["format"], from_iso(row["published_at"]), row["duration_seconds"],
                       analysis.outliers[row["id"]].idr if allowed else None)
        for row in rows
    ]
    # Cadência, medianas e termos também são derivados: ficam sujeitos à mesma trava.
    channel["editorial"] = {fmt: editorial_profile(videos, fmt).to_dict() for fmt in ("short", "long")} if allowed else None
    channel["editorial_note"] = "Termos com melhor desempenho indicam correlação, não causa."
    channel["subscriber_history"] = [
        {"captured_at": row["captured_at"], "subscribers": row["subscriber_count"]}
        for row in conn.execute("SELECT captured_at, subscriber_count FROM channel_snapshots WHERE channel_id = ? ORDER BY captured_at", (channel_id,))
    ]
    return channel


def compare_channels(conn: sqlite3.Connection, settings: Settings, video_format: str) -> dict:
    state = policy_state(settings)
    if not state.derived_allowed:
        return {"blocked": True, "reason": BLOCK_REASON, "rows": []}
    analysis = analyze(conn, settings)
    rows = []
    for channel in list_channels(conn, settings):
        mine = conn.execute("SELECT * FROM videos WHERE channel_id = ?", (channel["id"],)).fetchall()
        videos = [EditorialVideo(r["id"], r["title"], r["format"], from_iso(r["published_at"]), r["duration_seconds"],
                                 analysis.outliers[r["id"]].idr) for r in mine]
        profile = editorial_profile(videos, video_format)
        info = channel["formats"][video_format]
        rows.append({
            "channel_id": channel["id"], "title": channel["title"], "is_own": channel["is_own"],
            "subscribers": channel["subscribers"], "sample_size": profile.sample_size, "uploads_per_week": profile.uploads_per_week,
            "median_duration_seconds": profile.median_duration_seconds, "median_views": info["median_views"],
            "outliers": info["outliers"], "scored": info["scored"], "question_title_share": profile.question_title_share,
            "top_weekday": profile.top_weekday,
        })
    return {"blocked": False, "origin_note": ORIGIN_NOTE, "rows": rows}


def trends(conn: sqlite3.Connection, settings: Settings, video_format: str | None = None, niche_id: int | None = None) -> dict:
    if not policy_state(settings).derived_allowed:
        return {"blocked": True, "reason": BLOCK_REASON, "items": []}
    analysis = analyze(conn, settings)
    rows = conn.execute(VIDEO_SELECT).fetchall()
    inputs = []
    for row in rows:
        if niche_id is not None and row["niche_id"] != niche_id:
            continue
        acceleration = analysis.accelerations[row["id"]]
        inputs.append(TrendInput(row["id"], row["channel_id"], row["title"], row["format"], acceleration.status,
                                 acceleration.recent_vph, acceleration.previous_vph))
    items = [t.to_dict() for t in compute_trends(inputs, settings.scoring["trends"])]
    if video_format:
        items = [t for t in items if t["format"] == video_format]
    return {"blocked": False, "items": items, "origin_note": ORIGIN_NOTE,
            "window_hours": settings.scoring["acceleration"]["window_hours"]}


def _vocabulary(conn: sqlite3.Connection, niche_id: int | None) -> tuple[str, ...]:
    words: list[str] = []
    for row in conn.execute("SELECT id, keywords_json FROM niches"):
        if niche_id is None or row["id"] == niche_id:
            words.extend(json.loads(row["keywords_json"]))
    for row in conn.execute("SELECT v.title AS title FROM videos v JOIN channels c ON c.id = v.channel_id WHERE c.is_own = 1"):
        words.append(row["title"])
    return tuple(words)


def _sample_video(row: sqlite3.Row, analysis: Analysis, subscribers: dict, now: datetime) -> SampleVideo:
    series = analysis.series[row["id"]]
    valid = series.valid_snapshots()
    moment = valid[-1].captured_at if valid else now
    return SampleVideo(row["id"], row["channel_id"], valid[-1].views if valid else None,
                       max(hours_between(series.published_at, moment) / 24, 0.0),
                       subscribers.get(row["channel_id"]), len(valid), row["format"])


def compute_opportunities(conn: sqlite3.Connection, settings: Settings, *, video_format: str | None = None,
                          niche_id: int | None = None, language: str | None = None, country: str | None = None) -> list[Opportunity]:
    analysis = analyze(conn, settings)
    subscribers = _latest_subscribers(conn)
    vocabulary = _vocabulary(conn, niche_id)
    now = utcnow()
    clauses, params = [], []
    for column, value in (("niche_id", niche_id), ("language", language), ("country", country)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    latest = conn.execute(f"SELECT query, MAX(id) AS id FROM searches{where} GROUP BY query", params).fetchall()
    results: list[Opportunity] = []
    for search in latest:
        info = conn.execute("SELECT total_results_approx FROM searches WHERE id = ?", (search["id"],)).fetchone()
        rows = conn.execute(
            "SELECT v.id, v.channel_id, v.format FROM search_results r JOIN videos v ON v.id = r.video_id WHERE r.search_id = ?",
            (search["id"],),
        ).fetchall()
        samples = tuple(_sample_video(row, analysis, subscribers, now) for row in rows)
        for fmt in ("short", "long"):
            if video_format and fmt != video_format:
                continue
            results.append(compute_opportunity(
                OpportunityInput(search["query"], fmt, samples, vocabulary, info["total_results_approx"]),
                settings.scoring["opportunity"],
            ))
    results.sort(key=lambda o: (o.score is None, -(o.score or 0), o.topic))
    return results


def _opportunity_payload(item: Opportunity) -> dict:
    return {
        "topic": item.topic, "format": item.format, "status": item.status,
        "score": metric(item.score, "estimated", "Ranking experimental deste aplicativo",
                        None if item.score is not None else "Confiança abaixo do mínimo."),
        "demand": metric(item.demand, "estimated", "Proxy: mediana de views por dia na amostra de busca",
                         None if item.demand is not None else "Sem views na amostra."),
        "competition": metric(item.competition, "estimated", "Porte dos canais, oferta recente, totalResults aproximado",
                              None if item.competition is not None else "Sem dados na amostra."),
        "relevance": metric(item.relevance, "calculated", "Palavras do tema no vocabulário do nicho ou do canal"),
        "confidence": metric(item.confidence, "calculated", "Amostra, diversidade de canais, cobertura de snapshots"),
        "search_volume": metric(None, "unavailable", "YouTube", "Nenhuma API pública do YouTube informa volume de busca."),
        "sample_size": item.sample_size, "distinct_channels": item.distinct_channels,
        "median_views_per_day": item.median_views_per_day, "median_subscribers": item.median_subscribers,
        "recent_share": item.recent_share, "total_results_approx": item.total_results_approx,
        "competition_parts": item.competition_parts, "justification": list(item.justification),
        "video_ids": list(item.video_ids),
    }


def opportunities(conn: sqlite3.Connection, settings: Settings, **filters) -> dict:
    if not policy_state(settings).derived_allowed:
        return {"blocked": True, "reason": BLOCK_REASON, "items": []}
    return {"blocked": False, "origin_note": ORIGIN_NOTE,
            "notice": "Ranking experimental. Indica onde olhar, não prevê resultado de nenhum vídeo.",
            "items": [_opportunity_payload(o) for o in compute_opportunities(conn, settings, **filters)]}


def opportunity_detail(conn: sqlite3.Connection, settings: Settings, topic: str, video_format: str) -> dict | None:
    if not policy_state(settings).derived_allowed:
        return {"blocked": True, "reason": BLOCK_REASON}
    match = next((o for o in compute_opportunities(conn, settings, video_format=video_format) if o.topic == topic), None)
    if match is None:
        return None
    output = _opportunity_payload(match)
    analysis = analyze(conn, settings)
    videos = []
    for video_id in match.video_ids:
        row = conn.execute(VIDEO_SELECT + " WHERE v.id = ?", (video_id,)).fetchone()
        if row:
            videos.append(_video_row(row, analysis, settings))
    videos.sort(key=lambda v: v["idr"]["value"] or -1, reverse=True)
    output["videos"] = videos[:30]
    output["blocked"] = False
    output["origin_note"] = ORIGIN_NOTE
    output["generations"] = [
        {"id": row["id"], "provider": row["provider"], "model": row["model"], "is_ai": bool(row["is_ai"]),
         "created_at": row["created_at"], "output": json.loads(row["output_json"])}
        for row in conn.execute(
            "SELECT * FROM ai_generations WHERE topic = ? AND format = ? ORDER BY id DESC LIMIT 5", (topic, video_format))
    ]
    return output


CONTENT_TYPE_LABEL = {"SHORTS": "short", "VIDEO_ON_DEMAND": "long", "LIVE_STREAM": "live", "STORY": "story", "UNSPECIFIED": "unknown"}


def own_channels(conn: sqlite3.Connection, settings: Settings, days: int = 28) -> list[dict]:
    """Só métricas medidas. Retenção é a porcentagem média; a curva e o CTR não são coletados."""
    output = []
    latest_day = conn.execute("SELECT MAX(day) AS d FROM analytics_daily").fetchone()["d"]
    for channel in conn.execute("SELECT * FROM channels WHERE is_own = 1").fetchall():
        by_type: dict[str, dict] = {}
        if latest_day:
            end = datetime.fromisoformat(latest_day)
            start = (end - timedelta(days=days - 1)).date().isoformat()
            rows = conn.execute(
                "SELECT * FROM analytics_daily WHERE channel_id = ? AND day >= ? ORDER BY day", (channel["id"], start)
            ).fetchall()
            for row in rows:
                group = by_type.setdefault(row["content_type"], {"rows": []})
                group["rows"].append(row)
        formats = []
        for content_type, group in by_type.items():
            rows = group["rows"]
            total_views = sum(r["views"] or 0 for r in rows)
            percentages = [(r["average_view_percentage"], r["views"] or 0) for r in rows if r["average_view_percentage"] is not None]
            weight = sum(v for _, v in percentages)
            formats.append({
                "content_type": content_type, "format": CONTENT_TYPE_LABEL.get(content_type, "unknown"),
                "views": metric(total_views, "measured", "YouTube Analytics"),
                "minutes_watched": metric(sum(r["estimated_minutes_watched"] or 0 for r in rows), "measured", "YouTube Analytics"),
                "average_view_percentage": metric(sum(p * v for p, v in percentages) / weight if weight else None,
                                                  "calculated" if weight else "unavailable",
                                                  "Média de averageViewPercentage ponderada por views",
                                                  None if weight else "Sem dados no período."),
                "subscribers_net": metric(sum((r["subscribers_gained"] or 0) - (r["subscribers_lost"] or 0) for r in rows), "measured", "YouTube Analytics"),
                "ctr": metric(None, "unavailable", "YouTube Analytics API", "A API não lista CTR nem impressões de thumbnail. Consulte o YouTube Studio."),
                "daily": [{"day": r["day"], "views": r["views"]} for r in rows],
            })
        formats.sort(key=lambda f: f["content_type"])
        output.append({
            "id": channel["id"], "title": channel["title"], "source_url": channel_url(channel["id"]),
            "days": days, "as_of": latest_day, "formats": formats, "has_analytics": bool(formats),
        })
    return output


def filters(conn: sqlite3.Connection) -> dict:
    def distinct(sql: str) -> list[str]:
        return [row[0] for row in conn.execute(sql) if row[0]]

    return {
        "niches": [{"id": r["id"], "name": r["name"]} for r in conn.execute("SELECT id, name FROM niches ORDER BY name")],
        "languages": distinct("SELECT DISTINCT language FROM videos ORDER BY 1"),
        "countries": distinct("SELECT DISTINCT country FROM channels ORDER BY 1"),
        "channels": [{"id": r["id"], "title": r["title"]} for r in conn.execute(
            "SELECT id, title FROM channels WHERE monitored = 1 OR is_own = 1 ORDER BY title")],
    }


def system_status(conn: sqlite3.Connection, settings: Settings) -> dict:
    state = policy_state(settings)
    now = utcnow()
    counts = {
        table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        for table in ("channels", "videos", "snapshots", "searches", "ai_generations")
    }
    return {
        "mode": settings.mode,
        "policy": {
            "state": state.state, "derived_allowed": state.derived_allowed, "stats_retention": state.stats_retention,
            "text_retention_days": state.text_retention_days, "description": state.description,
            "approval_declared": bool(settings.approval_ref),
        },
        "credentials": {
            "youtube_api_key": bool(settings.youtube_api_key),
            "oauth_client": bool(settings.oauth_client_secrets),
            "own_channels_authorized": conn.execute("SELECT COUNT(*) AS n FROM oauth_channels").fetchone()["n"],
        },
        "ai": {"provider": settings.ai_provider, "model": settings.ai_model if settings.ai_provider != "none" else None},
        "vidiq": DisabledVidiqProvider().status(),
        "quota": QuotaLedger(conn, settings).usage(now),
        "jobs": [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY name")],
        "counts": counts,
        "count_changes": [{"date": m.date().isoformat(), "description": d} for m, _, d in COUNT_REGIME_CHANGES],
        "scoring": settings.scoring,
    }


def overview(conn: sqlite3.Connection, settings: Settings, video_format: str | None = None) -> dict:
    state = policy_state(settings)
    if not state.derived_allowed:
        recent = list_videos(conn, settings, video_format=video_format, sort="recent", limit=8)
        return {"blocked": True, "reason": BLOCK_REASON, "recent": recent["items"], "counts": system_status(conn, settings)["counts"]}
    items = opportunities(conn, settings, video_format=video_format)["items"]
    videos = list_videos(conn, settings, video_format=video_format, limit=5000)["items"]
    rising = [v for v in videos if v["acceleration"]["status"] in {"acelerando", "emergente"}]
    rising.sort(key=lambda v: v["acceleration"]["recent_vph"] or 0, reverse=True)
    outliers = [v for v in videos if v["idr"]["value"] is not None and v["outlier"]["band"] in {"muito_acima", "extremo"}]
    trend_items = trends(conn, settings, video_format)["items"]
    insufficient = sum(1 for v in videos if v["outlier"] and v["outlier"]["status"] == "insufficient_sample")
    return {
        "blocked": False, "origin_note": ORIGIN_NOTE,
        "top_opportunities": items[:4], "rising": rising[:6], "outliers": outliers[:6], "trends": trend_items[:6],
        "health": {"videos": len(videos), "insufficient_sample": insufficient, "rising": len(rising), "outliers": len(outliers)},
    }
