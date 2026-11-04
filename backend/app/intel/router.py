"""API de inteligência. Leituras abertas só para a própria máquina; toda escrita exige o token da API local."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from .. import demo
from ..config import Settings
from ..db import connect, migrate, utcnow
from ..deps import settings_dep
from ..policy import policy_state
from ..studio.router import studio_conn
from ..studio.store import list_channels
from . import keywords, research
from .common import ClientFactory, compatible, default_client

router = APIRouter(prefix="/api/intel")


def research_db(settings: Settings = Depends(settings_dep)) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        migrate(conn)
        if settings.mode == "demo":
            if not demo.is_seeded(conn):
                demo.seed_demo(conn, utcnow())
            keywords.seed_demo_terms(conn, utcnow())
        yield conn
    finally:
        conn.close()


def client_factory() -> ClientFactory:
    """Testes trocam a fábrica por uma com transporte falso."""
    return default_client


def csv_response(body: str, filename: str) -> Response:
    return Response(content=body.encode("utf-8"), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})


PageLimit = Query(default=30, ge=1, le=100)
PageOffset = Query(default=0, ge=0)


@router.get("/context")
def context(studio=Depends(studio_conn), settings=Depends(settings_dep)):
    """Canais que podem receber os dados do modo atual, e o que está disponível agora."""
    state = policy_state(settings)
    channels = list_channels(studio)
    return {
        "mode": settings.mode, "derived_allowed": state.derived_allowed, "policy_state": state.state, "has_api_key": bool(settings.youtube_api_key),
        "channels": [{"id": c["id"], "name": c["name"], "is_demo": c["is_demo"], "language": c["language"], "niche": c["niche"]} for c in channels if compatible(c, settings)],
        "other_channels": [{"id": c["id"], "name": c["name"], "is_demo": c["is_demo"]} for c in channels if not compatible(c, settings)],
    }


class SearchBody(BaseModel):
    kind: str = "videos"
    query: str
    channel_id: str | None = None
    language: str | None = None
    country: str | None = None
    days: int | None = None
    format: str | None = None
    order: str = "relevance"
    max_subscribers: int | None = None


@router.post("/research/search", status_code=201)
def search(body: SearchBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return research.run_search(conn, studio, settings, kind=body.kind, query=body.query, channel_id=body.channel_id or None, now=utcnow(),
                               language=body.language, country=body.country, days=body.days, video_format=body.format or None, order=body.order,
                               max_subscribers=body.max_subscribers, factory=factory)


@router.get("/research/runs")
def runs(channel_id: str | None = None, saved: bool | None = None, limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db)):
    return research.list_runs(conn, channel_id=channel_id, saved=saved, limit=limit, offset=offset)


@router.get("/research/compare")
def compare(a: str, b: str, channel_id: str | None = None, conn=Depends(research_db)):
    return research.compare_runs(conn, a, b, channel_id)


@router.get("/research/growing")
def growing(q: str | None = None, format: str | None = Query(default=None, pattern="^(short|long)$"), conn=Depends(research_db), settings=Depends(settings_dep)):
    return research.growing_topics(conn, settings, q, format)


@router.get("/research/runs/{run_id}")
def run(run_id: str, channel_id: str | None = None, limit: int = Query(default=50, ge=1, le=100), offset: int = PageOffset, conn=Depends(research_db), settings=Depends(settings_dep)):
    return research.run_items(conn, settings, run_id, channel_id=channel_id, limit=limit, offset=offset)


@router.get("/research/runs/{run_id}/export.csv")
def export(run_id: str, channel_id: str | None = None, conn=Depends(research_db), settings=Depends(settings_dep)):
    return csv_response(*research.export_csv(conn, settings, run_id, channel_id))


class SaveBody(BaseModel):
    name: str | None = None


@router.post("/research/runs/{run_id}/save")
def save(run_id: str, body: SaveBody, conn=Depends(research_db)):
    return research.save_run(conn, run_id, body.name)


@router.post("/research/runs/{run_id}/rerun", status_code=201)
def rerun(run_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return research.rerun(conn, studio, settings, run_id, utcnow(), factory)


@router.post("/research/runs/{run_id}/delete")
def delete_run(run_id: str, conn=Depends(research_db)):
    research.delete_run(conn, run_id)
    return {"deleted": run_id}


class LookupBody(BaseModel):
    term: str
    channel_id: str | None = None
    fetch: bool = True


@router.post("/keywords/lookup")
def keyword_lookup(body: LookupBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return keywords.lookup(conn, studio, settings, body.term, body.channel_id or None, utcnow(), body.fetch, factory)


@router.get("/keywords/analyze")
def keyword_analyze(term: str, channel_id: str | None = None, limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return keywords.analyze(conn, studio, settings, term, channel_id, utcnow(), limit=limit, offset=offset)


@router.get("/keywords/history")
def keyword_history(channel_id: str | None = None, limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db)):
    return keywords.history(conn, channel_id, limit, offset)


@router.get("/channels/{channel_id}/keywords/favorites")
def favorites(channel_id: str, studio=Depends(studio_conn)):
    return {"items": keywords.list_favorites(studio, channel_id)}


@router.get("/channels/{channel_id}/keywords/favorites.csv")
def favorites_csv(channel_id: str, studio=Depends(studio_conn)):
    return csv_response(*keywords.favorites_csv(studio, channel_id))


class FavoriteBody(BaseModel):
    term: str
    note: str = ""


@router.post("/channels/{channel_id}/keywords/favorites", status_code=201)
def add_favorite(channel_id: str, body: FavoriteBody, studio=Depends(studio_conn)):
    return keywords.add_favorite(studio, channel_id, body.term, body.note, utcnow())


@router.post("/channels/{channel_id}/keywords/favorites/remove")
def remove_favorite(channel_id: str, body: FavoriteBody, studio=Depends(studio_conn)):
    keywords.remove_favorite(studio, channel_id, body.term)
    return {"removed": body.term}


@router.get("/channels/{channel_id}/keywords/own-terms")
def own_terms(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return keywords.own_terms(conn, studio, settings, channel_id)


@router.get("/channels/{channel_id}/keywords/for-you")
def for_you(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return keywords.for_channel(conn, studio, settings, channel_id)
