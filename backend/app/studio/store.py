"""Cadastros do estúdio. Toda consulta é limitada a um canal: um canal não enxerga dados de outro."""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db import connect, migrate, to_iso, utcnow

MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "migrations_studio"
JSON_LIST_FIELDS = {"keywords": "keywords_json", "avoid": "avoid_json", "topic_backlog": "topic_backlog_json", "formats": "formats_json"}
TEXT_FIELDS = ("name", "handle", "youtube_channel_id", "niche", "language", "country", "audience", "positioning", "tone", "pipeline_profile")
NUMBER_FIELDS = ("long_target_seconds", "short_target_seconds", "cadence_per_week")
AUTOMATION_FIELDS = {"auto_research": ("off", "on"), "auto_briefing": ("off", "on"),
                     "auto_production": ("off", "manual", "auto_simulated"), "auto_package": ("off", "on")}
YOUTUBE_ID = re.compile(r"^UC[0-9A-Za-z_-]{22}$")
ACTIVE_STATES = ("awaiting_authorization", "authorized", "running")


class StudioError(Exception):
    """Erro previsto, com código estável para a interface e para os agentes."""

    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable = code, message, status, retryable


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def open_studio(settings: Settings) -> sqlite3.Connection:
    conn = connect(settings.studio_db_path)
    migrate(conn, MIGRATIONS)
    return conn


def _channel_view(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for public, column in JSON_LIST_FIELDS.items():
        data[public] = json.loads(data.pop(column))
    data["is_demo"] = bool(data["is_demo"])
    data["automation"] = {key: data.pop(key) for key in AUTOMATION_FIELDS}
    data["automation"]["publishing"] = "desativada"
    return data


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise StudioError("invalid_field", "Esperava uma lista de textos.")
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen[text] = None
    return list(seen)


def _validate(fields: dict[str, Any]) -> dict[str, Any]:
    columns: dict[str, Any] = {}
    for key, value in fields.items():
        if key in TEXT_FIELDS:
            columns[key] = value.strip() if isinstance(value, str) else value
        elif key in NUMBER_FIELDS:
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                raise StudioError("invalid_field", f"{key} precisa ser um número positivo.")
            columns[key] = value
        elif key in JSON_LIST_FIELDS:
            items = _clean_list(value)
            if key == "formats" and (not items or set(items) - {"short", "long"}):
                raise StudioError("invalid_field", "Formatos válidos: short e long.")
            columns[JSON_LIST_FIELDS[key]] = json.dumps(items, ensure_ascii=False)
        elif key in AUTOMATION_FIELDS:
            if value not in AUTOMATION_FIELDS[key]:
                raise StudioError("invalid_field", f"Valor inválido para {key}.")
            columns[key] = value
        else:
            raise StudioError("unknown_field", f"Campo não reconhecido: {key}.")
    if "name" in columns and not columns["name"]:
        raise StudioError("invalid_field", "Informe o nome do canal.")
    if "pipeline_profile" in columns:
        from .pipelines import load_profiles  # Evita ciclo: pipelines usa StudioError deste módulo.

        if columns["pipeline_profile"] not in load_profiles():
            raise StudioError("invalid_field", "Perfil de pipeline desconhecido.")
    if columns.get("youtube_channel_id") == "":
        columns["youtube_channel_id"] = None
    if columns.get("youtube_channel_id") and not YOUTUBE_ID.match(columns["youtube_channel_id"]):
        raise StudioError("invalid_field", "O ID do canal do YouTube começa com UC e tem 24 caracteres.")
    if "language" in columns and not re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2,4})?", columns["language"] or ""):
        raise StudioError("invalid_field", "Idioma no formato pt, es, en.")
    return columns


def create_channel(conn: sqlite3.Connection, fields: dict[str, Any], *, is_demo: bool = False, channel_id: str | None = None) -> dict:
    if not str(fields.get("name", "")).strip():
        raise StudioError("invalid_field", "Informe o nome do canal.")
    columns = _validate(fields)
    identifier = channel_id or new_id("chn")
    stamp = to_iso(utcnow())
    columns.update(id=identifier, is_demo=int(is_demo), created_at=stamp, updated_at=stamp)
    names = ", ".join(columns)
    try:
        conn.execute(f"INSERT INTO managed_channels ({names}) VALUES ({', '.join('?' for _ in columns)})", tuple(columns.values()))
        conn.commit()
    except sqlite3.IntegrityError as error:
        conn.rollback()
        raise StudioError("duplicate_channel", "Este ID do YouTube já está cadastrado.", 409) from error
    return get_channel(conn, identifier)


