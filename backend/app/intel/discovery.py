"""Descoberta de oportunidades para canais dark: nicho, subnicho, país, idioma, recência e formato.

Separa o que foi observado, o que é estimado e o que é hipótese editorial. Sem aprovação do Google, nada aqui
calcula VPH, outlier, índice, ranking ou contagem sobre dados da API. As hipóteses usam só o que é seu: o perfil,
o histórico e a lista de temas evitados do canal, além do texto da sua própria pesquisa.
"""
from __future__ import annotations

import sqlite3
import tomllib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ..config import BACKEND_DIR, Settings
from ..db import to_iso
from ..metrics.text import tokens
from ..policy import policy_state
from ..studio import store
from ..studio.store import StudioError, new_id
from . import research
from .common import ClientFactory, default_client, require_channel

CATALOG_PATH = BACKEND_DIR / "config" / "nichos_dark.toml"
TARGETS = {
    "recent_videos": ("recent", "Vídeos recentes"),
    "videos": ("videos", "Vídeos do tema"),
    "emerging_channels": ("emerging", "Canais pequenos com vídeo recente"),
    "channels": ("channels", "Canais do tema"),
}
ITEM_TYPES = {"video", "canal", "titulo", "tema"}
FORMAT_CONFIDENCE = {
    "analytics": ("confirmado", "Informado pelo YouTube Analytics do próprio canal."),
    "broadcast": ("confirmado", "A API indica transmissão ao vivo."),
    "duration": ("confiavel", "Mais longo do que um Short pode ser."),
    "aspect_ratio": ("estimado", "Pela duração, pela data de envio e pela proporção do player. É um indício, não uma confirmação do YouTube."),
    "fictional": ("ficticio", "Definido nos dados fictícios."),
    "missing": ("indeterminado", "A API não informou a duração."),
}


def _load_catalog(path: Path = CATALOG_PATH) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def catalog() -> dict:
    data = _load_catalog()
    return {"note": "Atalhos editoriais escritos à mão. Não vêm do YouTube e não medem demanda.", "targets": [{"key": key, "label": value[1]} for key, value in TARGETS.items()], "niches": [
        {"key": key, "label": niche["label"], "subniches": [{"key": sub_key, "label": sub["label"]} for sub_key, sub in niche["subniches"].items()]}
        for key, niche in data.items()
    ]}


def build_query(niche: str | None, subniche: str | None, free_text: str | None, language: str | None) -> tuple[str, str | None, str | None]:
    """Termo enviado à API. O texto digitado vem primeiro: é ele que define o recorte."""
    typed = " ".join((free_text or "").split())
    data = _load_catalog()
    if niche and niche not in data:
        raise StudioError("invalid_field", "Nicho desconhecido.")
    base = ""
    niche_label = data[niche]["label"] if niche else None
    subniche_label = None
    if subniche:
        if not niche or subniche not in data[niche]["subniches"]:
            raise StudioError("invalid_field", "Subnicho desconhecido neste nicho.")
        entry = data[niche]["subniches"][subniche]
        subniche_label = entry["label"]
        base = entry.get((language or "pt").split("-")[0]) or entry["en"]
    elif niche and not typed:
        raise StudioError("invalid_field", "Escolha um subnicho ou digite o assunto.")
    query = " ".join(part for part in (typed, base) if part)
    if not query:
        raise StudioError("invalid_field", "Escolha um subnicho ou digite o assunto.")
    return query[:120], niche_label, subniche_label


def discover(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, *, target: str, niche: str | None, subniche: str | None, free_text: str | None,
             language: str | None, country: str | None, days: int | None, video_format: str | None, max_subscribers: int | None, channel_id: str | None, now: datetime,
             factory: ClientFactory = default_client) -> dict:
    if target not in TARGETS:
        raise StudioError("invalid_field", "Tipo de descoberta desconhecido.")
    query, niche_label, subniche_label = build_query(niche, subniche, free_text, language)
    return research.run_search(conn, studio, settings, kind=TARGETS[target][0], query=query, channel_id=channel_id, now=now, language=language, country=country, days=days,
                               video_format=video_format, order="date" if target == "recent_videos" else "relevance", max_subscribers=max_subscribers, factory=factory,
                               tags={"niche": niche_label, "subniche": subniche_label, "discovery": True})


def _format_estimate(video: dict, source: str) -> dict:
    level, basis = FORMAT_CONFIDENCE.get(source, ("indeterminado", "Sem dados suficientes."))
    if video["format"] == "indeterminate":
        level, basis = "indeterminado", "Vídeo curto sem proporção conhecida: pode ser Short ou vídeo normal."
    return {"format": video["format"], "confidence": level, "basis": basis}


