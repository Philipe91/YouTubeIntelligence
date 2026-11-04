"""Pesquisas agendadas por canal: persistentes, econômicas e desligadas com dados reais até o dono aprovar.

Nada aqui roda sozinho: uma rodada só acontece pelo botão do painel ou pelo comando `research-tick`, que precisa
ser iniciado à mão. Com dados reais, a rodada exige chave, consulta real confirmada e limites aprovados, e para sozinha
diante de falta de cota ou de problema na chave. O modo demonstração só toca nos dados fictícios, sem internet.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta

from ..config import Settings
from ..connectors.quota import PACIFIC, QuotaLedger, quota_day
from ..db import from_iso, to_iso
from ..logging_safe import redact
from ..metrics.text import normalize
from ..studio.store import StudioError, new_id
from . import research
from .api_status import real_validation_exists
from .common import ClientFactory, default_client, loads, require_channel

INTERVALS = {24: "Todo dia", 72: "A cada 3 dias", 168: "Toda semana", 720: "Todo mês"}
MAX_PER_CHANNEL = 10
MAX_SEARCHES_APPROVABLE = 20
MAX_RUNS_PER_TICK = 5
DUPLICATE_WINDOW_HOURS = 6  # O mesmo prazo do cache de search.list.
MAX_CONSECUTIVE_ERRORS = 3
FILTER_KEYS = ("language", "country", "days", "format", "order", "max_subscribers", "niche", "subniche", "discovery")
QUOTA_CODES = {"quota_local", "quota_google"}
CREDENTIAL_CODES = {"api_credential", "api_key_missing"}
INDEFINITE = "9999-12-31T00:00:00Z"


def _settings_row(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute("SELECT * FROM automation_settings WHERE id = 1").fetchone()


def _signature(kind: str, query: str, filters: dict) -> str:
    clean = {key: filters.get(key) for key in FILTER_KEYS if filters.get(key) not in (None, "", False)}
    return hashlib.sha256(json.dumps([kind, normalize(" ".join(query.split())), clean], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]


def _next_quota_day(now: datetime) -> datetime:
    local = now.astimezone(PACIFIC)
    return (local + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)


def _automated_today(conn: sqlite3.Connection, now: datetime) -> int:
    """Conta só o que chamou a busca de verdade. Resposta do cache e item duplicado não gastam cota."""
    day = quota_day(now)
    since = to_iso(now - timedelta(hours=26))
    rows = conn.execute("SELECT e.at FROM schedule_events e WHERE e.status = 'ok_api' AND e.at >= ?", (since,)).fetchall()
    return sum(1 for row in rows if quota_day(from_iso(row["at"])) == day)


def gate(conn: sqlite3.Connection, settings: Settings, now: datetime) -> dict:
    """Pode rodar agora? Sempre diz o motivo, para a tela mostrar o que falta."""
    row = _settings_row(conn)
    base = {"mode": settings.mode, "real_enabled": bool(row["real_enabled"]), "max_searches_per_day": row["max_searches_per_day"], "approved_at": row["approved_at"], "approved_by": row["approved_by"],
            "paused_until": None if row["paused_until"] == INDEFINITE else row["paused_until"], "paused_reason": row["paused_reason"], "used_today": _automated_today(conn, now), "target": settings.api_target}
    if settings.mode == "demo":
        return {**base, "can_run": True, "state": "demo", "reason": "Modo demonstração: as rodadas só tocam nos dados fictícios, sem internet e sem cota."}
    if not settings.youtube_api_key:
        return {**base, "can_run": False, "state": "sem_chave", "reason": "Falta configurar YOUTUBE_API_KEY. Veja Sistema e cotas."}
    if settings.api_target == "google" and not real_validation_exists(conn):
        return {**base, "can_run": False, "state": "sem_validacao", "reason": "Falta uma consulta real confirmada. Use Testar conexão em Sistema e cotas."}
    if not row["real_enabled"]:
        return {**base, "can_run": False, "state": "aguardando_aprovacao", "reason": "Desligado até você aprovar os limites."}
    if row["paused_until"] and row["paused_until"] > to_iso(now):
        return {**base, "can_run": False, "state": "pausado", "reason": row["paused_reason"] or "Pausado."}
    if base["used_today"] >= row["max_searches_per_day"]:
        return {**base, "can_run": False, "state": "limite_do_dia", "reason": f"O limite aprovado de {row['max_searches_per_day']} buscas automáticas por dia foi atingido."}
    return {**base, "can_run": True, "state": "ligado", "reason": "Ligado, dentro dos limites aprovados."}


def approve(conn: sqlite3.Connection, settings: Settings, max_searches_per_day: int, now: datetime, approved_by: str = "dono_local") -> dict:
    """Só o dono aprova: esta função não é exposta ao agente."""
    if settings.mode == "demo":
        raise StudioError("not_needed_in_demo", "No modo demonstração, não há limites a aprovar: nada usa a internet.", 409)
    if not settings.youtube_api_key:
        raise StudioError("api_key_missing", "Configure YOUTUBE_API_KEY antes de aprovar. Os passos estão em Sistema e cotas.", 424)
    if settings.api_target == "google" and not real_validation_exists(conn):
        raise StudioError("validation_missing", "Confirme uma consulta real em Sistema e cotas antes de aprovar.", 409)
    bucket_limit = QuotaLedger(conn, settings).limits["search"]
    ceiling = min(MAX_SEARCHES_APPROVABLE, bucket_limit)
    if not 1 <= max_searches_per_day <= ceiling:
        raise StudioError("invalid_field", f"Escolha de 1 a {ceiling} buscas automáticas por dia.")
    conn.execute("UPDATE automation_settings SET real_enabled = 1, max_searches_per_day = ?, approved_at = ?, approved_by = ?, paused_until = NULL, paused_reason = NULL WHERE id = 1",
                 (max_searches_per_day, to_iso(now), approved_by))
    conn.commit()
    return gate(conn, settings, now)


def revoke(conn: sqlite3.Connection, settings: Settings, now: datetime) -> dict:
    conn.execute("UPDATE automation_settings SET real_enabled = 0, max_searches_per_day = 0, paused_until = NULL, paused_reason = NULL WHERE id = 1")
    conn.commit()
    return gate(conn, settings, now)


def resume(conn: sqlite3.Connection, settings: Settings, now: datetime) -> dict:
    conn.execute("UPDATE automation_settings SET paused_until = NULL, paused_reason = NULL WHERE id = 1")
    conn.commit()
    return gate(conn, settings, now)


def _pause_all(conn: sqlite3.Connection, until: str, reason: str) -> None:
    conn.execute("UPDATE automation_settings SET paused_until = ?, paused_reason = ? WHERE id = 1", (until, reason))


def _view(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["filters"] = loads(data.pop("filters_json"), {})
    data["enabled"] = bool(data["enabled"])
    data["interval_label"] = INTERVALS.get(data["interval_hours"], f"A cada {data['interval_hours']} horas")
    data["kind_label"] = research.KINDS[data["kind"]]
    data.pop("signature")
    return data


def _load(conn: sqlite3.Connection, channel_id: str, schedule_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM research_schedules WHERE id = ? AND managed_channel_id = ?", (schedule_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("schedule_not_found", "Agendamento não encontrado neste canal.", 404)
    return row


def create(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, *, kind: str, query: str, filters: dict | None, interval_hours: int, now: datetime) -> dict:
    require_channel(studio, settings, channel_id)
    if kind not in research.KINDS:
        raise StudioError("invalid_field", "Tipo de pesquisa desconhecido.")
    if interval_hours not in INTERVALS:
        raise StudioError("invalid_field", "Periodicidade inválida. Use uma das opções da tela.")
    text = research._clean_query(query)
    given = filters or {}
    # A mesma validação da pesquisa manual, antes de guardar.
    clean = research._filters(kind, given.get("language"), given.get("country"), given.get("days"), given.get("format"), given.get("order") or "relevance", given.get("max_subscribers"))
    clean.update({key: given[key] for key in ("niche", "subniche", "discovery") if given.get(key)})
    if conn.execute("SELECT COUNT(*) AS n FROM research_schedules WHERE managed_channel_id = ?", (channel_id,)).fetchone()["n"] >= MAX_PER_CHANNEL:
        raise StudioError("too_many_schedules", f"Cada canal pode ter até {MAX_PER_CHANNEL} agendamentos.", 409)
    signature = _signature(kind, text, clean)
    if conn.execute("SELECT 1 FROM research_schedules WHERE managed_channel_id = ? AND signature = ?", (channel_id, signature)).fetchone():
        raise StudioError("duplicate_schedule", "Esta pesquisa já está agendada neste canal.", 409)
    identifier = new_id("sch")
    conn.execute("""INSERT INTO research_schedules (id, managed_channel_id, signature, kind, query, filters_json, interval_hours, next_run_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (identifier, channel_id, signature, kind, text, json.dumps(clean, ensure_ascii=False), interval_hours, to_iso(now), to_iso(now), to_iso(now)))
    conn.commit()
    return _view(_load(conn, channel_id, identifier))