def get_channel(conn: sqlite3.Connection, channel_id: str) -> dict:
    row = conn.execute("SELECT * FROM managed_channels WHERE id = ?", (channel_id,)).fetchone()
    if row is None:
        raise StudioError("channel_not_found", "Canal não encontrado.", 404)
    return _channel_view(row)


def list_channels(conn: sqlite3.Connection) -> list[dict]:
    return [_channel_view(row) for row in conn.execute("SELECT * FROM managed_channels ORDER BY is_demo, name")]


def update_channel(conn: sqlite3.Connection, channel_id: str, fields: dict[str, Any]) -> dict:
    get_channel(conn, channel_id)
    columns = _validate(fields)
    if not columns:
        return get_channel(conn, channel_id)
    columns["updated_at"] = to_iso(utcnow())
    assignments = ", ".join(f"{name} = ?" for name in columns)
    try:
        conn.execute(f"UPDATE managed_channels SET {assignments} WHERE id = ?", (*columns.values(), channel_id))
        conn.commit()
    except sqlite3.IntegrityError as error:
        conn.rollback()
        raise StudioError("duplicate_channel", "Este ID do YouTube já está cadastrado.", 409) from error
    return get_channel(conn, channel_id)


def delete_channel(conn: sqlite3.Connection, channel_id: str, confirm_name: str) -> None:
    channel = get_channel(conn, channel_id)
    if confirm_name.strip() != channel["name"]:
        raise StudioError("confirmation_mismatch", "Digite o nome exato do canal para remover.")
    active = conn.execute(
        f"SELECT COUNT(*) AS n FROM production_jobs WHERE channel_id = ? AND state IN ({', '.join('?' for _ in ACTIVE_STATES)})",
        (channel_id, *ACTIVE_STATES),
    ).fetchone()["n"]
    if active:
        raise StudioError("channel_has_active_jobs", f"Cancele as {active} tarefas ativas antes de remover o canal.", 409)
    conn.execute("DELETE FROM managed_channels WHERE id = ?", (channel_id,))
    conn.commit()


# --- Concorrentes ------------------------------------------------------------------------------

