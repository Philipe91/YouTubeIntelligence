"""Keyword Intelligence.

Quatro campos nunca se misturam: volume medido, estimativa de provedor, índice experimental
próprio e indisponível. Nenhuma API pública do YouTube informa volume de busca, então os dois
primeiros ficam indisponíveis enquanto não houver um provedor legítimo configurado.
"""
from __future__ import annotations

import itertools
import sqlite3
from collections import Counter
from datetime import datetime
from typing import Protocol

from .. import services
from ..config import Settings
from ..db import from_iso, to_iso
from ..metrics.opportunity import OpportunityInput, compute_opportunity
from ..metrics.text import normalize, terms, tokens
from ..policy import BLOCK_REASON, ORIGIN_NOTE, policy_state
from ..studio.store import StudioError, get_channel, list_history
from . import research
from .common import ClientFactory, compatible, data_origin, default_client, linked_research_channel, require_channel, to_csv

NO_VOLUME = "Nenhuma API pública do YouTube informa volume de busca."
NO_PROVIDER = "Nenhum provedor de estimativa está configurado. Este aplicativo não inventa esse número."
INDEX_NOTE = ("Índice experimental deste aplicativo, de 0 a 100, feito com views dos vídeos encontrados. "
              "É relativo e mede atenção a vídeos, não buscas. Não é volume nem previsão.")
MIN_TERM_VIDEOS = 2
MAX_SAMPLE = 30

MODIFIERS = {
    "pt": ["explicado", "resumo", "história", "curiosidades", "documentário", "para iniciantes", "o que foi", "verdade sobre"],
    "es": ["explicado", "resumen", "historia", "curiosidades", "documental", "para principiantes", "qué fue", "la verdad sobre"],
    "en": ["explained", "summary", "history", "facts", "documentary", "for beginners", "what was", "truth about"],
}
QUESTIONS = {
    "pt": ["O que é {t}?", "Por que {t} importa?", "Como funciona {t}?", "Qual é a origem de {t}?", "Quem está por trás de {t}?", "O que quase ninguém sabe sobre {t}?"],
    "es": ["¿Qué es {t}?", "¿Por qué importa {t}?", "¿Cómo funciona {t}?", "¿Cuál es el origen de {t}?", "¿Quién está detrás de {t}?", "¿Qué casi nadie sabe sobre {t}?"],
    "en": ["What is {t}?", "Why does {t} matter?", "How does {t} work?", "Where did {t} come from?", "Who is behind {t}?", "What does almost nobody know about {t}?"],
}


class VolumeProvider(Protocol):
    """Ponto de ligação de um provedor legítimo de estimativas. Nenhum vem configurado."""

    name: str

    def estimate(self, term: str, language: str | None) -> int | None: ...


def _lang(language: str | None) -> str:
    code = (language or "pt").split("-")[0].lower()
    return code if code in MODIFIERS else "en"


def clean_term(term: str) -> str:
    text = " ".join((term or "").split())
    if not 2 <= len(text) <= 100:
        raise StudioError("invalid_field", "O termo precisa ter de 2 a 100 caracteres.")
    if not tokens(text):
        raise StudioError("invalid_field", "Use ao menos uma palavra com significado no termo.")
    return text


def variations(term: str, language: str | None) -> list[dict]:
    """Geradas por regra a partir do próprio termo. Nenhuma foi medida."""
    words = term.split()
    seen = {normalize(term)}
    items: list[dict] = []

    def push(text: str, rule: str) -> None:
        key = normalize(text)
        if key not in seen:
            seen.add(key)
            items.append({"term": text, "rule": rule})

    if 2 <= len(words) <= 3:
        for order in itertools.permutations(words):
            push(" ".join(order), "Mesmas palavras em outra ordem")
    for modifier in MODIFIERS[_lang(language)]:
        rule = "Com palavra de intenção"
        push(f"{modifier} {term}" if modifier.split()[0].lower() in {"o", "qué", "what", "verdade", "la", "truth"} else f"{term} {modifier}", rule)
    return items[:14]


def model_questions(term: str, language: str | None) -> list[str]:
    return [pattern.format(t=term) for pattern in QUESTIONS[_lang(language)]]


def _sample(conn: sqlite3.Connection, settings: Settings, term: str) -> list[sqlite3.Row]:
    wanted = set(tokens(term))
    return [r for r in conn.execute(services.VIDEO_SELECT) if wanted <= set(tokens(r["title"]))]


