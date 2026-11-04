"""Cruza as pesquisas registradas com o perfil editorial de cada canal.

Regras de dados:
- Canal fictício no modo demo usa as oportunidades fictícias, sempre rotuladas.
- Canal real nunca usa dado fictício.
- Canal real só usa pontuações se a política liberar métricas derivadas. Fora disso, a
  recomendação é editorial: perfil, backlog e histórico do canal, sem nenhum score.
- O banco do estúdio não guarda texto da API: fontes apontam para buscas do aplicativo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import services
from ..config import Settings
from ..db import to_iso, utcnow
from ..metrics.opportunity import Opportunity
from ..metrics.text import normalize, tokens
from ..policy import policy_state
from .store import StudioError, add_calendar, get_channel, list_history, new_id, recommendation_view, update_calendar

MAX_NEW_PER_RUN = 6
FACTS_DEFAULT = "Confirme datas, nomes e afirmações em fontes confiáveis antes de escrever o roteiro."

TEMPLATES = {
    "pt": {
        "titles": ["{s}: a história pouco contada", "{s}: o que quase ninguém explica", "{s}: por que isso importa até hoje"],
        "thumb": "Uma única cena sobre \"{s}\", com um personagem em destaque e no máximo três palavras na imagem.",
        "tone": "Tom",
        "hook": "Abra com a pergunta mais concreta sobre \"{s}\" e responda só no fim do vídeo.",
        "backlog": "Está no backlog editorial do canal.",
        "gap": "A palavra do perfil \"{k}\" ainda não aparece no histórico de vídeos do canal.",
        "fit": "Combina com o posicionamento: {p}",
    },
    "es": {
        "titles": ["{s}: la historia poco contada", "{s}: lo que casi nadie explica", "{s}: por qué sigue importando"],
        "thumb": "Una sola escena sobre \"{s}\", con un personaje destacado y un máximo de tres palabras.",
        "tone": "Tono",
        "hook": "Abre con la pregunta más concreta sobre \"{s}\" y respóndela solo al final.",
        "backlog": "Está en la lista editorial del canal.",
        "gap": "La palabra del perfil \"{k}\" todavía no aparece en el historial del canal.",
        "fit": "Encaja con el posicionamiento: {p}",
    },
    "en": {
        "titles": ["{s}: the untold story", "{s}: what almost nobody explains", "{s}: why it still matters"],
        "thumb": "A single scene about \"{s}\", one character in focus, three words at most.",
        "tone": "Tone",
        "hook": "Open with the most concrete question about \"{s}\" and answer it only at the end.",
        "backlog": "It is on the channel's editorial backlog.",
        "gap": "The profile keyword \"{k}\" does not appear in the channel's video history yet.",
        "fit": "Fits the positioning: {p}",
    },
}


def _text(language: str) -> dict[str, Any]:
    return TEMPLATES.get(language.split("-")[0], TEMPLATES["en"])


def dedupe_key(subject: str, video_format: str) -> str:
    return f"{video_format}:{' '.join(tokens(subject)) or normalize(subject)}"


def _is_avoided(subject: str, avoid: list[str]) -> bool:
    words = set(tokens(subject))
    return any(set(tokens(item)) and set(tokens(item)) <= words for item in avoid)


def _duration(channel: dict, video_format: str) -> int:
    return channel["short_target_seconds"] if video_format == "short" else channel["long_target_seconds"]


def _covered_text(channel_history: list[dict]) -> set[str]:
    covered: set[str] = set()
    for video in channel_history:
        covered.update(tokens(video["title"]))
    return covered


def _insert(conn: sqlite3.Connection, channel: dict, *, subject: str, justification: str, sources: list[dict], titles: list[str],
            thumbnail_idea: str, hook: str, video_format: str, duration_seconds: int, target_audience: str, priority: str,
            facts: list[str], data_basis: str, origin: str) -> dict | None:
    identifier = new_id("rec")
    stamp = to_iso(utcnow())
    cursor = conn.execute(
        """INSERT OR IGNORE INTO recommendations (id, channel_id, dedupe_key, subject, justification, sources_json, titles_json,
               thumbnail_idea, hook, format, duration_seconds, target_audience, editorial_priority, facts_to_verify_json,
               data_basis, origin, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (identifier, channel["id"], dedupe_key(subject, video_format), subject, justification,
         json.dumps(sources, ensure_ascii=False), json.dumps(titles, ensure_ascii=False), thumbnail_idea, hook, video_format,
         duration_seconds, target_audience, priority, json.dumps(facts, ensure_ascii=False), data_basis, origin, stamp, stamp),
    )
    if cursor.rowcount == 0:
        return None
    return recommendation_view(conn.execute("SELECT * FROM recommendations WHERE id = ?", (identifier,)).fetchone())


