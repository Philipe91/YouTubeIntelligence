"""Dados explicitamente fictícios para o modo demonstração.

Canais, vídeos e números são inventados. Nada aqui representa um canal real.
Com a mesma semente e a mesma data, o resultado é o mesmo.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import datetime, timedelta

from .db import to_iso

SEED = 20261103
FICTION = "(fictício)"
TOPICS = [
    "Roma antiga", "queda de Cartago", "peste negra", "Império Mongol", "Revolução Francesa", "faraós do Egito",
    "cruzadas", "vikings", "samurais", "Grande Navegação", "Guerra dos Cem Anos", "Império Asteca",
    "rota da seda", "Grécia clássica", "Império Otomano", "Brasil Colônia",
]
RISING_TOPICS = {"queda de Cartago", "rota da seda", "Império Asteca"}
TEMPLATES = [
    "A verdade sobre {t}", "{t} em 5 minutos", "Por que {t} mudou tudo?", "O dia em que {t} surpreendeu o mundo",
    "{t} explicado com animação", "O que ninguém conta sobre {t}", "3 mitos sobre {t}", "Como era viver em {t}?",
]
CHANNELS = [
    ("Crônicas de Papel", 420_000, 9000, 26000, "pt", "BR", False),
    ("Atlas Animado", 1_250_000, 30000, 90000, "pt", "BR", False),
    ("Tinta e Império", 88_000, 2500, 9000, "pt", "BR", False),
    ("Era em Traços", 32_000, 900, 5000, "pt", "PT", False),
    ("Historieta Viva", None, 6000, 20000, "es", "MX", False),
    ("Pergamino Animado", 610_000, 14000, 50000, "es", "ES", False),
    ("Paper Empires", 2_100_000, 60000, 180000, "en", "US", False),
    ("Canal Novo em Teste", 4_000, 200, 1200, "pt", "BR", False),
    ("Meu Canal Demo", 15_000, 700, 3500, "pt", "BR", True),
]
QUERIES = [
    ("história animada roma", "pt", "BR"),
    ("queda de cartago animação", "pt", "BR"),
    ("rota da seda história", "pt", "BR"),
    ("império asteca animado", "pt", "BR"),
    ("peste negra explicada", "pt", "BR"),
    ("vikings história animada", "pt", "BR"),
    ("samurais história", "pt", "BR"),
    ("tema raro de nicho", "pt", "BR"),
    ("historia animada imperio azteca", "es", "MX"),
]


def _growth(age_hours: float, tau_hours: float) -> float:
    return 1 - math.exp(-max(age_hours, 0) / tau_hours)


def _capture_times(published: datetime, monitor_start: datetime, now: datetime) -> list[datetime]:
    """Cadência decrescente, como o coletor real. Só existe medição depois do início do monitoramento."""
    times = []
    moment = max(published + timedelta(hours=1), monitor_start)
    while moment <= now:
        times.append(moment)
        age = (moment - published).total_seconds() / 3600
        moment += timedelta(hours=1 if age < 48 else 6 if age < 168 else 24)
    if not times or times[-1] != now:
        times.append(now)
    return times


def seed_demo(conn: sqlite3.Connection, now: datetime) -> None:
    now = now.replace(minute=0, second=0, microsecond=0)
    rng = random.Random(SEED)
    stamp = to_iso(now)
    monitor_start = now - timedelta(days=45)

    niche_pt = conn.execute(
        "INSERT INTO niches (name, keywords_json, language, country, created_at) VALUES (?, ?, ?, ?, ?)",
        ("História animada", json.dumps(["história", "animação", "animada", "roma", "cartago", "império", "rota", "seda", "peste", "vikings", "samurais", "asteca"], ensure_ascii=False), "pt", "BR", stamp),
    ).lastrowid
    niche_es = conn.execute(
        "INSERT INTO niches (name, keywords_json, language, country, created_at) VALUES (?, ?, ?, ?, ?)",
        ("Historia animada (ES)", json.dumps(["historia", "animada", "imperio", "azteca"]), "es", "MX", stamp),
    ).lastrowid

    video_rows: list[tuple] = []
    snapshot_rows: list[tuple] = []
    by_language: dict[str, list[tuple[str, str]]] = {}
    for index, (name, subs, base_short, base_long, language, country, is_own) in enumerate(CHANNELS):
        channel_id = f"DEMO_UC{index:02d}"
        conn.execute(
            "INSERT INTO channels (id, title, handle, description, country, default_language, uploads_playlist_id, is_own, "
            "monitored, niche_id, text_refreshed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (channel_id, f"{name} {FICTION}", f"@demo{index}", "Canal inventado para o modo demonstração.", country, language,
             f"DEMO_UU{index:02d}", int(is_own), 1, niche_es if language == "es" else niche_pt, stamp, stamp),
        )
        for day in range(0, 46, 5):
            moment = now - timedelta(days=45 - day)
            conn.execute(
                "INSERT INTO channel_snapshots (channel_id, captured_at, subscriber_count, view_count, video_count) VALUES (?, ?, ?, ?, ?)",
                (channel_id, to_iso(moment), None if subs is None else int(subs * (0.97 + 0.03 * day / 45)), None, None),
            )
        # O canal novo tem poucos vídeos, para mostrar o aviso de amostra insuficiente.
        counts = {"short": 3, "long": 2} if name == "Canal Novo em Teste" else {"short": 26, "long": 18}
        for video_format, count in counts.items():
            base = base_short if video_format == "short" else base_long
            for number in range(count):
                age_days = rng.uniform(0.3, 28) if number < count * 0.55 else rng.uniform(28, 170)
                published = now - timedelta(days=age_days)
                topic = rng.choice(TOPICS)
                title = rng.choice(TEMPLATES).format(t=topic)
                video_id = f"DEMO_V{index:02d}{video_format[0]}{number:03d}"
                factor = math.exp(rng.gauss(0, 0.45))
                if rng.random() < 0.07:
                    factor *= rng.uniform(4, 11)  # outliers plantados
                tau = 40.0 if video_format == "short" else 110.0
                final = base * factor
                # Tópicos em alta recebem impulso só nas últimas 24 h em vídeos menos recentes.
                rising = topic in RISING_TOPICS and age_days > 3 and rng.random() < 0.8
                duration = rng.randint(25, 175) if video_format == "short" else rng.randint(360, 1500)
                video_rows.append((video_id, channel_id, title, f"Descrição fictícia sobre {topic}.", to_iso(published), duration,
                                   video_format, "fictional", language, country,
                                   stamp, to_iso(published + timedelta(hours=1))))
                by_language.setdefault(language, []).append((video_id, topic))
                for captured in _capture_times(published, monitor_start, now):
                    age = (captured - published).total_seconds() / 3600
                    views = final * _growth(age, tau) * (1 + 0.0012 * max(age - tau, 0) ** 0.8 / 10)
                    hours_ago = (now - captured).total_seconds() / 3600
                    if rising and hours_ago < 24:
                        views += final * 0.09 * (24 - hours_ago) / 24
                    snapshot_rows.append((video_id, to_iso(captured), int(views), int(views * 0.04), int(views * 0.004)))

    conn.executemany(
        "INSERT INTO videos (id, channel_id, title, description, published_at, duration_seconds, format, format_source, "
        "language, country, text_refreshed_at, first_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", video_rows)
    conn.executemany(
        "INSERT INTO snapshots (video_id, captured_at, view_count, like_count, comment_count) VALUES (?, ?, ?, ?, ?)", snapshot_rows)

    for query, language, country in QUERIES:
        words = set(query.lower().replace("história", "").replace("historia", "").split())
        pool = by_language.get(language, [])
        matched = [vid for vid, topic in pool if words & set(topic.lower().split())]
        if query == "tema raro de nicho":
            matched = [vid for vid, _ in pool][:4]  # amostra pequena de propósito
        cursor = conn.execute(
            "INSERT INTO searches (query, niche_id, language, country, sort_order, total_results_approx, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (query, niche_es if language == "es" else niche_pt, language, country, "relevance", rng.randint(800, 400000), stamp),
        )
        conn.executemany(
            "INSERT INTO search_results (search_id, video_id, rank) VALUES (?, ?, ?)",
            [(cursor.lastrowid, vid, rank + 1) for rank, vid in enumerate(matched[:50])],
        )

    own_id = f"DEMO_UC{len(CHANNELS) - 1:02d}"
    for offset in range(90):
        day = (now - timedelta(days=offset + 1)).date().isoformat()
        trend = 1 + (90 - offset) / 120
        for content_type, base_views, percent, duration in (("SHORTS", 2600, 71.0, 38.0), ("VIDEO_ON_DEMAND", 900, 38.0, 310.0)):
            views = int(base_views * trend * rng.uniform(0.7, 1.3))
            conn.execute(
                "INSERT INTO analytics_daily (channel_id, day, content_type, views, estimated_minutes_watched, average_view_duration, "
                "average_view_percentage, subscribers_gained, subscribers_lost, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (own_id, day, content_type, views, int(views * duration / 60), duration, percent + rng.uniform(-4, 4),
                 int(views / 180), int(views / 900), stamp),
            )
    conn.commit()


def is_seeded(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) AS n FROM channels").fetchone()["n"] > 0


def reset_demo(conn: sqlite3.Connection, now: datetime) -> None:
    for table in ("ai_generations", "search_results", "searches", "analytics_daily", "snapshots", "videos",
                  "channel_snapshots", "channels", "niches"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    seed_demo(conn, now)