def create_from_run(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, run_id: str, interval_hours: int, now: datetime) -> dict:
    run = research.get_run(conn, run_id, channel_id)
    return create(conn, studio, settings, channel_id, kind=run["kind"], query=run["query"], filters=run["filters"], interval_hours=interval_hours, now=now)


def update(conn: sqlite3.Connection, channel_id: str, schedule_id: str, *, enabled: bool | None, interval_hours: int | None, now: datetime) -> dict:
    row = _load(conn, channel_id, schedule_id)
    if interval_hours is not None:
        if interval_hours not in INTERVALS:
            raise StudioError("invalid_field", "Periodicidade inválida.")
        conn.execute("UPDATE research_schedules SET interval_hours = ?, updated_at = ? WHERE id = ?", (interval_hours, to_iso(now), schedule_id))
    if enabled is not None:
        # Retomar zera os erros e pede uma rodada nova, se o prazo já tiver passado.
        conn.execute("UPDATE research_schedules SET enabled = ?, paused_reason = CASE WHEN ? = 1 THEN NULL ELSE 'Pausado por você.' END, consecutive_errors = CASE WHEN ? = 1 THEN 0 ELSE consecutive_errors END, updated_at = ? WHERE id = ?",
                     (int(enabled), int(enabled), int(enabled), to_iso(now), row["id"]))
    conn.commit()
    return _view(_load(conn, channel_id, schedule_id))