def _from_template(conn, channel, subject, reasons, sources, video_format, priority, data_basis) -> dict | None:
    text = _text(channel["language"])
    subject = subject[:1].upper() + subject[1:]
    thumbnail = text["thumb"].format(s=subject)
    if channel["tone"]:
        thumbnail += f" {text['tone']}: {channel['tone']}."
    return _insert(
        conn, channel, subject=subject, justification=" ".join(reasons), sources=sources,
        titles=[pattern.format(s=subject) for pattern in text["titles"]],
        thumbnail_idea=thumbnail, hook=text["hook"].format(s=subject),
        video_format=video_format, duration_seconds=_duration(channel, video_format),
        target_audience=channel["audience"] or "Público ainda não definido no perfil do canal.",
        priority=priority, facts=[FACTS_DEFAULT], data_basis=data_basis, origin="regras",
    )


def _keyword_overlap(topic: str, channel: dict) -> set[str]:
    wanted: set[str] = set()
    for keyword in channel["keywords"]:
        wanted.update(tokens(keyword))
    return set(tokens(topic)) & wanted


def _metric_candidates(channel: dict, research: sqlite3.Connection, settings: Settings) -> list[Opportunity]:
    items: list[Opportunity] = []
    for video_format in channel["formats"]:
        for item in services.compute_opportunities(research, settings, video_format=video_format, language=channel["language"].split("-")[0]):
            if item.score is not None and _keyword_overlap(item.topic, channel) and not _is_avoided(item.topic, channel["avoid"]):
                items.append(item)
    items.sort(key=lambda o: (-len(_keyword_overlap(o.topic, channel)), -(o.score or 0), o.topic))
    return items


def _search_sources(channel: dict, research: sqlite3.Connection | None, subject: str) -> list[dict]:
    """Só o texto da busca, que é seu, e um link interno. Nenhum dado da API fica guardado aqui."""
    if research is None:
        return []
    words = set(tokens(subject))
    label = "Busca fictícia" if channel["is_demo"] else "Busca registrada"
    sources = []
    for row in research.execute("SELECT DISTINCT query FROM searches WHERE language = ? OR language IS NULL ORDER BY query", (channel["language"].split("-")[0],)):
        shared = sorted(words & set(tokens(row["query"])))
        if shared:
            sources.append({"kind": "pesquisa", "label": f"{label}: {row['query']}", "url": f"/videos?q={quote(shared[0])}", "fictional": channel["is_demo"]})
    return sources[:2]