def _volume(term: str, language: str | None, provider: VolumeProvider | None) -> dict:
    estimate = provider.estimate(term, language) if provider else None
    return {
        "measured": services.metric(None, "unavailable", "YouTube", NO_VOLUME),
        "provider_estimate": (services.metric(estimate, "estimated", f"Estimativa de {provider.name}, não é dado do YouTube")
                              if estimate is not None else services.metric(None, "unavailable", "Provedor de estimativas", NO_PROVIDER)),
    }


def _index(conn: sqlite3.Connection, settings: Settings, term: str, rows: list[sqlite3.Row], vocabulary: tuple[str, ...], now: datetime) -> dict:
    """Índice experimental por formato. Bloqueado quando a política não libera métricas derivadas."""
    if not policy_state(settings).derived_allowed:
        return {"blocked": True, "reason": BLOCK_REASON, "note": INDEX_NOTE, "formats": []}
    analysis = services.analyze(conn, settings)
    subscribers = services._latest_subscribers(conn)
    samples = tuple(services._sample_video(row, analysis, subscribers, now) for row in rows)
    output = []
    for video_format in ("short", "long"):
        item = compute_opportunity(OpportunityInput(term, video_format, samples, vocabulary, None), settings.scoring["opportunity"])
        output.append({
            "format": video_format, "status": item.status, "sample_size": item.sample_size, "distinct_channels": item.distinct_channels,
            "index": services.metric(item.score, "estimated", "Índice experimental deste aplicativo",
                                     None if item.score is not None else "Amostra pequena para calcular."),
            "attention": services.metric(item.demand, "estimated", "Proxy: mediana de views por dia dos vídeos encontrados",
                                         None if item.demand is not None else "Sem views na amostra."),
            "competition": services.metric(item.competition, "estimated", "Porte dos canais e oferta recente",
                                           None if item.competition is not None else "Sem dados na amostra."),
            "relevance": services.metric(item.relevance, "calculated", "Palavras do termo no perfil do canal"),
            "confidence": services.metric(item.confidence, "calculated", "Amostra, diversidade de canais, cobertura de snapshots"),
            "justification": list(item.justification),
        })
    return {"blocked": False, "reason": None, "note": INDEX_NOTE, "origin_note": ORIGIN_NOTE, "formats": output}


def _related_counts(rows: list[sqlite3.Row], term: str) -> list[dict]:
    wanted = set(tokens(term))
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(item for item in terms(row["title"]) if not (set(item.split()) <= wanted))
    return [{"term": item, "videos": count} for item, count in counts.most_common(20) if count >= MIN_TERM_VIDEOS]


def _profile_terms(channel: dict | None, term: str) -> list[dict]:
    """Palavras que você mesmo cadastrou no perfil. Não vêm da API."""
    if channel is None:
        return []
    wanted = set(tokens(term))
    return [{"term": item, "reason": "Palavra do perfil do canal"} for item in channel["keywords"] if not set(tokens(item)) <= wanted][:15]


def analyze(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, term: str, channel_id: str | None, now: datetime,
            provider: VolumeProvider | None = None, limit: int = MAX_SAMPLE, offset: int = 0) -> dict:
    """Só leitura: não consome cota nem grava histórico."""
    text = clean_term(term)
    channel = require_channel(studio, settings, channel_id)
    language = channel["language"] if channel else "pt"
    rows = _sample(conn, settings, text)
    analysis = services.analyze(conn, settings)
    videos = [services._video_row(r, analysis, settings) for r in rows]
    videos.sort(key=lambda v: v["views"]["value"] or -1, reverse=True)
    allowed = policy_state(settings).derived_allowed
    vocabulary = tuple(channel["keywords"]) if channel else ()
    question_titles = [v for v in videos if "?" in v["title"]][:15]
    rising = research.growing_topics(conn, settings, text)
    is_favorite = bool(channel and studio.execute("SELECT 1 FROM keyword_favorites WHERE channel_id = ? AND term = ?", (channel["id"], text)).fetchone())
    last = conn.execute("SELECT MAX(executed_at) AS at FROM research_runs WHERE query = ? AND data_origin = ?", (text, data_origin(settings))).fetchone()["at"]
    return {
        "term": text, "language": language, "channel_id": channel_id, "fictional": settings.mode == "demo", "is_favorite": is_favorite,
        "volume": _volume(text, language, provider), "index": _index(conn, settings, text, rows, vocabulary, now),
        "sample": {"total": len(videos), "limit": limit, "offset": offset, "videos": videos[offset:offset + limit],
                   "note": "Vídeos já coletados com todas as palavras do termo, em qualquer ordem. Não é a busca completa do YouTube."},
        "last_youtube_search_at": last if settings.mode == "live" else None,
        "related": {
            "from_titles": _related_counts(rows, text) if allowed else [],
            "from_titles_blocked": not allowed, "from_titles_reason": None if allowed else BLOCK_REASON,
            "from_profile": _profile_terms(channel, text),
        },
        "variations": {"items": variations(text, language), "note": "Geradas por regra a partir do termo. Nenhuma foi medida."},
        "questions": {"from_model": model_questions(text, language), "model_note": "Modelos de pergunta, não buscas reais.",
                      "from_titles": [{"id": v["id"], "title": v["title"], "channel_title": v["channel_title"], "source_url": v["source_url"]} for v in question_titles]},
        "rising": rising,
    }