def delete(conn: sqlite3.Connection, channel_id: str, schedule_id: str) -> None:
    _load(conn, channel_id, schedule_id)
    conn.execute("DELETE FROM research_schedules WHERE id = ?", (schedule_id,))
    conn.commit()


def _event(conn: sqlite3.Connection, schedule_id: str, now: datetime, status: str, run_id: str | None = None, message: str = "") -> None:
    conn.execute("INSERT INTO schedule_events (schedule_id, at, status, run_id, message) VALUES (?, ?, ?, ?, ?)", (schedule_id, to_iso(now), status, run_id, redact(message)[:500]))


def _recent_duplicate(conn: sqlite3.Connection, row: sqlite3.Row, now: datetime) -> str | None:
    """A mesma pesquisa, feita à mão ou por outro agendamento do canal, há pouco tempo."""
    since = to_iso(now - timedelta(hours=DUPLICATE_WINDOW_HOURS))
    for candidate in conn.execute("SELECT id, kind, query, filters_json FROM research_runs WHERE managed_channel_id = ? AND executed_at >= ? ORDER BY executed_at DESC", (row["managed_channel_id"], since)):
        if _signature(candidate["kind"], candidate["query"], loads(candidate["filters_json"], {})) == row["signature"]:
            return candidate["id"]
    return None


