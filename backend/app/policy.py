"""Trava de política da API do YouTube e regras de retenção.

Base: Developer Policies III.E.2, III.E.4 e III.L; Derived Metrics Policy.
Detalhes em docs/RELATORIO_EQUIVALENCIA.md.
"""
from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .config import ComplianceRecord, Settings
from .db import from_iso, to_iso

DEMO = "demo"
LIVE_RESTRICTED = "live_restricted"
LIVE_APPROVED = "live_approved"

BLOCK_REASON = (
    "Bloqueado: a política da API do YouTube (III.E.4.h e III.L) não permite métricas derivadas "
    "de dados da API sem auditoria e aprovação do Google. Veja Sistema e cotas."
)
ORIGIN_NOTE = "Calculado por este aplicativo. Não é um dado publicado pelo YouTube."
SCOPE_DERIVED = "derived_metrics"
SCOPE_STORAGE = "extended_storage"


class PolicyBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyState:
    state: str
    derived_allowed: bool
    stats_retention: str
    text_retention_days: int
    description: str
    extended_storage: bool = False
    problems: tuple[str, ...] = ()


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def compliance_problems(record: ComplianceRecord, today: date) -> list[str]:
    """Lista o que impede a liberação. Lista vazia significa registro completo e em vigor."""
    if record.load_error:
        return [f"O arquivo de conformidade não pôde ser lido ({record.load_error})."]
    problems: list[str] = []
    if record.status != "approved":
        problems.append(f"Status atual: {record.status}. É preciso estar 'approved'.")
    if record.use_case != "analytics_reporting":
        problems.append("Caso de uso precisa ser 'analytics_reporting'.")
    if not record.amendment_accepted:
        problems.append("Emenda às políticas não aceita.")
    if not record.compliance_audit_passed:
        problems.append("Auditoria de conformidade não concluída.")
    if not record.google_case_ref:
        problems.append("Falta a referência do caso no Google.")
    if not record.declared_by:
        problems.append("Falta quem declarou o registro.")
    approved_on = _parse_day(record.approved_on)
    if approved_on is None:
        problems.append("Data de aprovação ausente ou inválida.")
    elif approved_on > today:
        problems.append("A data de aprovação está no futuro.")
    review_by = _parse_day(record.review_by)
    if review_by is None:
        problems.append("Data de revisão ausente ou inválida.")
    elif review_by < today:
        problems.append("A data de revisão venceu.")
    return problems


def policy_state(settings: Settings, today: date | None = None) -> PolicyState:
    retention = settings.scoring["retention"]
    if settings.mode == "demo":
        return PolicyState(DEMO, True, "sem limite (dados fictícios)", retention["text_days"],
                           "Dados fictícios. Nenhum dado do YouTube é usado.")
    record = settings.compliance
    problems = compliance_problems(record, today or datetime.now(UTC).date())
    derived = not problems and SCOPE_DERIVED in record.approved_scopes
    storage = not problems and SCOPE_STORAGE in record.approved_scopes
    if not problems and not derived:
        problems = ["O escopo 'derived_metrics' não foi aprovado."]
    stats = f"{retention['approved_stats_months']} meses" if storage else f"{retention['restricted_days']} dias"
    if derived:
        return PolicyState(LIVE_APPROVED, True, stats, retention["text_days"],
                           "Aprovação declarada no registro de conformidade. O aplicativo não consegue confirmá-la com o Google.",
                           extended_storage=storage)
    return PolicyState(LIVE_RESTRICTED, False, stats, retention["text_days"],
                       "Só dados crus. Métricas derivadas bloqueadas até auditoria e aprovação do Google.",
                       extended_storage=storage, problems=tuple(problems))


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
    if policy_state(settings, now.date()).extended_storage:
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