def _hypotheses(studio: sqlite3.Connection, settings: Settings, channel: dict | None, query: str) -> list[dict]:
    """Só dados seus. Nenhuma hipótese usa título, view ou inscrito devolvido pela API."""
    if channel is None:
        return [{"text": "Associe a pesquisa a um canal para cruzar o tema com o perfil e o histórico dele.", "basis": "Sem canal associado.", "kind": "falta"}]
    output: list[dict] = []
    words = set(tokens(query))
    profile = {word for keyword in channel["keywords"] for word in tokens(keyword)}
    shared = sorted(words & profile)
    if shared:
        output.append({"text": f"O tema pode combinar com {channel['name']}: ele aparece no seu perfil em \"{', '.join(shared[:5])}\".", "basis": "Comparação com as palavras do perfil do canal.", "kind": "perfil"})
    elif profile:
        output.append({"text": f"O tema pode estar fora do perfil de {channel['name']}, ou pode ser um recorte novo. Decida antes de investir nele.", "basis": "Nenhuma palavra da pesquisa aparece no perfil do canal.", "kind": "perfil"})
    avoided = [item for item in channel["avoid"] if set(tokens(item)) & words]
    if avoided:
        output.append({"text": f"Atenção: o perfil do canal evita \"{avoided[0]}\".", "basis": "Lista de temas evitados do canal.", "kind": "evitar"})
    history = store.list_history(studio, channel["id"])
    covered = [video for video in history if words & set(tokens(video["title"]))]
    if history and not covered:
        output.append({"text": "Pode haver espaço no seu calendário: nenhum vídeo do seu histórico cita estas palavras.", "basis": f"Comparação com {len(history)} vídeos que você registrou. Não diz nada sobre a concorrência no YouTube.", "kind": "historico"})
    elif covered:
        output.append({"text": f"Você já tratou de assunto próximo em \"{covered[0]['title']}\". Um ângulo diferente pode evitar repetição.", "basis": "Histórico de vídeos que você registrou.", "kind": "historico"})
    if not output:
        output.append({"text": "Preencha as palavras e o histórico do canal para eu cruzar este tema com ele.", "basis": "O perfil do canal está vazio.", "kind": "falta"})
    return output


def view(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, run_id: str, *, limit: int = 25, offset: int = 0) -> dict:
    data = research.run_items(conn, settings, run_id, limit=limit, offset=offset)
    run = data["run"]
    channel = None
    if run["managed_channel_id"]:
        try:
            channel = store.get_channel(studio, run["managed_channel_id"])
        except StudioError:
            channel = None
    sources = {row["id"]: row["format_source"] for row in conn.execute(
        "SELECT id, format_source FROM videos WHERE id IN (SELECT item_id FROM research_items WHERE run_id = ? AND item_type = 'video')", (run_id,))}
    estimates = []
    if run["total_results_approx"] is not None:
        estimates.append({"label": "Resultados informados pela API", "value": run["total_results_approx"], "note": "Número aproximado de resultados da busca (pageInfo.totalResults). Não é volume de buscas e costuma variar."})
    estimates.append({"label": "Volume de busca", "value": None, "note": "Indisponível: nenhuma API pública do YouTube informa esse número."})
    return {
        **data,
        "observed": {"videos": data["videos"], "channels": data["channels"],
                     "note": "Dados públicos devolvidos pela API, como estavam na hora da coleta."},
        "estimates": estimates,
        "format_estimates": {video["id"]: _format_estimate(video, sources.get(video["id"], "missing")) for video in data["videos"]},
        "hypotheses": _hypotheses(studio, settings, channel, run["query"]),
        "hypotheses_note": "Hipóteses por regras, a partir do seu perfil e do seu histórico. Não são análise de IA, e nenhuma usa números do YouTube.",
        "channel": {"id": channel["id"], "name": channel["name"]} if channel else None,
        "blocked_metrics": None if policy_state(settings).derived_allowed else "VPH, outliers, índices e rankings seguem bloqueados: faltam auditoria e aprovação do Google.",
    }


def save_item(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str, *, item_type: str, item_id: str | None, text: str | None, note: str,
              run_id: str | None, now: datetime) -> dict:
    """Vídeo, título e canal guardam o ID, e o texto da API segue a retenção. Tema guarda o texto, que é seu."""
    require_channel(studio, settings, channel_id)
    if item_type not in ITEM_TYPES:
        raise StudioError("invalid_field", "Tipo de item inválido.")
    title, video_id, channel_ref, niche, subniche = "", None, None, None, None
    if run_id:
        run = research.get_run(conn, run_id)
        niche, subniche = run["filters"].get("niche"), run["filters"].get("subniche")
    if item_type == "tema":
        title = " ".join((text or "").split())
        if not 3 <= len(title) <= 200:
            raise StudioError("invalid_field", "Descreva o tema em 3 a 200 caracteres.")
    elif item_type in {"video", "titulo"}:
        if not item_id or conn.execute("SELECT 1 FROM videos WHERE id = ?", (item_id,)).fetchone() is None:
            raise StudioError("video_not_found", "Vídeo não encontrado na base.", 404)
        video_id = item_id
    else:
        if not item_id or conn.execute("SELECT 1 FROM channels WHERE id = ?", (item_id,)).fetchone() is None:
            raise StudioError("channel_not_found", "Canal não encontrado na base.", 404)
        channel_ref = item_id
    duplicate = conn.execute(
        "SELECT id FROM editorial_opportunities WHERE managed_channel_id = ? AND item_type = ? AND status = 'aberta' AND ((video_id IS NOT NULL AND video_id = ?) OR (channel_ref IS NOT NULL AND channel_ref = ?) OR (? != '' AND title = ?))",
        (channel_id, item_type, video_id, channel_ref, title, title)).fetchone()
    if duplicate:
        raise StudioError("already_saved", "Este item já está salvo neste canal.", 409)
    identifier = new_id("opp")
    conn.execute("""INSERT INTO editorial_opportunities (id, managed_channel_id, title, note, video_id, channel_ref, item_type, niche, subniche, run_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 (identifier, channel_id, title, (note or "").strip()[:1000], video_id, channel_ref, item_type, niche, subniche, run_id, to_iso(now), to_iso(now)))
    conn.commit()
    return {"id": identifier}


def lab_link(channel_id: str, subject: str) -> str:
    return f"/lab?canal={quote(channel_id)}&assunto={quote(subject)}"