def tick(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, now: datetime, factory: ClientFactory = default_client) -> dict:
    """Roda o que venceu, até os limites. Falha numa pesquisa não derruba as outras, e falta de cota para tudo."""
    state = gate(conn, settings, now)
    summary = {"ran": 0, "cached": 0, "duplicates": 0, "errors": 0, "paused": False, "state": state["state"], "reason": state["reason"]}
    if not state["can_run"]:
        return summary
    budget = MAX_RUNS_PER_TICK if settings.mode == "demo" else min(MAX_RUNS_PER_TICK, state["max_searches_per_day"] - state["used_today"])
    due = conn.execute("SELECT * FROM research_schedules WHERE enabled = 1 AND next_run_at <= ? ORDER BY next_run_at, id", (to_iso(now),)).fetchall()
    for row in due:
        if budget <= 0:
            break
        next_run = to_iso(now + timedelta(hours=row["interval_hours"]))
        duplicate = _recent_duplicate(conn, row, now)
        if duplicate:
            _event(conn, row["id"], now, "duplicada", duplicate, "A mesma pesquisa foi feita há pouco. Nada foi chamado.")
            conn.execute("UPDATE research_schedules SET next_run_at = ?, last_run_at = ?, last_status = 'duplicada', last_error = NULL, updated_at = ? WHERE id = ?", (next_run, to_iso(now), to_iso(now), row["id"]))
            conn.commit()
            summary["duplicates"] += 1
            continue
        filters = loads(row["filters_json"], {})
        try:
            created = research.run_search(conn, studio, settings, kind=row["kind"], query=row["query"], channel_id=row["managed_channel_id"], now=now, language=filters.get("language"), country=filters.get("country"),
                                          days=filters.get("days"), video_format=filters.get("format"), order=filters.get("order") or "relevance", max_subscribers=filters.get("max_subscribers"), factory=factory,
                                          tags={key: filters[key] for key in ("niche", "subniche", "discovery") if key in filters} or None, schedule_id=row["id"])
        except StudioError as error:
            summary["errors"] += 1
            message = error.message
            if error.code in QUOTA_CODES:
                until = _next_quota_day(now)
                _pause_all(conn, to_iso(until), f"Pausado por falta de cota até {to_iso(until)}, a virada do dia de cota. Volta sozinho.")
                _event(conn, row["id"], now, "sem_cota", None, message)
                conn.execute("UPDATE research_schedules SET last_run_at = ?, last_status = 'sem_cota', last_error = ?, updated_at = ? WHERE id = ?", (to_iso(now), redact(message)[:500], to_iso(now), row["id"]))
                conn.commit()
                summary["paused"] = True
                break
            if error.code in CREDENTIAL_CODES:
                _pause_all(conn, INDEFINITE, f"Pausado por problema na chave: {message} Corrija e clique em Retomar.")
                _event(conn, row["id"], now, "erro_chave", None, message)
                conn.execute("UPDATE research_schedules SET last_run_at = ?, last_status = 'erro_chave', last_error = ?, updated_at = ? WHERE id = ?", (to_iso(now), redact(message)[:500], to_iso(now), row["id"]))
                conn.commit()
                summary["paused"] = True
                break
            failures = row["consecutive_errors"] + 1
            stop = failures >= MAX_CONSECUTIVE_ERRORS or not error.retryable
            reason = (f"Pausado depois de {failures} falhas seguidas." if failures >= MAX_CONSECUTIVE_ERRORS else "Pausado: este erro não se resolve sozinho.") if stop else None
            _event(conn, row["id"], now, "erro", None, message)
            conn.execute("UPDATE research_schedules SET enabled = ?, paused_reason = ?, consecutive_errors = ?, next_run_at = ?, last_run_at = ?, last_status = 'erro', last_error = ?, updated_at = ? WHERE id = ?",
                         (0 if stop else 1, reason, failures, next_run, to_iso(now), redact(message)[:500], to_iso(now), row["id"]))
            conn.commit()
            continue
        api_calls = created["provenance"].get("api_calls", 0)
        used_search = bool(created["provenance"].get("search_api_calls"))
        status = "ok_api" if used_search else "ok_cache"
        _event(conn, row["id"], now, status, created["id"], f"{created['result_count']} resultados. {api_calls} chamadas novas.")
        conn.execute("UPDATE research_schedules SET next_run_at = ?, last_run_at = ?, last_status = ?, last_error = NULL, consecutive_errors = 0, updated_at = ? WHERE id = ?", (next_run, to_iso(now), status, to_iso(now), row["id"]))
        conn.commit()
        if used_search:
            summary["ran"] += 1
            budget -= 1
        elif settings.mode == "demo":
            summary["ran"] += 1
            budget -= 1
        else:
            summary["cached"] += 1
    return summary


def overview(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, now: datetime, channel_id: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    where, params = ("WHERE s.managed_channel_id = ?", [channel_id]) if channel_id else ("", [])
    schedules = [_view(row) for row in conn.execute(f"SELECT s.* FROM research_schedules s {where} ORDER BY s.next_run_at, s.id", params)]
    total = conn.execute(f"SELECT COUNT(*) AS n FROM schedule_events e JOIN research_schedules s ON s.id = e.schedule_id {where}", params).fetchone()["n"]
    events = [dict(row) for row in conn.execute(
        f"SELECT e.*, s.query, s.managed_channel_id FROM schedule_events e JOIN research_schedules s ON s.id = e.schedule_id {where} ORDER BY e.at DESC, e.id DESC LIMIT ? OFFSET ?", (*params, limit, offset))]
    ledger = QuotaLedger(conn, settings)
    return {
        "gate": gate(conn, settings, now), "schedules": schedules, "events": {"total": total, "limit": limit, "offset": offset, "items": events},
        "intervals": [{"hours": hours, "label": label} for hours, label in INTERVALS.items()], "due_now": sum(1 for item in schedules if item["enabled"] and item["next_run_at"] <= to_iso(now)),
        "quota": {"search_used": ledger.used("search", now), "search_limit": ledger.limits["search"], "quota_day": quota_day(now)}, "max_approvable": min(MAX_SEARCHES_APPROVABLE, ledger.limits["search"]),
        "max_per_channel": MAX_PER_CHANNEL,
    }
