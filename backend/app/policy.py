"""Trava de política da API do YouTube e regras de retenção.

Base: Developer Policies III.E.2, III.E.4 e III.L; Derived Metrics Policy.
Detalhes em docs/RELATORIO_EQUIVALENCIA.md.
"""
from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import Settings
from .db import from_iso, to_iso

DEMO = "demo"
LIVE_RESTRICTED = "live_restricted"
LIVE_APPROVED = "live_approved"

BLOCK_REASON = (
    "Bloqueado: a política da API do YouTube (III.E.4.h) não permite métricas derivadas "
    "de dados da API sem aceite do uso analítico. Veja Sistema > Política."
)
ORIGIN_NOTE = "Calculado por este aplicativo. Não é um dado publicado pelo YouTube."


class PolicyBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyState:
    state: str
    derived_allowed: bool
    stats_retention: str
    text_retention_days: int
    description: str


def policy_state(settings: Settings) -> PolicyState:
    retention = settings.scoring["retention"]
    if settings.mode == "demo":
        return PolicyState(DEMO, True, "sem limite (dados fictícios)", retention["text_days"],
                           "Dados fictícios. Nenhum dado do YouTube é usado.")
    if settings.approval_ref:
        return PolicyState(LIVE_APPROVED, True, f"{retention['approved_stats_months']} meses",
                           retention["text_days"],
                           "Aprovação declarada por você; o aplicativo não consegue verificá-la.")
    return PolicyState(LIVE_RESTRICTED, False, f"{retention['restricted_days']} dias",
                       retention["text_days"],
                       "Só dados crus. Métricas derivadas bloqueadas até o aceite do uso analítico.")


def require_derived(settings: Settings) -> None:
    if not policy_state(settings).derived_allowed:
        raise PolicyBlocked(BLOCK_REASON)


def _months_ago(now: datetime, months: int) -> datetime:
    year = now.year
    month = now.month - months
    while month <= 0:
        month += 12
        year -= 1
    return now.replace(year=year, month=month, day=min(now.day, calendar.monthrange(year, month)[1]))


def apply_retention(conn: sqlite3.Connection, settings: Settings, now: datetime) -> dict[str, int]:
    """Apaga o que passou do prazo. Sem efeito no modo demo."""
    removed = {"snapshots": 0, "channel_snapshots": 0, "videos": 0, "channels": 0, "cache": 0}
    removed["cache"] = conn.execute(
        "DELETE FROM api_cache WHERE expires_at < ?", (to_iso(now),)
    ).rowcount
    if settings.mode == "demo":
        conn.commit()
        return removed

    retention = settings.scoring["retention"]
    if policy_state(settings).state == LIVE_APPROVED:
        stats_cutoff = _months_ago(now, retention["approved_stats_months"])
    else:
        stats_cutoff = now - timedelta(days=retention["restricted_days"])
    text_cutoff = to_iso(now - timedelta(days=retention["text_days"]))

    # Canais próprios autorizados têm estatísticas sob as regras de dados autorizados.
    third_party = "SELECT v.id FROM videos v JOIN channels c ON c.id = v.channel_id WHERE c.is_own = 0"
    removed["snapshots"] = conn.execute(
        f"DELETE FROM snapshots WHERE captured_at < ? AND video_id IN ({third_party})",
        (to_iso(stats_cutoff),),
    ).rowcount
    removed["channel_snapshots"] = conn.execute(
        "DELETE FROM channel_snapshots WHERE captured_at < ? AND channel_id IN "
        "(SELECT id FROM channels WHERE is_own = 0)",
        (to_iso(stats_cutoff),),
    ).rowcount
    # Texto não atualizado no prazo é apagado, inclusive o de canais próprios.
    removed["videos"] = conn.execute(
        "DELETE FROM videos WHERE text_refreshed_at < ?", (text_cutoff,)
    ).rowcount
    removed["channels"] = conn.execute(
        "DELETE FROM channels WHERE text_refreshed_at < ?", (text_cutoff,)
    ).rowcount
    conn.commit()
    return removed


def authorizations_due(conn: sqlite3.Connection, settings: Settings, now: datetime) -> list[str]:
    """Canais próprios cuja autorização precisa ser reconferida (a cada 30 dias)."""
    days = settings.scoring["retention"]["authorization_check_days"]
    return [
        row["channel_id"]
        for row in conn.execute("SELECT channel_id, last_authorization_check_at FROM oauth_channels")
        if now - from_iso(row["last_authorization_check_at"]) >= timedelta(days=days)
    ]


def delete_channel_data(conn: sqlite3.Connection, channel_id: str) -> None:
    """Exclui canal, vídeos, snapshots e analytics em cascata."""
    conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