def lookup(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, term: str, channel_id: str | None, now: datetime,
           fetch: bool = True, factory: ClientFactory = default_client) -> dict:
    """Registra a pesquisa. No modo real, gasta uma chamada de busca quando há chave e `fetch` está ligado."""
    text = clean_term(term)
    channel = require_channel(studio, settings, channel_id)
    run = None
    fetch_error = None
    if fetch and settings.mode == "live":
        try:
            run = research.run_search(conn, studio, settings, kind="videos", query=text, channel_id=channel_id, now=now,
                                      language=channel["language"] if channel else None, factory=factory)
        except StudioError as error:
            if error.code not in {"api_key_missing", "quota_local", "quota_google", "youtube_error"}:
                raise
            # Falha da fonte não impede a análise local: a tela diz o que aconteceu.
            fetch_error = {"code": error.code, "message": error.message}
    conn.execute("INSERT INTO keyword_lookups (managed_channel_id, term, language, data_origin, looked_up_at) VALUES (?, ?, ?, ?, ?)",
                 (channel_id, text, channel["language"] if channel else None, data_origin(settings), to_iso(now)))
    conn.commit()
    return {"term": text, "run_id": run["id"] if run else None, "fetch_error": fetch_error}


def history(conn: sqlite3.Connection, channel_id: str | None, limit: int = 30, offset: int = 0) -> dict:
    where, params = ("WHERE managed_channel_id = ?", [channel_id]) if channel_id else ("", [])
    rows = conn.execute(f"SELECT * FROM keyword_lookups {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    total = conn.execute(f"SELECT COUNT(*) AS n FROM keyword_lookups {where}", params).fetchone()["n"]
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


def list_favorites(studio: sqlite3.Connection, channel_id: str) -> list[dict]:
    get_channel(studio, channel_id)
    return [dict(r) for r in studio.execute("SELECT term, note, created_at FROM keyword_favorites WHERE channel_id = ? ORDER BY created_at DESC, term", (channel_id,))]


def add_favorite(studio: sqlite3.Connection, channel_id: str, term: str, note: str, now: datetime) -> dict:
    get_channel(studio, channel_id)
    text = clean_term(term)
    studio.execute("INSERT INTO keyword_favorites (channel_id, term, note, created_at) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(channel_id, term) DO UPDATE SET note = excluded.note", (channel_id, text, note.strip()[:300], to_iso(now)))
    studio.commit()
    return {"channel_id": channel_id, "term": text}


def remove_favorite(studio: sqlite3.Connection, channel_id: str, term: str) -> None:
    cursor = studio.execute("DELETE FROM keyword_favorites WHERE channel_id = ? AND term = ?", (channel_id, term))
    studio.commit()
    if cursor.rowcount == 0:
        raise StudioError("not_found", "Favorito não encontrado neste canal.", 404)


def favorites_csv(studio: sqlite3.Connection, channel_id: str) -> tuple[str, str]:
    rows = [(item["term"], item["note"], item["created_at"]) for item in list_favorites(studio, channel_id)]
    return to_csv(("termo", "nota", "criado_em"), rows), f"palavras_{channel_id}.csv"


def own_terms(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str) -> dict:
    """Termos reais de descoberta, vindos do YouTube Analytics. Exigem OAuth do canal."""
    channel = get_channel(studio, channel_id)
    if not compatible(channel, settings):
        return {"available": False, "items": [], "reason": "Modo demonstração: canal real não recebe dados fictícios."}
    research_id = linked_research_channel(channel)
    if not research_id:
        return {"available": False, "items": [], "reason": "Informe o ID do YouTube do canal e autorize o acesso com OAuth para ver estes termos."}
    latest = conn.execute("SELECT MAX(period_end) AS end FROM own_search_terms WHERE channel_id = ?", (research_id,)).fetchone()["end"]
    if not latest:
        return {"available": False, "items": [], "reason": "Ainda sem termos coletados. Exige OAuth do canal e a sincronização do Analytics."}
    rows = conn.execute("SELECT term, views, minutes_watched, period_start, period_end, fetched_at FROM own_search_terms WHERE channel_id = ? AND period_end = ? ORDER BY views DESC",
                        (research_id, latest)).fetchall()
    return {"available": True, "reason": None, "fictional": settings.mode == "demo", "source": "YouTube Analytics (insightTrafficSourceDetail)",
            "items": [{"term": r["term"], "views": services.metric(r["views"], "measured", "YouTube Analytics", as_of=r["fetched_at"]),
                       "minutes_watched": services.metric(r["minutes_watched"], "measured", "YouTube Analytics", as_of=r["fetched_at"]),
                       "period_start": r["period_start"], "period_end": r["period_end"]} for r in rows]}


def for_channel(conn: sqlite3.Connection, studio: sqlite3.Connection, settings: Settings, channel_id: str) -> dict:
    """Recomendações por canal. Cada item diz de onde saiu, e nada usa dado de outro canal."""
    channel = get_channel(studio, channel_id)
    items: list[dict] = []
    seen: set[str] = set()

    def push(term: str, reason: str, origin: str) -> None:
        key = normalize(term)
        if key not in seen and not any(set(tokens(a)) and set(tokens(a)) <= set(tokens(term)) for a in channel["avoid"]):
            seen.add(key)
            items.append({"term": term, "reason": reason, "origin": origin})

    usable = compatible(channel, settings)
    terms_found = own_terms(conn, studio, settings, channel_id)
    for item in terms_found["items"][:5]:
        push(item["term"], "As pessoas já acham o canal por este termo.", "analytics")
    for item in list_favorites(studio, channel_id)[:5]:
        push(item["term"], "Você marcou como favorito.", "favorito")
    covered: set[str] = set()
    for video in list_history(studio, channel_id):
        covered.update(tokens(video["title"]))
    for keyword in channel["keywords"]:
        if not set(tokens(keyword)) & covered:
            push(keyword, "Está no perfil e ainda não aparece no histórico de vídeos.", "perfil")
    for subject in channel["topic_backlog"][:5]:
        push(subject, "Está no backlog editorial do canal.", "backlog")
    blocked = False
    if usable:
        data = services.trends(conn, settings)
        blocked = bool(data.get("blocked"))
        wanted = {token for keyword in channel["keywords"] for token in tokens(keyword)}
        for trend in data.get("items", []):
            if wanted & set(tokens(trend["term"])):
                push(trend["term"], f"{trend['accelerating']} de {trend['videos']} vídeos monitorados ganham velocidade, em {trend['channels']} canais.", "tendencia")
    return {"channel_id": channel_id, "items": items[:20], "trends_blocked": blocked, "trends_reason": BLOCK_REASON if blocked else None,
            "uses_research": usable, "fictional": usable and settings.mode == "demo"}


def seed_demo_terms(conn: sqlite3.Connection, now: datetime) -> None:
    """Termos fictícios para demonstrar a aba de descoberta. Sempre rotulados como fictícios."""
    if conn.execute("SELECT 1 FROM intel_meta WHERE key = 'demo_terms'").fetchone():
        return
    day = now.date().isoformat()
    start = (from_iso(to_iso(now))).replace(day=1).date().isoformat()
    if conn.execute("SELECT 1 FROM channels WHERE id = 'DEMO_UC00'").fetchone():
        for term, views, minutes in (("história de roma animada", 4200, 15200), ("vikings não usavam chifres", 2100, 6100),
                                     ("peste negra explicada", 1600, 5200), ("como era viver em roma", 980, 3300)):
            conn.execute("INSERT OR IGNORE INTO own_search_terms (channel_id, term, views, minutes_watched, period_start, period_end, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         ("DEMO_UC00", term, views, minutes, start, day, to_iso(now)))
    conn.execute("INSERT INTO intel_meta (key, value) VALUES ('demo_terms', ?)", (to_iso(now),))
    conn.commit()


