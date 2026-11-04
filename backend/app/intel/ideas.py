"""Daily Ideas: recomendações por canal, sobre a tabela de recomendações que já alimenta a produção.

Sem previsão de views. Dificuldade e confiança são estimativas por regra: a confiança descreve a evidência
disponível, nunca a chance de o vídeo dar certo. Títulos que repetem um vídeo da base são descartados.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from urllib.parse import quote

from .. import services
from ..config import Settings
from ..db import to_iso
from ..metrics.text import normalize, tokens
from ..policy import policy_state
from ..studio import recommend, store
from ..studio.store import StudioError
from . import competitors, keywords, titles
from .common import compatible

MAX_NEW = 6
STATUS_FILTERS = {"novas": ("nova",), "salvas": ("aceita",), "rejeitadas": ("descartada",), "producao": ("em_producao", "concluida")}
SAVE_MAP = {"salvar": "aceita", "rejeitar": "descartada", "restaurar": "nova"}
EVIDENCE_KINDS = {"pesquisa", "demo", "analytics", "tendencia", "concorrentes", "favorita"}
ESTIMATE_NOTE = "Dificuldade e confiança são estimativas por regra. A confiança descreve a evidência reunida, não a chance de resultado."


def estimate_difficulty(video_format: str, duration_seconds: int) -> str:
    """Só formato e duração: quanto material a produção exige. Não mede a dificuldade do assunto."""
    if video_format == "short":
        return "baixa"
    return "media" if duration_seconds <= 480 else "alta"


def estimate_confidence(sources: list[dict], data_basis: str, justification: str) -> str:
    """Conta fontes independentes do perfil. Com métrica aprovada ou fictícia, sobe um nível."""
    evidence = sum(1 for source in sources if source.get("kind") in EVIDENCE_KINDS)
    if evidence == 0:
        return "baixa"
    if data_basis in {"demo_metrics", "approved_metrics"} and evidence >= 1 and "confiança" in justification.lower():
        return "alta" if evidence >= 2 else "media"
    return "media" if evidence >= 2 else "baixa"


def _backfill(studio: sqlite3.Connection, channel_id: str) -> None:
    rows = studio.execute("SELECT * FROM recommendations WHERE channel_id = ? AND (difficulty IS NULL OR confidence IS NULL)", (channel_id,)).fetchall()
    for row in rows:
        studio.execute("UPDATE recommendations SET difficulty = ?, confidence = ? WHERE id = ?", (
            estimate_difficulty(row["format"], row["duration_seconds"]),
            estimate_confidence(json.loads(row["sources_json"]), row["data_basis"], row["justification"]), row["id"]))
    if rows:
        studio.commit()


def _copies_a_video(conn: sqlite3.Connection, titles: list[str]) -> bool:
    wanted = {normalize(title) for title in titles}
    return any(normalize(row["title"]) in wanted for row in conn.execute("SELECT title FROM videos"))


def _candidates(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel: dict, now: datetime) -> list[tuple[str, str, dict, str]]:
    """Assunto, motivo, fonte e prioridade. Os dados de pesquisa só entram se o canal puder recebê-los."""
    output: list[tuple[str, str, dict, str]] = []
    fictional = channel["is_demo"]
    usable = compatible(channel, settings)
    for item in keywords.list_favorites(studio, channel["id"])[:4]:
        output.append((item["term"], "Você marcou este termo como favorito.", {"kind": "favorita", "label": f"Palavra favorita: {item['term']}", "url": f"/palavras?termo={quote(item['term'])}&canal={channel['id']}", "fictional": fictional}, "media"))
    if not usable:
        return output
    for row in conn.execute("SELECT id, query, saved_name FROM research_runs WHERE managed_channel_id = ? AND saved_name IS NOT NULL ORDER BY executed_at DESC LIMIT 4", (channel["id"],)):
        output.append((row["query"], "Você salvou esta pesquisa para o canal.", {"kind": "pesquisa", "label": f"Pesquisa salva: {row['saved_name']}", "url": f"/pesquisa/{row['id']}", "fictional": fictional}, "media"))
    for item in keywords.own_terms(conn, studio, settings, channel["id"])["items"][:3]:
        output.append((item["term"], "As pessoas já acham o canal por esta busca, segundo o YouTube Analytics.", {"kind": "analytics", "label": f"Termo de descoberta: {item['term']}", "url": f"/palavras?aba=descoberta&canal={channel['id']}", "fictional": fictional}, "alta"))
    if policy_state(settings).derived_allowed:
        wanted = {token for keyword in channel["keywords"] for token in tokens(keyword)}
        for trend in services.trends(conn, settings)["items"]:
            if wanted & set(tokens(trend["term"])) and trend["accelerating_share"] >= 0.3 and titles.is_real_subject(trend["term"], channel["language"]):
                output.append((trend["term"], f"{trend['accelerating']} de {trend['videos']} vídeos monitorados ganham velocidade, em {trend['channels']} canais. Calculado por este aplicativo.",
                               {"kind": "tendencia", "label": f"Tendência: {trend['term']}", "url": f"/palavras?termo={quote(trend['term'])}&canal={channel['id']}&aba=ascensao", "fictional": fictional}, "media"))
        covered = {token for video in store.list_history(studio, channel["id"]) for token in tokens(video["title"])}
        for competitor in store.list_competitors(studio, channel["id"]):
            research_id = competitors._research_id(conn, settings, competitor)
            if not research_id:
                continue
            for subject in competitors._recurring_subjects(competitors._videos(conn, research_id))[:4]:
                if " " in subject["term"] and titles.is_real_subject(subject["term"], channel["language"]) and not set(tokens(subject["term"])) & covered:
                    output.append((subject["term"], f"Assunto recorrente em {subject['videos']} vídeos de uma referência e ausente do seu histórico. Use um ângulo próprio.",
                                   {"kind": "concorrentes", "label": f"Referência: {competitor['name']}", "url": f"/canais/{channel['id']}/concorrentes/{competitor['id']}", "fictional": fictional}, "baixa"))
    return output


def generate(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, now: datetime) -> dict:
    """Junta as regras do perfil às fontes novas. Repetir não duplica: assunto e formato são únicos no canal."""
    channel = store.get_channel(studio, channel_id)
    research = conn if channel["is_demo"] == (settings.mode == "demo") else None
    created = recommend.generate(studio, research, settings, channel_id)["created"]
    basis = "editorial"
    skipped_copies = 0
    formats = channel["formats"]
    for index, (subject, reason, source, priority) in enumerate(_candidates(conn, studio, settings, channel, now)):
        if len(created) >= MAX_NEW:
            break
        if recommend._is_avoided(subject, channel["avoid"]):
            continue
        if _copies_a_video(conn, [item["title"] for item in recommend.title_options(channel, subject, formats[index % len(formats)])]):
            skipped_copies += 1
            continue
        kind_basis = "demo_metrics" if source["kind"] == "tendencia" and channel["is_demo"] else "approved_metrics" if source["kind"] in {"tendencia", "concorrentes"} else basis
        if source["kind"] == "concorrentes" and channel["is_demo"]:
            kind_basis = "demo_metrics"
        profile_source = {"kind": "perfil", "label": "Perfil editorial do canal", "url": None, "fictional": channel["is_demo"]}
        record = recommend._from_template(studio, channel, subject, [reason], [source, profile_source], formats[index % len(formats)], priority, kind_basis)
        if record:
            created.append(record)
    studio.commit()
    _backfill(studio, channel_id)
    return {"created": len(created), "skipped_copies": skipped_copies, "generated_at": to_iso(now), "data_policy": policy_state(settings).state, "uses_research": research is not None,
            "note": "Texto por regras, para você editar. Para texto escrito, use o Coach com Claude ou o contrato do agente."}


def _view(row: sqlite3.Row) -> dict:
    data = store.recommendation_view(row)
    data["favorite"] = bool(data["favorite"])
    data["recommended_on"] = data["created_at"][:10]
    return data


def list_ideas(studio: sqlite3.Connection, channel_id: str, *, filter_name: str = "novas", limit: int = 20, offset: int = 0) -> dict:
    store.get_channel(studio, channel_id)
    _backfill(studio, channel_id)
    where, params = "channel_id = ?", [channel_id]
    if filter_name == "favoritas":
        where += " AND favorite = 1"
    elif filter_name in STATUS_FILTERS:
        statuses = STATUS_FILTERS[filter_name]
        where += f" AND status IN ({', '.join('?' for _ in statuses)})"
        params.extend(statuses)
    else:
        raise StudioError("invalid_field", "Filtro inválido.")
    total = studio.execute(f"SELECT COUNT(*) AS n FROM recommendations WHERE {where}", params).fetchone()["n"]
    rows = studio.execute(f"SELECT * FROM recommendations WHERE {where} ORDER BY {store.PRIORITY_ORDER}, created_at DESC, id LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    scheduled = {r["recommendation_id"]: r["scheduled_on"] for r in studio.execute("SELECT recommendation_id, scheduled_on FROM calendar_entries WHERE channel_id = ? AND recommendation_id IS NOT NULL AND status != 'cancelado'", (channel_id,))}
    counts = {name: studio.execute(f"SELECT COUNT(*) AS n FROM recommendations WHERE channel_id = ? AND status IN ({', '.join('?' for _ in statuses)})", (channel_id, *statuses)).fetchone()["n"] for name, statuses in STATUS_FILTERS.items()}
    counts["favoritas"] = studio.execute("SELECT COUNT(*) AS n FROM recommendations WHERE channel_id = ? AND favorite = 1", (channel_id,)).fetchone()["n"]
    return {"total": total, "limit": limit, "offset": offset, "counts": counts, "estimate_note": ESTIMATE_NOTE,
            "items": [{**_view(row), "scheduled_on": scheduled.get(row["id"])} for row in rows]}


def act(studio: sqlite3.Connection, channel_id: str, recommendation_id: str, action: str) -> dict:
    if action not in SAVE_MAP:
        raise StudioError("invalid_field", "Ação inválida.")
    return store.set_recommendation_status(studio, channel_id, recommendation_id, SAVE_MAP[action])


def set_favorite(studio: sqlite3.Connection, channel_id: str, recommendation_id: str, favorite: bool, now: datetime) -> dict:
    cursor = studio.execute("UPDATE recommendations SET favorite = ?, updated_at = ? WHERE id = ? AND channel_id = ?", (int(favorite), to_iso(now), recommendation_id, channel_id))
    studio.commit()
    if cursor.rowcount == 0:
        raise StudioError("recommendation_not_in_channel", "A ideia não pertence a este canal.", 404)
    return _view(studio.execute("SELECT * FROM recommendations WHERE id = ?", (recommendation_id,)).fetchone())


def schedule(studio: sqlite3.Connection, channel_id: str, recommendation_id: str, scheduled_on: str, today: date) -> dict:
    """Pôr no calendário salva a ideia. Repetir muda a data, sem criar item duplicado."""
    row = studio.execute("SELECT * FROM recommendations WHERE id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("recommendation_not_in_channel", "A ideia não pertence a este canal.", 404)
    if row["status"] == "descartada":
        raise StudioError("recommendation_unavailable", "Restaure a ideia antes de pôr no calendário.", 409)
    try:
        chosen = date.fromisoformat(scheduled_on)
    except (TypeError, ValueError) as error:
        raise StudioError("invalid_field", "Data: use o formato AAAA-MM-DD.") from error
    if chosen < today:
        raise StudioError("invalid_field", "Escolha hoje ou uma data futura.")
    titles = json.loads(row["titles_json"])
    existing = studio.execute("SELECT id FROM calendar_entries WHERE channel_id = ? AND recommendation_id = ? AND status != 'cancelado'", (channel_id, recommendation_id)).fetchone()
    if existing:
        entry = store.update_calendar(studio, channel_id, existing["id"], scheduled_on=chosen.isoformat())
    else:
        entry = store.add_calendar(studio, channel_id, scheduled_on=chosen.isoformat(), title=titles[0] if titles else row["subject"], format=row["format"], notes="Criado em Ideias diárias.", recommendation_id=recommendation_id)
    if row["status"] == "nova":
        store.set_recommendation_status(studio, channel_id, recommendation_id, "aceita")
    return entry