def list_competitors(conn: sqlite3.Connection, channel_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM competitors WHERE channel_id = ? ORDER BY name", (channel_id,))]


def add_competitor(conn: sqlite3.Connection, channel_id: str, name: str, youtube_ref: str | None, notes: str) -> dict:
    get_channel(conn, channel_id)
    if not name.strip():
        raise StudioError("invalid_field", "Informe o nome do concorrente.")
    identifier = new_id("cmp")
    try:
        conn.execute(
            "INSERT INTO competitors (id, channel_id, name, youtube_ref, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (identifier, channel_id, name.strip(), (youtube_ref or "").strip() or None, notes.strip(), to_iso(utcnow())),
        )
        conn.commit()
    except sqlite3.IntegrityError as error:
        conn.rollback()
        raise StudioError("duplicate_competitor", "Este concorrente já está associado ao canal.", 409) from error
    return dict(conn.execute("SELECT * FROM competitors WHERE id = ?", (identifier,)).fetchone())


def remove_scoped(conn: sqlite3.Connection, table: str, channel_id: str, item_id: str) -> None:
    """Remove um item só se ele pertencer ao canal informado."""
    if table not in {"competitors", "video_history", "calendar_entries"}:
        raise ValueError(table)
    cursor = conn.execute(f"DELETE FROM {table} WHERE id = ? AND channel_id = ?", (item_id, channel_id))
    conn.commit()
    if cursor.rowcount == 0:
        raise StudioError("not_found", "Item não encontrado neste canal.", 404)


# --- Histórico ---------------------------------------------------------------------------------

def _day(value: str, field: str = "data") -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as error:
        raise StudioError("invalid_field", f"{field}: use o formato AAAA-MM-DD.") from error


def list_history(conn: sqlite3.Connection, channel_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM video_history WHERE channel_id = ? ORDER BY published_on DESC, created_at DESC", (channel_id,))]


def add_history(conn: sqlite3.Connection, channel_id: str, *, title: str, format: str, published_on: str, url: str | None,
                views: int | None, result_notes: str, source: str = "manual") -> dict:
    get_channel(conn, channel_id)
    if not title.strip():
        raise StudioError("invalid_field", "Informe o título do vídeo.")
    if format not in {"short", "long"}:
        raise StudioError("invalid_field", "Formato inválido.")
    if views is not None and views < 0:
        raise StudioError("invalid_field", "Views não pode ser negativo.")
    identifier = new_id("vid")
    conn.execute(
        "INSERT INTO video_history (id, channel_id, title, format, published_on, url, views, result_notes, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, channel_id, title.strip(), format, _day(published_on, "Publicação"), (url or "").strip() or None, views, result_notes.strip(), source, to_iso(utcnow())),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM video_history WHERE id = ?", (identifier,)).fetchone())


# --- Calendário --------------------------------------------------------------------------------

CALENDAR_STATUSES = ("planejado", "em_producao", "pronto_para_revisao", "publicado_manualmente", "cancelado")


def list_calendar(conn: sqlite3.Connection, channel_id: str | None, start: str, end: str) -> list[dict]:
    query = ("SELECT e.*, c.name AS channel_name, c.is_demo AS channel_is_demo FROM calendar_entries e "
             "JOIN managed_channels c ON c.id = e.channel_id WHERE e.scheduled_on BETWEEN ? AND ?")
    params: list[Any] = [_day(start), _day(end)]
    if channel_id:
        query += " AND e.channel_id = ?"
        params.append(channel_id)
    return [dict(r) for r in conn.execute(query + " ORDER BY e.scheduled_on, e.created_at", params)]


def add_calendar(conn: sqlite3.Connection, channel_id: str, *, scheduled_on: str, title: str, format: str, notes: str = "",
                 recommendation_id: str | None = None) -> dict:
    get_channel(conn, channel_id)
    if not title.strip():
        raise StudioError("invalid_field", "Informe o título.")
    if format not in {"short", "long"}:
        raise StudioError("invalid_field", "Formato inválido.")
    if recommendation_id:
        owner = conn.execute("SELECT 1 FROM recommendations WHERE id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone()
        if owner is None:
            raise StudioError("recommendation_not_in_channel", "A recomendação não pertence a este canal.", 404)
    identifier = new_id("cal")
    stamp = to_iso(utcnow())
    conn.execute(
        "INSERT INTO calendar_entries (id, channel_id, scheduled_on, title, format, recommendation_id, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (identifier, channel_id, _day(scheduled_on, "Data"), title.strip(), format, recommendation_id, notes.strip(), stamp, stamp),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM calendar_entries WHERE id = ?", (identifier,)).fetchone())


def update_calendar(conn: sqlite3.Connection, channel_id: str, entry_id: str, *, scheduled_on: str | None = None, status: str | None = None) -> dict:
    if status is not None and status not in CALENDAR_STATUSES:
        raise StudioError("invalid_field", "Status inválido.")
    row = conn.execute("SELECT * FROM calendar_entries WHERE id = ? AND channel_id = ?", (entry_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("not_found", "Item não encontrado neste canal.", 404)
    conn.execute(
        "UPDATE calendar_entries SET scheduled_on = ?, status = ?, updated_at = ? WHERE id = ?",
        (_day(scheduled_on, "Data") if scheduled_on else row["scheduled_on"], status or row["status"], to_iso(utcnow()), entry_id),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM calendar_entries WHERE id = ?", (entry_id,)).fetchone())


# --- Recomendações -----------------------------------------------------------------------------

def recommendation_view(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["sources"] = json.loads(data.pop("sources_json"))
    data["titles"] = json.loads(data.pop("titles_json"))
    data["facts_to_verify"] = json.loads(data.pop("facts_to_verify_json"))
    data.pop("dedupe_key", None)
    return data


PRIORITY_ORDER = "CASE editorial_priority WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END"


def list_recommendations(conn: sqlite3.Connection, channel_id: str, status: str | None = None) -> list[dict]:
    get_channel(conn, channel_id)
    query = "SELECT * FROM recommendations WHERE channel_id = ?"
    params: list[Any] = [channel_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    return [recommendation_view(r) for r in conn.execute(f"{query} ORDER BY {PRIORITY_ORDER}, created_at DESC, id", params)]


def set_recommendation_status(conn: sqlite3.Connection, channel_id: str, recommendation_id: str, status: str) -> dict:
    if status not in {"nova", "aceita", "descartada"}:
        raise StudioError("invalid_field", "Status inválido para esta ação.")
    row = conn.execute("SELECT * FROM recommendations WHERE id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("recommendation_not_in_channel", "A recomendação não pertence a este canal.", 404)
    if row["status"] in {"em_producao", "concluida"}:
        raise StudioError("recommendation_locked", "Esta recomendação já está em produção ou concluída.", 409)
    conn.execute("UPDATE recommendations SET status = ?, updated_at = ? WHERE id = ?", (status, to_iso(utcnow()), recommendation_id))
    conn.commit()
    return recommendation_view(conn.execute("SELECT * FROM recommendations WHERE id = ?", (recommendation_id,)).fetchone())


# --- Dados de demonstração ---------------------------------------------------------------------

DEMO_CHANNELS = [
    {"id": "chn_demo_cronicas", "name": "Crônicas de Papel (fictício)", "handle": "@cronicas-demo", "niche": "História animada", "language": "pt", "country": "BR",
     "audience": "Adultos curiosos, 25 a 45 anos, que assistem história no celular",
     "positioning": "Episódios pouco conhecidos da história, contados com humor seco e animação simples.", "tone": "Irônico e direto",
     "keywords": ["história", "roma", "cartago", "império", "vikings", "samurais", "peste"], "avoid": ["política atual"],
     "topic_backlog": ["O cerco de Cartago visto pelos cartagineses", "Quem limpava as ruas de Roma"], "formats": ["long", "short"],
     "long_target_seconds": 540, "short_target_seconds": 55, "cadence_per_week": 3.0},
    {"id": "chn_demo_rotas", "name": "Rotas Esquecidas (fictício)", "handle": "@rotas-demo", "niche": "Comércio e exploração", "language": "pt", "country": "PT",
     "audience": "Público de 30 a 55 anos interessado em geografia e viagens",
     "positioning": "Como rotas comerciais moldaram cidades e impérios.", "tone": "Calmo e documental",
     "keywords": ["rota", "seda", "navegação", "comércio"], "avoid": [],
     "topic_backlog": ["O mercado de especiarias de Calecute"], "formats": ["long"], "long_target_seconds": 900, "short_target_seconds": 60, "cadence_per_week": 1.0},
    {"id": "chn_demo_imperios", "name": "Imperios Olvidados (ficticio)", "handle": "@imperios-demo", "niche": "Historia animada", "language": "es", "country": "MX",
     "audience": "Hispanohablantes de 20 a 40 años", "positioning": "Civilizaciones poco contadas, en formato corto.", "tone": "Enérgico",
     "keywords": ["imperio", "azteca", "historia"], "avoid": [], "topic_backlog": ["La vida diaria en Tenochtitlan"], "formats": ["short"],
     "long_target_seconds": 600, "short_target_seconds": 50, "cadence_per_week": 5.0},
]


def seed_demo_once(conn: sqlite3.Connection, now: datetime | None = None) -> bool:
    """Cria os canais fictícios uma única vez. Se você os remover, eles não voltam."""
    if conn.execute("SELECT 1 FROM studio_meta WHERE key = 'demo_seeded'").fetchone():
        return False
    moment = now or utcnow()
    today = moment.date()
    for blueprint in DEMO_CHANNELS:
        fields = {key: value for key, value in blueprint.items() if key != "id"}
        create_channel(conn, fields, is_demo=True, channel_id=blueprint["id"])
    for channel, name, notes in (
        ("chn_demo_cronicas", "Atlas Animado (fictício)", "Referência de ritmo em vídeos longos"),
        ("chn_demo_cronicas", "Tinta e Império (fictício)", "Mesmo público, menos humor"),
        ("chn_demo_rotas", "Paper Empires (fictício)", "Referência internacional"),
        ("chn_demo_imperios", "Pergamino Animado (fictício)", "Concorrente direto em espanhol"),
    ):
        add_competitor(conn, channel, name, None, notes)
    history = (
        ("chn_demo_cronicas", "O dia em que Roma ficou sem sal", "long", 21, 18400, "Bom início nos primeiros dias"),
        ("chn_demo_cronicas", "Vikings não usavam chifres", "short", 14, 92000, "Comentários pediram parte 2"),
        ("chn_demo_cronicas", "Samurais tinham contador?", "long", 7, None, "Resultado ainda não informado"),
        ("chn_demo_rotas", "Por que Veneza ficou rica", "long", 30, 6100, ""),
        ("chn_demo_imperios", "El mercado de Tlatelolco", "short", 10, 41000, ""),
    )
    for channel, title, video_format, days, views, notes in history:
        add_history(conn, channel, title=title, format=video_format, published_on=(today - timedelta(days=days)).isoformat(),
                    url=None, views=views, result_notes=notes, source="demo")
    for channel, days, title, video_format in (
        ("chn_demo_cronicas", 2, "Quem limpava as ruas de Roma", "long"),
        ("chn_demo_cronicas", 5, "Corte: as ruas de Roma", "short"),
        ("chn_demo_rotas", 9, "O mercado de Calecute", "long"),
        ("chn_demo_imperios", 3, "Un día en Tenochtitlan", "short"),
    ):
        add_calendar(conn, channel, scheduled_on=(today + timedelta(days=days)).isoformat(), title=title, format=video_format, notes="Planejamento fictício")
    conn.execute("INSERT INTO studio_meta (key, value) VALUES ('demo_seeded', ?)", (to_iso(moment),))
    conn.commit()
    return True
