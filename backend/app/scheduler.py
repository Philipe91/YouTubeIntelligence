"""Tarefas periódicas. Só o modo live coleta; o modo demo não faz chamadas externas."""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta

from . import collector
from .config import Settings
from .connectors.oauth import KeyringTokenStore
from .connectors.quota import BudgetExceeded
from .connectors.youtube_data import QuotaExceeded, YouTubeDataClient
from .db import from_iso, to_iso
from .logging_safe import redact
from .policy import apply_retention

log = logging.getLogger("yti.scheduler")

DEFAULT_JOBS = {
    "snapshots": 60,
    "discover_videos": 720,
    "refresh_channels": 1440,
    "own_analytics": 1440,
    "retention": 1440,
}


def ensure_jobs(conn: sqlite3.Connection) -> None:
    for name, minutes in DEFAULT_JOBS.items():
        conn.execute("INSERT OR IGNORE INTO jobs (name, interval_minutes) VALUES (?, ?)", (name, minutes))
    conn.commit()


def build_runners(conn: sqlite3.Connection, settings: Settings, client: YouTubeDataClient | None) -> dict[str, Callable[[datetime], object]]:
    runners: dict[str, Callable[[datetime], object]] = {
        "retention": lambda now: apply_retention(conn, settings, now),
    }
    if client is not None:
        runners["snapshots"] = lambda now: collector.take_snapshots(client, conn, settings, now)
        runners["discover_videos"] = lambda now: collector.discover_monitored(client, conn, settings, now)
        runners["refresh_channels"] = lambda now: collector.refresh_channels(client, conn, now)
    if settings.oauth_client_secrets:
        runners["own_analytics"] = lambda now: collector.sync_own_analytics(conn, settings, KeyringTokenStore(), now)
    return runners


def run_due(conn: sqlite3.Connection, runners: dict[str, Callable[[datetime], object]], now: datetime) -> dict[str, str]:
    """Roda as tarefas vencidas. Uma falha é registrada e não impede as demais."""
    ensure_jobs(conn)
    results: dict[str, str] = {}
    for job in conn.execute("SELECT * FROM jobs WHERE enabled = 1 ORDER BY name").fetchall():
        name = job["name"]
        if name not in runners:
            results[name] = "sem_credencial"
            continue
        if job["last_run_at"] and now - from_iso(job["last_run_at"]) < timedelta(minutes=job["interval_minutes"]):
            results[name] = "aguardando"
            continue
        error = None
        try:
            runners[name](now)
            status = "ok"
        except (BudgetExceeded, QuotaExceeded) as exc:
            status, error = "sem_cota", redact(exc)
        except Exception as exc:  # noqa: BLE001 - uma tarefa não pode derrubar o agendador
            status, error = "erro", redact(exc)
            log.exception("Tarefa %s falhou", name)
        conn.execute(
            "UPDATE jobs SET last_run_at = ?, last_status = ?, last_error = ? WHERE name = ?",
            (to_iso(now), status, error, name),
        )
        conn.commit()
        results[name] = status
    return results