def generate(conn: sqlite3.Connection, research: sqlite3.Connection | None, settings: Settings, channel_id: str) -> dict:
    """Gera recomendações por regras. Repetir não duplica: o par assunto e formato é único no canal."""
    channel = get_channel(conn, channel_id)
    state = policy_state(settings)
    use_demo = channel["is_demo"] and settings.mode == "demo" and research is not None
    use_approved = not channel["is_demo"] and settings.mode == "live" and state.derived_allowed and research is not None
    created: list[dict] = []

    if use_demo or use_approved:
        for item in _metric_candidates(channel, research, settings):
            if len(created) >= MAX_NEW_PER_RUN // 2:
                break
            priority = "alta" if (item.score or 0) >= 55 else "media" if (item.score or 0) >= 45 else "baixa"
            if use_demo:
                reasons = [f"Dados fictícios de demonstração: pontuação experimental {item.score:.0f}, confiança {item.confidence:.0f}, amostra de {item.sample_size} vídeos fictícios."]
                sources = [{"kind": "demo", "label": f"Busca fictícia: {item.topic}", "url": f"/oportunidades/detalhe?topic={quote(item.topic)}&f={item.format}", "fictional": True}]
            else:
                reasons = [f"Métrica calculada por este aplicativo, não pelo YouTube: pontuação experimental {item.score:.0f}, confiança {item.confidence:.0f}."]
                sources = [{"kind": "pesquisa", "label": f"Busca registrada: {item.topic}", "url": f"/oportunidades/detalhe?topic={quote(item.topic)}&f={item.format}", "fictional": False}]
            reasons.append(f"Coincide com o perfil do canal em: {', '.join(sorted(_keyword_overlap(item.topic, channel)))}.")
            record = _from_template(conn, channel, item.topic, reasons, sources, item.format, priority, "demo_metrics" if use_demo else "approved_metrics")
            if record:
                created.append(record)

    text = _text(channel["language"])
    profile_source = {"kind": "perfil", "label": "Perfil editorial do canal", "url": None, "fictional": channel["is_demo"]}
    primary_format = channel["formats"][0]
    # Canal real só cita pesquisa real; canal fictício só cita pesquisa fictícia.
    search_conn = research if channel["is_demo"] == (settings.mode == "demo") else None
    for position, subject in enumerate(channel["topic_backlog"]):
        if len(created) >= MAX_NEW_PER_RUN:
            break
        if _is_avoided(subject, channel["avoid"]):
            continue
        reasons = [text["backlog"]]
        if channel["positioning"]:
            reasons.append(text["fit"].format(p=channel["positioning"]))
        record = _from_template(conn, channel, subject, reasons, [profile_source, *_search_sources(channel, search_conn, subject)],
                                primary_format, "alta" if position == 0 else "media", "editorial")
        if record:
            created.append(record)

    covered = _covered_text(list_history(conn, channel_id))
    for keyword in channel["keywords"]:
        if len(created) >= MAX_NEW_PER_RUN:
            break
        words = set(tokens(keyword))
        if not words or words & covered or _is_avoided(keyword, channel["avoid"]):
            continue
        history_source = {"kind": "historico", "label": "Histórico de vídeos do canal", "url": None, "fictional": channel["is_demo"]}
        record = _from_template(conn, channel, keyword, [text["gap"].format(k=keyword)],
                                [profile_source, history_source, *_search_sources(channel, search_conn, keyword)],
                                primary_format, "baixa", "editorial")
        if record:
            created.append(record)

    conn.commit()
    return {"created": created, "data_policy": state.state,
            "note": "Texto gerado por regras, para você editar. Peça ao Claude pelo contrato do agente para uma versão escrita."}


def create_owner_recommendation(conn: sqlite3.Connection, channel_id: str, *, subject: str, justification: str, video_format: str,
                                duration_seconds: int | None = None, target_audience: str = "", priority: str = "media") -> dict:
    """Recomendação escrita por você. Começa sem títulos: gere ou escreva depois."""
    channel = get_channel(conn, channel_id)
    subject = subject.strip()
    if len(subject) < 3:
        raise StudioError("invalid_field", "Informe o assunto do vídeo.")
    if not justification.strip():
        raise StudioError("invalid_field", "Informe a justificativa.")
    if video_format not in channel["formats"]:
        raise StudioError("format_not_in_profile", "Este canal não usa esse formato.", 422)
    if priority not in {"alta", "media", "baixa"}:
        raise StudioError("invalid_field", "Prioridade inválida.")
    if duration_seconds is not None and duration_seconds <= 0:
        raise StudioError("invalid_field", "A duração precisa ser positiva.")
    if _is_avoided(subject, channel["avoid"]):
        raise StudioError("subject_avoided", "O assunto está na lista de temas evitados do canal.", 422)
    text = _text(channel["language"])
    thumbnail = text["thumb"].format(s=subject)
    if channel["tone"]:
        thumbnail += f" {text['tone']}: {channel['tone']}."
    record = _insert(
        conn, channel, subject=subject, justification=justification.strip(),
        sources=[{"kind": "dono", "label": "Ideia registrada por você", "url": None, "fictional": channel["is_demo"]}],
        titles=[], thumbnail_idea=thumbnail, hook=text["hook"].format(s=subject), video_format=video_format,
        duration_seconds=duration_seconds or _duration(channel, video_format),
        target_audience=target_audience.strip() or channel["audience"] or "Público ainda não definido no perfil do canal.",
        priority=priority, facts=[FACTS_DEFAULT], data_basis="editorial", origin="dono",
    )
    if record is None:
        raise StudioError("duplicate_recommendation", "Já existe recomendação com este assunto e formato neste canal.", 409)
    conn.commit()
    return record


