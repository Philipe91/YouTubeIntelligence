"""Coleta: grava dados crus e snapshots. Não calcula métricas."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .config import Settings
from .connectors import oauth, youtube_analytics
from .connectors.quota import QuotaLedger
from .connectors.youtube_data import YouTubeDataClient, YouTubeApiError
from .db import from_iso, to_iso
from .metrics.classify import classify_format, parse_duration
from .policy import delete_channel_data


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_channel(conn: sqlite3.Connection, item: dict, now: datetime, *, is_own: bool = False,
                   monitored: bool = False, niche_id: int | None = None) -> str:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    stamp = to_iso(now)
    conn.execute(
        """INSERT INTO channels (id, title, handle, description, country, default_language, thumbnail_url,
               uploads_playlist_id, is_own, monitored, niche_id, text_refreshed_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET title = excluded.title, handle = excluded.handle,
               description = excluded.description, country = excluded.country,
               default_language = excluded.default_language, thumbnail_url = excluded.thumbnail_url,
               uploads_playlist_id = COALESCE(excluded.uploads_playlist_id, channels.uploads_playlist_id),
               is_own = MAX(channels.is_own, excluded.is_own), monitored = MAX(channels.monitored, excluded.monitored),
               niche_id = COALESCE(excluded.niche_id, channels.niche_id), text_refreshed_at = excluded.text_refreshed_at""",
        (item["id"], snippet.get("title", ""), snippet.get("customUrl"), snippet.get("description"),
         snippet.get("country"), snippet.get("defaultLanguage"),
         snippet.get("thumbnails", {}).get("default", {}).get("url"), uploads, int(is_own), int(monitored),
         niche_id, stamp, stamp),
    )
    subscribers = None if stats.get("hiddenSubscriberCount") else _int(stats.get("subscriberCount"))
    conn.execute(
        "INSERT OR REPLACE INTO channel_snapshots (channel_id, captured_at, subscriber_count, view_count, video_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (item["id"], stamp, subscribers, _int(stats.get("viewCount")), _int(stats.get("videoCount"))),
    )
    return item["id"]


def upsert_video(conn: sqlite3.Connection, item: dict, now: datetime, settings: Settings) -> str:
    snippet = item.get("snippet", {})
    duration = parse_duration(item.get("contentDetails", {}).get("duration"))
    format_config = settings.scoring["format"]
    video_format, source = classify_format(
        duration, format_config["short_max_seconds"],
        live_broadcast_content=snippet.get("liveBroadcastContent"),
        has_live_details="liveStreamingDetails" in item,
        published_at=snippet.get("publishedAt"),
        short_cutoff=format_config["three_minute_shorts_since"],
        legacy_short_max_seconds=format_config["legacy_short_max_seconds"],
        embed_width=item.get("player", {}).get("embedWidth"),
        embed_height=item.get("player", {}).get("embedHeight"),
    )
    stamp = to_iso(now)
    language = snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage")
    thumbnails = snippet.get("thumbnails", {})
    thumbnail = (thumbnails.get("medium") or thumbnails.get("default") or {}).get("url")
    conn.execute(
        """INSERT INTO videos (id, channel_id, title, description, published_at, duration_seconds, format, format_source,
               language, thumbnail_url, category_id, text_refreshed_at, first_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET title = excluded.title, description = excluded.description,
               duration_seconds = excluded.duration_seconds,
               format = CASE WHEN videos.format_source = 'analytics' THEN videos.format ELSE excluded.format END,
               format_source = CASE WHEN videos.format_source = 'analytics' THEN videos.format_source ELSE excluded.format_source END,
               language = excluded.language, thumbnail_url = excluded.thumbnail_url, category_id = excluded.category_id,
               text_refreshed_at = excluded.text_refreshed_at""",
        (item["id"], snippet["channelId"], snippet.get("title", ""), snippet.get("description"), snippet["publishedAt"],
         duration, video_format, source, language, thumbnail, snippet.get("categoryId"), stamp, stamp),
    )
    stats = item.get("statistics", {})
    conn.execute(
        "INSERT OR REPLACE INTO snapshots (video_id, captured_at, view_count, like_count, comment_count) VALUES (?, ?, ?, ?, ?)",
        (item["id"], stamp, _int(stats.get("viewCount")), _int(stats.get("likeCount")), _int(stats.get("commentCount"))),
    )
    return item["id"]


def add_channel(client: YouTubeDataClient, conn: sqlite3.Connection, reference: str, now: datetime,
                *, niche_id: int | None = None, is_own: bool = False) -> str:
    """Cadastra um canal por ID (UC...) ou @handle e passa a monitorá-lo."""
    reference = reference.strip()
    response = client.channels(handle=reference) if reference.startswith("@") else client.channels(ids=[reference])
    items = response.get("items", [])
    if not items:
        raise YouTubeApiError(f"Canal não encontrado: {reference}")
    channel_id = upsert_channel(conn, items[0], now, is_own=is_own, monitored=True, niche_id=niche_id)
    conn.commit()
    return channel_id


def collect_channel_videos(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings,
                           channel_id: str, now: datetime, max_videos: int = 100) -> list[str]:
    """Usa a playlist de uploads, muito mais barata que search.list."""
    row = conn.execute("SELECT uploads_playlist_id FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not row or not row["uploads_playlist_id"]:
        raise YouTubeApiError(f"Canal sem playlist de uploads: {channel_id}")
    ids: list[str] = []
    token = None
    while len(ids) < max_videos:
        page = client.playlist_items(row["uploads_playlist_id"], page_token=token)
        ids.extend(item["contentDetails"]["videoId"] for item in page.get("items", []))
        token = page.get("nextPageToken")
        if not token:
            break
    ids = ids[:max_videos]
    _hydrate_videos(client, conn, settings, ids, now, use_cache=False)
    return ids


def _hydrate_videos(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings, ids: list[str],
                    now: datetime, use_cache: bool) -> list[dict]:
    items: list[dict] = []
    # Resposta do cache mantém a data da busca original: não vira uma medição nova.
    measured: list[tuple[dict, datetime]] = []
    for start in range(0, len(ids), 50):
        batch = client.videos(ids[start:start + 50], use_cache=use_cache).get("items", [])
        items.extend(batch)
        measured.extend((item, client.last_fetched_at or now) for item in batch)
    _ensure_channels(client, conn, {item["snippet"]["channelId"] for item in items}, now)
    for item, moment in measured:
        upsert_video(conn, item, moment, settings)
    conn.commit()
    return items


def _ensure_channels(client: YouTubeDataClient, conn: sqlite3.Connection, channel_ids: set[str], now: datetime) -> None:
    known = {row["id"] for row in conn.execute("SELECT id FROM channels")}
    missing = sorted(channel_ids - known)
    for start in range(0, len(missing), 50):
        for item in client.channels(ids=missing[start:start + 50]).get("items", []):
            upsert_channel(conn, item, client.last_fetched_at or now)
    conn.commit()


def refresh_channel_stats(client: YouTubeDataClient, conn: sqlite3.Connection, channel_ids: list[str], now: datetime) -> None:
    """Inscritos atuais antes de filtrar por tamanho. O cache de 6 horas evita gastar à toa."""
    for start in range(0, len(channel_ids), 50):
        for item in client.channels(ids=channel_ids[start:start + 50]).get("items", []):
            upsert_channel(conn, item, client.last_fetched_at or now)
    conn.commit()


def search_niche(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings, query: str, now: datetime,
                 *, niche_id: int | None = None, language: str | None = None, country: str | None = None,
                 published_after: str | None = None, published_before: str | None = None,
                 order: str = "relevance", pages: int = 1) -> dict:
    """Busca e grava resultados. Cada página custa 1 chamada do balde de busca (100 por dia, por padrão)."""
    ids: list[str] = []
    total = None
    token = None
    for _ in range(pages):
        page = client.search_videos(query, language, country, published_after, published_before, order, page_token=token)
        total = page.get("pageInfo", {}).get("totalResults", total)
        ids.extend(item["id"]["videoId"] for item in page.get("items", []) if item.get("id", {}).get("videoId"))
        token = page.get("nextPageToken")
        if not token:
            break
    ids = list(dict.fromkeys(ids))
    items = _hydrate_videos(client, conn, settings, ids, now, use_cache=True)
    cursor = conn.execute(
        "INSERT INTO searches (query, niche_id, language, country, published_after, published_before, sort_order, "
        "total_results_approx, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (query, niche_id, language, country, published_after, published_before, order, total, to_iso(now)),
    )
    search_id = cursor.lastrowid
    returned = {item["id"] for item in items}
    rank = 0
    for video_id in ids:
        if video_id in returned:
            rank += 1
            conn.execute("INSERT INTO search_results (search_id, video_id, rank) VALUES (?, ?, ?)", (search_id, video_id, rank))
    conn.commit()
    return {"search_id": search_id, "videos": rank, "total_results_approx": total}


def videos_due_for_snapshot(conn: sqlite3.Connection, settings: Settings, now: datetime) -> list[str]:
    tiers = settings.scoring["snapshots"]["tiers"]
    limit = settings.scoring["snapshots"]["max_videos_per_run"]
    rows = conn.execute(
        """SELECT v.id, v.published_at, MAX(s.captured_at) AS last_capture FROM videos v
           JOIN channels c ON c.id = v.channel_id
           LEFT JOIN snapshots s ON s.video_id = v.id
           WHERE c.monitored = 1 OR c.is_own = 1 OR v.id IN (SELECT video_id FROM search_results) OR v.id IN (SELECT video_id FROM study_videos)
           GROUP BY v.id ORDER BY v.published_at DESC"""
    ).fetchall()
    due: list[str] = []
    for row in rows:
        age_hours = (now - from_iso(row["published_at"])).total_seconds() / 3600
        interval = next((hours for max_age, hours in tiers if age_hours <= max_age), tiers[-1][1])
        if row["last_capture"] is None or (now - from_iso(row["last_capture"])).total_seconds() / 3600 >= interval:
            due.append(row["id"])
        if len(due) >= limit:
            break
    return due


def take_snapshots(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings, now: datetime) -> dict:
    """Mede agora, sempre sem cache. Vídeo que sumiu da API é removido da base."""
    due = videos_due_for_snapshot(conn, settings, now)
    returned: set[str] = set()
    for start in range(0, len(due), 50):
        batch = due[start:start + 50]
        response = client.videos(batch, use_cache=False)
        for item in response.get("items", []):
            upsert_video(conn, item, now, settings)
            returned.add(item["id"])
        conn.commit()
    removed = [video_id for video_id in due if video_id not in returned]
    conn.executemany("DELETE FROM videos WHERE id = ?", [(video_id,) for video_id in removed])
    conn.commit()
    return {"requested": len(due), "captured": len(returned), "removed": len(removed)}


def refresh_channels(client: YouTubeDataClient, conn: sqlite3.Connection, now: datetime) -> int:
    ids = [row["id"] for row in conn.execute("SELECT id FROM channels")]
    refreshed = 0
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        for item in client.channels(ids=batch, use_cache=False).get("items", []):
            upsert_channel(conn, item, now)
            refreshed += 1
    conn.commit()
    return refreshed


def discover_monitored(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings, now: datetime) -> int:
    found = 0
    for row in conn.execute("SELECT id FROM channels WHERE monitored = 1 OR is_own = 1").fetchall():
        found += len(collect_channel_videos(client, conn, settings, row["id"], now, max_videos=50))
    return found


def sync_own_analytics(conn: sqlite3.Connection, settings: Settings, store: oauth.TokenStore, now: datetime,
                       days: int = 90, transport=None) -> dict:
    """Atualiza analytics e reconfere a autorização. Autorização perdida apaga os dados do canal."""
    synced: dict[str, int] = {}
    rows = conn.execute("SELECT channel_id FROM oauth_channels").fetchall()
    if not rows:
        return synced
    client_id, client_secret = oauth.load_client_secrets(settings.oauth_client_secrets)
    for row in rows:
        channel_id = row["channel_id"]
        refresh = store.get(channel_id)
        if not refresh:
            delete_channel_data(conn, channel_id)
            continue
        try:
            access = oauth.refresh_access_token(client_id, client_secret, refresh, transport)
        except oauth.OAuthError as error:
            if error.invalid_grant:
                store.delete(channel_id)
                delete_channel_data(conn, channel_id)
                continue
            raise
        ledger = QuotaLedger(conn, settings)
        ledger.check("reports.query", now)
        bucket, units = ledger.cost("reports.query")
        try:
            rows_out = youtube_analytics.fetch_daily_by_content_type(
                access, (now - timedelta(days=days)).date().isoformat(), now.date().isoformat(), transport
            )
        except youtube_analytics.AnalyticsError as error:
            ledger.record("analytics", "reports.query", bucket, units, None, type(error).__name__, now)
            raise
        ledger.record("analytics", "reports.query", bucket, units, 200, None, now)
        for item in rows_out:
            conn.execute(
                """INSERT OR REPLACE INTO analytics_daily (channel_id, day, content_type, views, estimated_minutes_watched,
                       average_view_duration, average_view_percentage, subscribers_gained, subscribers_lost, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (channel_id, item.get("day"), item.get("creatorContentType", "UNSPECIFIED"), item.get("views"),
                 item.get("estimatedMinutesWatched"), item.get("averageViewDuration"), item.get("averageViewPercentage"),
                 item.get("subscribersGained"), item.get("subscribersLost"), to_iso(now)),
            )
        conn.execute("UPDATE oauth_channels SET last_authorization_check_at = ? WHERE channel_id = ?", (to_iso(now), channel_id))
        conn.commit()
        synced[channel_id] = len(rows_out)
        _sync_search_terms(conn, ledger, access, channel_id, now, transport)
    return synced


def _sync_search_terms(conn: sqlite3.Connection, ledger: QuotaLedger, access: str, channel_id: str, now: datetime, transport=None, days: int = 28) -> int:
    """Relatório nunca testado com conta real: se o Google recusar, os dados diários já estão salvos."""
    ledger.check("reports.query", now)
    bucket, units = ledger.cost("reports.query")
    start, end = (now - timedelta(days=days)).date().isoformat(), now.date().isoformat()
    try:
        rows = youtube_analytics.fetch_top_search_terms(access, start, end, transport)
    except youtube_analytics.AnalyticsError as error:
        ledger.record("analytics", "reports.query", bucket, units, None, type(error).__name__, now)
        return 0
    ledger.record("analytics", "reports.query", bucket, units, 200, None, now)
    conn.execute("DELETE FROM own_search_terms WHERE channel_id = ?", (channel_id,))
    for item in rows:
        if not item.get("insightTrafficSourceDetail"):
            continue
        conn.execute(
            "INSERT OR REPLACE INTO own_search_terms (channel_id, term, views, minutes_watched, period_start, period_end, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (channel_id, item["insightTrafficSourceDetail"], item.get("views"), item.get("estimatedMinutesWatched"), start, end, to_iso(now)),
        )
    conn.commit()
    return len(rows)


def register_own_channel(client: YouTubeDataClient, conn: sqlite3.Connection, settings: Settings, store: oauth.TokenStore,
                         channel_reference: str, tokens: dict, now: datetime) -> str:
    channel_id = add_channel(client, conn, channel_reference, now, is_own=True)
    if not tokens.get("refresh_token"):
        raise oauth.OAuthError("O Google não devolveu refresh token. Revogue o acesso e autorize de novo.")
    store.set(channel_id, tokens["refresh_token"])
    conn.execute(
        "INSERT OR REPLACE INTO oauth_channels (channel_id, scopes, authorized_at, last_authorization_check_at) VALUES (?, ?, ?, ?)",
        (channel_id, " ".join(oauth.SCOPES), to_iso(now), to_iso(now)),
    )
    conn.commit()
    return channel_id


def revoke_own_channel(conn: sqlite3.Connection, store: oauth.TokenStore, channel_id: str, transport=None) -> None:
    """Revoga no Google, apaga o token e exclui os dados do canal."""
    refresh = store.get(channel_id)
    if refresh:
        oauth.revoke_token(refresh, transport)
        store.delete(channel_id)
    delete_channel_data(conn, channel_id)
