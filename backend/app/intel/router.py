"""API de inteligência. Leituras abertas só para a própria máquina; toda escrita exige o token da API local."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import demo
from ..config import Settings
from ..db import connect, migrate, utcnow
from ..deps import settings_dep
from ..metrics.text import normalize
from ..policy import policy_state
from ..scheduler import ensure_jobs
from ..studio.router import studio_conn
from ..studio.store import StudioError, get_channel, list_channels
from . import api_status, coach, competitors, discovery, explorer, feed, ideas, keywords, lab, research
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
        "mode": settings.mode, "derived_allowed": state.derived_allowed, "policy_state": state.state, "has_api_key": bool(settings.youtube_api_key), "api_target": settings.api_target,
        "channels": [{"id": c["id"], "name": c["name"], "is_demo": c["is_demo"], "language": c["language"], "niche": c["niche"]} for c in channels if compatible(c, settings)],
        "other_channels": [{"id": c["id"], "name": c["name"], "is_demo": c["is_demo"]} for c in channels if not compatible(c, settings)],
    }


# --- Conexão com a YouTube Data API ---------------------------------------------------------------

@router.get("/api-status")
def youtube_api_status(settings=Depends(settings_dep)):
    return api_status.status(settings, utcnow())


class ApiCheckBody(BaseModel):
    with_search: bool = False


@router.post("/api-status/check")
def youtube_api_check(body: ApiCheckBody, settings=Depends(settings_dep), factory=Depends(client_factory)):
    return api_status.run_check(settings, factory, utcnow(), body.with_search)


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


# --- Descoberta para canais dark ------------------------------------------------------------------

@router.get("/discovery/catalog")
def discovery_catalog():
    return discovery.catalog()


class DiscoverBody(BaseModel):
    target: str = "recent_videos"
    niche: str | None = None
    subniche: str | None = None
    text: str | None = None
    language: str | None = None
    country: str | None = None
    days: int | None = None
    format: str | None = None
    max_subscribers: int | None = None
    channel_id: str | None = None


@router.post("/discovery/search", status_code=201)
def discovery_search(body: DiscoverBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return discovery.discover(conn, studio, settings, target=body.target, niche=body.niche or None, subniche=body.subniche or None, free_text=body.text, language=body.language,
                              country=body.country, days=body.days, video_format=body.format or None, max_subscribers=body.max_subscribers, channel_id=body.channel_id or None, now=utcnow(), factory=factory)


@router.get("/discovery/runs/{run_id}")
def discovery_run(run_id: str, limit: int = Query(default=25, ge=1, le=50), offset: int = PageOffset, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return discovery.view(conn, studio, settings, run_id, limit=limit, offset=offset)


class SaveItemBody(BaseModel):
    item_type: str
    item_id: str | None = None
    text: str | None = None
    note: str = ""
    run_id: str | None = None


@router.post("/channels/{channel_id}/saved-items", status_code=201)
def saved_item_add(channel_id: str, body: SaveItemBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return discovery.save_item(conn, studio, settings, channel_id, item_type=body.item_type, item_id=body.item_id, text=body.text, note=body.note, run_id=body.run_id, now=utcnow())


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


# --- Outlier Explorer -----------------------------------------------------------------------------

@router.get("/explorer")
def explorer_search(q: str | None = None, days: int | None = Query(default=None, ge=1, le=3650), format: str = "long", sort: str = "views", only_above: bool = False,
                    min_views: int | None = Query(default=None, ge=0), limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db), settings=Depends(settings_dep)):
    return explorer.search(conn, settings, q=q, days=days, video_format=format, sort=sort, only_above=only_above, min_views=min_views, limit=limit, offset=offset)


@router.get("/channels/{channel_id}/study")
def study_list(channel_id: str, origin: str | None = None, limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    get_channel(studio, channel_id)
    return explorer.list_study(conn, settings, channel_id, origin=origin, limit=limit, offset=offset)


@router.get("/channels/{channel_id}/study/ids")
def study_id_list(channel_id: str, conn=Depends(research_db)):
    return {"ids": explorer.study_ids(conn, channel_id)}


@router.get("/channels/{channel_id}/study/compare")
def study_compare(channel_id: str, ids: str, conn=Depends(research_db), settings=Depends(settings_dep)):
    return explorer.compare_videos(conn, settings, channel_id, [item for item in ids.split(",") if item])


class StudyBody(BaseModel):
    video_id: str
    origin: str = "explorer"
    note: str = ""


@router.post("/channels/{channel_id}/study", status_code=201)
def study_add(channel_id: str, body: StudyBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return explorer.add_study(conn, studio, settings, channel_id, body.video_id, utcnow(), body.origin, body.note)


@router.post("/channels/{channel_id}/study/note")
def study_note(channel_id: str, body: StudyBody, conn=Depends(research_db)):
    explorer.update_study_note(conn, channel_id, body.video_id, body.note)
    return {"updated": body.video_id}


@router.post("/channels/{channel_id}/study/remove")
def study_remove(channel_id: str, body: StudyBody, conn=Depends(research_db)):
    explorer.remove_study(conn, channel_id, body.video_id)
    return {"removed": body.video_id}


# --- Competitor Intelligence ----------------------------------------------------------------------

@router.get("/channels/{channel_id}/competitors")
def competitor_overview(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return competitors.overview(conn, studio, settings, channel_id, utcnow())


@router.get("/channels/{channel_id}/competitors/report.md")
def competitor_report(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    body, filename = competitors.report(conn, studio, settings, channel_id, utcnow())
    return Response(content=body.encode("utf-8"), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})


@router.get("/channels/{channel_id}/competitors/{competitor_id}")
def competitor_detail(channel_id: str, competitor_id: str, limit: int = Query(default=20, ge=1, le=50), offset: int = PageOffset, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return competitors.detail(conn, studio, settings, channel_id, competitor_id, utcnow(), limit, offset)


class CompetitorBody(BaseModel):
    reference: str
    name: str = ""
    notes: str = ""


@router.post("/channels/{channel_id}/competitors", status_code=201)
def competitor_add(channel_id: str, body: CompetitorBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return competitors.add(conn, studio, settings, channel_id, body.reference, body.name, body.notes, utcnow(), factory)


@router.post("/channels/{channel_id}/competitors/{competitor_id}/link")
def competitor_link(channel_id: str, competitor_id: str, body: CompetitorBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return competitors.link(conn, studio, settings, channel_id, competitor_id, body.reference, utcnow(), factory)


@router.post("/channels/{channel_id}/competitors/{competitor_id}/refresh")
def competitor_refresh(channel_id: str, competitor_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), factory=Depends(client_factory)):
    return competitors.refresh(conn, studio, settings, channel_id, competitor_id, utcnow(), factory)


@router.get("/channels/{channel_id}/opportunities")
def opportunities(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn)):
    get_channel(studio, channel_id)
    return {"items": competitors.list_opportunities(conn, channel_id)}


class OpportunityBody(BaseModel):
    title: str
    note: str = ""
    video_id: str | None = None


@router.post("/channels/{channel_id}/opportunities", status_code=201)
def opportunity_add(channel_id: str, body: OpportunityBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return competitors.add_opportunity(conn, studio, settings, channel_id, body.title, body.note, body.video_id, utcnow())


@router.post("/channels/{channel_id}/opportunities/{opportunity_id}/discard")
def opportunity_discard(channel_id: str, opportunity_id: str, conn=Depends(research_db)):
    competitors.discard_opportunity(conn, channel_id, opportunity_id, utcnow())
    return {"discarded": opportunity_id}


class ToIdeaBody(BaseModel):
    format: str
    subject: str | None = None


@router.post("/channels/{channel_id}/opportunities/{opportunity_id}/idea", status_code=201)
def opportunity_idea(channel_id: str, opportunity_id: str, body: ToIdeaBody, conn=Depends(research_db), studio=Depends(studio_conn)):
    return competitors.opportunity_to_idea(conn, studio, channel_id, opportunity_id, body.format, utcnow(), body.subject)


# --- Ideias diárias -------------------------------------------------------------------------------

@router.get("/channels/{channel_id}/ideas")
def ideas_list(channel_id: str, filtro: str = "novas", limit: int = Query(default=20, ge=1, le=50), offset: int = PageOffset, studio=Depends(studio_conn)):
    return ideas.list_ideas(studio, channel_id, filter_name=filtro, limit=limit, offset=offset)


@router.post("/channels/{channel_id}/ideas/generate")
def ideas_generate(channel_id: str, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return ideas.generate(conn, studio, settings, channel_id, utcnow())


class IdeaAction(BaseModel):
    action: str


@router.post("/channels/{channel_id}/ideas/{idea_id}/act")
def ideas_act(channel_id: str, idea_id: str, body: IdeaAction, studio=Depends(studio_conn)):
    return ideas.act(studio, channel_id, idea_id, body.action)


class IdeaFavorite(BaseModel):
    favorite: bool


@router.post("/channels/{channel_id}/ideas/{idea_id}/favorite")
def ideas_favorite(channel_id: str, idea_id: str, body: IdeaFavorite, studio=Depends(studio_conn)):
    return ideas.set_favorite(studio, channel_id, idea_id, body.favorite, utcnow())


class IdeaSchedule(BaseModel):
    scheduled_on: str


@router.post("/channels/{channel_id}/ideas/{idea_id}/schedule")
def ideas_schedule(channel_id: str, idea_id: str, body: IdeaSchedule, studio=Depends(studio_conn)):
    return ideas.schedule(studio, channel_id, idea_id, body.scheduled_on, utcnow().date())


# --- AI Coach -------------------------------------------------------------------------------------

@router.get("/coach/status")
def coach_status(settings=Depends(settings_dep)):
    return coach.provider_status(settings)


@router.get("/channels/{channel_id}/coach")
def coach_list(channel_id: str, limit: int = PageLimit, offset: int = PageOffset, conn=Depends(research_db), studio=Depends(studio_conn)):
    get_channel(studio, channel_id)
    return coach.list_conversations(conn, channel_id, limit, offset)


@router.get("/channels/{channel_id}/coach/{conversation_id}")
def coach_get(channel_id: str, conversation_id: str, conn=Depends(research_db)):
    return coach.get_conversation(conn, channel_id, conversation_id)


class CoachBody(BaseModel):
    question: str
    conversation_id: str | None = None


def coach_provider():
    """Testes trocam por um provedor falso."""
    return None


@router.post("/channels/{channel_id}/coach", status_code=201)
def coach_ask(channel_id: str, body: CoachBody, conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep), provider=Depends(coach_provider)):
    return coach.ask(conn, studio, settings, channel_id, body.question, body.conversation_id, utcnow(), provider)


class RenameBody(BaseModel):
    title: str


@router.post("/channels/{channel_id}/coach/{conversation_id}/rename")
def coach_rename(channel_id: str, conversation_id: str, body: RenameBody, conn=Depends(research_db)):
    coach.rename_conversation(conn, channel_id, conversation_id, body.title, utcnow())
    return {"renamed": conversation_id}


@router.post("/channels/{channel_id}/coach/{conversation_id}/delete")
def coach_delete(channel_id: str, conversation_id: str, conn=Depends(research_db)):
    coach.delete_conversation(conn, channel_id, conversation_id)
    return {"deleted": conversation_id}


# --- Title & Thumbnail Lab ------------------------------------------------------------------------

class EvaluateBody(BaseModel):
    title: str
    subject: str = ""


@router.post("/lab/evaluate")
def lab_evaluate(body: EvaluateBody):
    return lab.evaluate_title(body.title, body.subject)


class ProjectBody(BaseModel):
    subject: str
    recommendation_id: str | None = None


@router.get("/channels/{channel_id}/lab/projects")
def lab_projects(channel_id: str, limit: int = PageLimit, offset: int = PageOffset, studio=Depends(studio_conn)):
    return lab.list_projects(studio, channel_id, limit, offset)


@router.post("/channels/{channel_id}/lab/projects", status_code=201)
def lab_create(channel_id: str, body: ProjectBody, studio=Depends(studio_conn)):
    return lab.create_project(studio, channel_id, body.subject, body.recommendation_id, utcnow())


@router.get("/channels/{channel_id}/lab/projects/{project_id}")
def lab_project(channel_id: str, project_id: str, conn=Depends(research_db), studio=Depends(studio_conn)):
    forbidden = {normalize(row["title"]) for row in conn.execute("SELECT title FROM videos")}
    return lab.get_project(studio, channel_id, project_id, forbidden)


@router.post("/channels/{channel_id}/lab/projects/{project_id}/delete")
def lab_delete_project(channel_id: str, project_id: str, studio=Depends(studio_conn), settings=Depends(settings_dep)):
    lab.delete_project(studio, settings, channel_id, project_id)
    return {"deleted": project_id}


class VariationBody(BaseModel):
    title: str
    note: str = ""


@router.post("/channels/{channel_id}/lab/projects/{project_id}/variations", status_code=201)
def lab_add_variation(channel_id: str, project_id: str, body: VariationBody, studio=Depends(studio_conn)):
    return lab.add_variation(studio, channel_id, project_id, body.title, body.note, utcnow())


class VariationPatch(BaseModel):
    note: str | None = None
    favorite: bool | None = None


@router.post("/channels/{channel_id}/lab/variations/{variation_id}/update")
def lab_update_variation(channel_id: str, variation_id: str, body: VariationPatch, studio=Depends(studio_conn)):
    return lab.update_variation(studio, channel_id, variation_id, note=body.note, favorite=body.favorite, now=utcnow())


@router.post("/channels/{channel_id}/lab/variations/{variation_id}/delete")
def lab_delete_variation(channel_id: str, variation_id: str, studio=Depends(studio_conn), settings=Depends(settings_dep)):
    lab.delete_variation(studio, settings, channel_id, variation_id)
    return {"deleted": variation_id}


@router.post("/channels/{channel_id}/lab/variations/{variation_id}/image")
async def lab_image(channel_id: str, variation_id: str, request: Request, studio=Depends(studio_conn), settings=Depends(settings_dep)):
    """Corpo com os bytes da imagem. O tamanho declarado é conferido antes de ler, e o lido, depois."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > lab.MAX_IMAGE_BYTES:
        raise StudioError("image_too_large", "A imagem passa de 5 MB.", 413)
    return lab.attach_image(studio, settings, channel_id, variation_id, await request.body(), utcnow())


@router.get("/channels/{channel_id}/lab/images/{file_name}")
def lab_image_file(channel_id: str, file_name: str, studio=Depends(studio_conn), settings=Depends(settings_dep)):
    return FileResponse(lab.image_path(studio, settings, channel_id, file_name), media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})


# --- Smart Dashboard ------------------------------------------------------------------------------

@router.get("/feed")
def smart_feed(channel_id: str | None = None, format: str = Query(default="long", pattern="^(short|long)$"), conn=Depends(research_db), studio=Depends(studio_conn), settings=Depends(settings_dep)):
    ensure_jobs(conn)
    return feed.build(conn, studio, settings, channel_id, format)