def _open_recommendation(conn: sqlite3.Connection, channel_id: str, recommendation_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM recommendations WHERE id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone()
    if row is None:
        raise StudioError("recommendation_not_in_channel", "A recomendação não pertence a este canal.", 404)
    if row["status"] not in {"nova", "aceita"}:
        raise StudioError("recommendation_unavailable", f"A recomendação está como '{row['status']}'.", 409)
    return row


def generate_titles(conn: sqlite3.Connection, channel_id: str, recommendation_id: str) -> dict:
    """Três títulos por regras, no idioma do canal. Pode ser refeito até a produção começar."""
    channel = get_channel(conn, channel_id)
    row = _open_recommendation(conn, channel_id, recommendation_id)
    subject = row["subject"][:1].upper() + row["subject"][1:]
    titles = [pattern.format(s=subject) for pattern in _text(channel["language"])["titles"]]
    conn.execute("UPDATE recommendations SET titles_json = ?, updated_at = ? WHERE id = ?",
                 (json.dumps(titles, ensure_ascii=False), to_iso(utcnow()), recommendation_id))
    conn.commit()
    return recommendation_view(conn.execute("SELECT * FROM recommendations WHERE id = ?", (recommendation_id,)).fetchone())


OUTLINE = {
    "long": (("Gancho", 0.05), ("Contexto", 0.2), ("Desenvolvimento", 0.45), ("Virada", 0.2), ("Fecho", 0.1)),
    "short": (("Gancho", 0.15), ("Desenvolvimento", 0.65), ("Fecho", 0.2)),
}


def approve_briefing(conn: sqlite3.Connection, channel_id: str, recommendation_id: str, chosen_title: str,
                     planned_on: str | None = None, approved_by: str = "dono_local") -> dict:
    """Só o dono aprova: esta função não é exposta ao agente."""
    channel = get_channel(conn, channel_id)
    row = _open_recommendation(conn, channel_id, recommendation_id)
    title = chosen_title.strip()
    if not title:
        raise StudioError("title_required", "Escolha ou escreva um título.")
    if len(title) > 100:
        raise StudioError("invalid_field", "O título pode ter no máximo 100 caracteres.")
    duration = row["duration_seconds"]
    payload = {
        "chosen_title": title, "subject": row["subject"], "justification": row["justification"], "hook": row["hook"],
        "thumbnail_idea": row["thumbnail_idea"], "format": row["format"], "duration_seconds": duration,
        "target_audience": row["target_audience"], "language": channel["language"], "tone": channel["tone"],
        "positioning": channel["positioning"], "avoid": channel["avoid"],
        "outline": [{"section": name, "target_seconds": round(duration * share)} for name, share in OUTLINE[row["format"]]],
        "sources": json.loads(row["sources_json"]), "facts_to_verify": json.loads(row["facts_to_verify_json"]),
        "data_basis": row["data_basis"], "fictional": channel["is_demo"] or row["data_basis"] == "demo_metrics",
        "constraints": ["Não publicar.", "Não inventar números de desempenho.", "Conferir fatos antes de produzir."],
    }
    stamp = to_iso(utcnow())
    existing = conn.execute("SELECT id FROM briefings WHERE recommendation_id = ?", (recommendation_id,)).fetchone()
    briefing_id = existing["id"] if existing else new_id("brf")
    conn.execute(
        """INSERT INTO briefings (id, channel_id, recommendation_id, chosen_title, payload_json, approved_by, approved_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET chosen_title = excluded.chosen_title,
           payload_json = excluded.payload_json, approved_by = excluded.approved_by, approved_at = excluded.approved_at, updated_at = excluded.updated_at""",
        (briefing_id, channel_id, recommendation_id, title, json.dumps(payload, ensure_ascii=False), approved_by, stamp, stamp),
    )
    conn.execute("UPDATE recommendations SET status = 'aceita', updated_at = ? WHERE id = ?", (stamp, recommendation_id))
    conn.commit()
    # O calendário acompanha o briefing: reaprovar atualiza o item existente, em vez de duplicar.
    entry = conn.execute("SELECT id FROM calendar_entries WHERE recommendation_id = ? AND channel_id = ?", (recommendation_id, channel_id)).fetchone()
    if entry:
        if planned_on:
            update_calendar(conn, channel_id, entry["id"], scheduled_on=planned_on)
        conn.execute("UPDATE calendar_entries SET title = ?, updated_at = ? WHERE id = ?", (title, stamp, entry["id"]))
        conn.commit()
    elif planned_on:
        add_calendar(conn, channel_id, scheduled_on=planned_on, title=title, format=row["format"],
                     notes="Criado ao aprovar o briefing.", recommendation_id=recommendation_id)
    return briefing_view(conn.execute("SELECT * FROM briefings WHERE id = ?", (briefing_id,)).fetchone())


def briefing_view(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    data["payload"] = json.loads(data.pop("payload_json"))
    return data


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=300)
    url: str | None = None

    @field_validator("url")
    @classmethod
    def _http_only(cls, value: str | None) -> str | None:
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("A URL precisa começar com http:// ou https://")
        return value


class RecommendationInput(BaseModel):
    """Recomendação escrita por um agente. Sem campo de score, de propósito."""

    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=3, max_length=200)
    justification: str = Field(min_length=10, max_length=2000)
    sources: list[SourceInput] = Field(min_length=1, max_length=20)
    titles: list[str] = Field(min_length=3, max_length=3)
    thumbnail_idea: str = Field(min_length=5, max_length=600)
    hook: str = Field(min_length=5, max_length=600)
    format: str = Field(pattern="^(short|long)$")
    duration_seconds: int = Field(gt=0, le=7200)
    target_audience: str = Field(min_length=3, max_length=300)
    editorial_priority: str = Field(pattern="^(alta|media|baixa)$")
    facts_to_verify: list[str] = Field(default_factory=list, max_length=40)


def insert_agent_recommendation(conn: sqlite3.Connection, channel: dict, data: RecommendationInput) -> dict:
    if data.format not in channel["formats"]:
        raise StudioError("format_not_in_profile", "Este canal não usa esse formato.", 422)
    if _is_avoided(data.subject, channel["avoid"]):
        raise StudioError("subject_avoided", "O assunto está na lista de temas evitados do canal.", 422)
    sources = [{"kind": "agente", "label": s.label, "url": s.url, "fictional": False, "verified": False} for s in data.sources]
    record = _insert(conn, channel, subject=data.subject, justification=data.justification, sources=sources, titles=data.titles,
                     thumbnail_idea=data.thumbnail_idea, hook=data.hook, video_format=data.format, duration_seconds=data.duration_seconds,
                     target_audience=data.target_audience, priority=data.editorial_priority,
                     facts=data.facts_to_verify or [FACTS_DEFAULT], data_basis="editorial", origin="agente")
    if record is None:
        raise StudioError("duplicate_recommendation", "Já existe recomendação com este assunto e formato neste canal.", 409)
    return record
