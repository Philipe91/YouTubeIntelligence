"""API do estúdio usada pelo dashboard. Escuta só em 127.0.0.1, como o restante do aplicativo."""
from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .. import demo
from ..config import Settings
from ..db import connect, migrate, utcnow
from ..deps import settings_dep
from ..policy import policy_state
from . import pipelines, recommend, simulator, status, store
from .contract import Contract

router = APIRouter(prefix="/api/studio")


def studio_error_response(error: store.StudioError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message, "retryable": error.retryable}})


_settings = settings_dep


def _seed_demo_activity(conn: sqlite3.Connection, settings: Settings) -> None:
    """Dá vida aos canais fictícios uma única vez: recomendações e fila simulada, tudo rotulado."""
    if settings.mode != "demo" or conn.execute("SELECT 1 FROM studio_meta WHERE key = 'demo_activity_seeded'").fetchone():
        return
    research = connect(settings.db_path)
    try:
        migrate(research)
        if not demo.is_seeded(research):
            demo.seed_demo(research, utcnow())
        existing = {channel["id"] for channel in store.list_channels(conn) if channel["is_demo"]}
        for channel_id in existing:
            recommend.generate(conn, research, settings, channel_id)
        contract = Contract(conn, settings)
        if "chn_demo_cronicas" in existing:
            first = store.list_recommendations(conn, "chn_demo_cronicas")[0]
            contract.start_production("chn_demo_cronicas", first["id"], "demo:cronicas", "agente_simulado", True)
        if "chn_demo_rotas" in existing:
            first = store.list_recommendations(conn, "chn_demo_rotas")[0]
            job = contract.start_production("chn_demo_rotas", first["id"], "demo:rotas", "agente_simulado", True)["job"]
            contract.authorize_job(job["id"], "chn_demo_rotas", "demonstracao")
            for _ in range(3):
                simulator.simulate_step(contract, job["id"], "chn_demo_rotas")
        conn.execute("INSERT INTO studio_meta (key, value) VALUES ('demo_activity_seeded', ?)", (utcnow().isoformat(),))
        conn.commit()
    finally:
        research.close()


def studio_conn(settings: Settings = Depends(_settings)) -> Iterator[sqlite3.Connection]:
    conn = store.open_studio(settings)
    try:
        store.seed_demo_once(conn)
        _seed_demo_activity(conn, settings)
        yield conn
    finally:
        conn.close()


def research_conn(settings: Settings = Depends(_settings)) -> Iterator[sqlite3.Connection | None]:
    """Banco de pesquisa do modo atual. No modo real, só é aberto se já existir."""
    conn = None
    if settings.mode == "demo" or settings.db_path.exists():
        conn = connect(settings.db_path)
        migrate(conn)
        if settings.mode == "demo" and not demo.is_seeded(conn):
            demo.seed_demo(conn, utcnow())
    try:
        yield conn
    finally:
        if conn:
            conn.close()


def _channel_summary(conn: sqlite3.Connection, channel: dict, settings: Settings, today: date) -> dict:
    channel_id = channel["id"]

    def count(sql: str) -> int:
        return conn.execute(sql, (channel_id,)).fetchone()[0]

    upcoming = conn.execute(
        "SELECT scheduled_on, title, format FROM calendar_entries WHERE channel_id = ? AND scheduled_on >= ? AND status IN ('planejado','em_producao','pronto_para_revisao') ORDER BY scheduled_on LIMIT 1",
        (channel_id, today.isoformat()),
    ).fetchone()
    return {
        **channel,
        "youtube_auth": status.youtube_auth_status(channel, settings),
        "open_recommendations": count("SELECT COUNT(*) FROM recommendations WHERE channel_id = ? AND status IN ('nova','aceita')"),
        "active_jobs": count("SELECT COUNT(*) FROM production_jobs WHERE channel_id = ? AND state IN ('awaiting_authorization','authorized','running','failed')"),
        "awaiting_authorization": count("SELECT COUNT(*) FROM production_jobs WHERE channel_id = ? AND state = 'awaiting_authorization'"),
        "packages_ready": count("SELECT COUNT(*) FROM production_jobs WHERE channel_id = ? AND state = 'package_ready'"),
        "history_count": count("SELECT COUNT(*) FROM video_history WHERE channel_id = ?"),
        "next_scheduled": dict(upcoming) if upcoming else None,
    }


@router.get("/overview")
def overview(conn=Depends(studio_conn), settings=Depends(_settings)):
    today = date.today()
    channels = [_channel_summary(conn, c, settings, today) for c in store.list_channels(conn)]
    contract = Contract(conn, settings)
    jobs = contract.list_jobs()["jobs"]
    upcoming = store.list_calendar(conn, None, today.isoformat(), (today + timedelta(days=14)).isoformat())
    return {
        "channels": channels, "jobs": jobs[:12],
        "upcoming": [e for e in upcoming if e["status"] in {"planejado", "em_producao", "pronto_para_revisao"}][:10],
        "claude": status.claude_status(conn), "mode": settings.mode,
        "policy": {"state": policy_state(settings).state, "derived_allowed": policy_state(settings).derived_allowed},
    }


class ChannelBody(BaseModel):
    fields: dict[str, Any]


@router.post("/channels", status_code=201)
def create_channel(body: ChannelBody, conn=Depends(studio_conn)):
    return store.create_channel(conn, body.fields)


@router.get("/channels/{channel_id}")
def channel_detail(channel_id: str, conn=Depends(studio_conn), settings=Depends(_settings)):
    channel = store.get_channel(conn, channel_id)
    summary = _channel_summary(conn, channel, settings, date.today())
    return {
        **summary,
        "competitors": store.list_competitors(conn, channel_id),
        "history": store.list_history(conn, channel_id),
        "claude": status.claude_status(conn, channel_id),
        "policy": {"state": policy_state(settings).state, "derived_allowed": policy_state(settings).derived_allowed},
        "mode": settings.mode,
    }


@router.patch("/channels/{channel_id}")
def patch_channel(channel_id: str, body: ChannelBody, conn=Depends(studio_conn)):
    return store.update_channel(conn, channel_id, body.fields)


class DeleteBody(BaseModel):
    confirm_name: str


@router.post("/channels/{channel_id}/delete")
def delete_channel(channel_id: str, body: DeleteBody, conn=Depends(studio_conn)):
    store.delete_channel(conn, channel_id, body.confirm_name)
    return {"deleted": channel_id}


class CompetitorBody(BaseModel):
    name: str
    youtube_ref: str | None = None
    notes: str = ""


@router.post("/channels/{channel_id}/competitors", status_code=201)
def add_competitor(channel_id: str, body: CompetitorBody, conn=Depends(studio_conn)):
    return store.add_competitor(conn, channel_id, body.name, body.youtube_ref, body.notes)


@router.post("/channels/{channel_id}/competitors/{item_id}/delete")
def delete_competitor(channel_id: str, item_id: str, conn=Depends(studio_conn)):
    store.remove_scoped(conn, "competitors", channel_id, item_id)
    return {"deleted": item_id}


class HistoryBody(BaseModel):
    title: str
    format: str
    published_on: str
    url: str | None = None
    views: int | None = None
    result_notes: str = ""


@router.post("/channels/{channel_id}/history", status_code=201)
def add_history(channel_id: str, body: HistoryBody, conn=Depends(studio_conn)):
    return store.add_history(conn, channel_id, title=body.title, format=body.format, published_on=body.published_on,
                             url=body.url, views=body.views, result_notes=body.result_notes)


@router.post("/channels/{channel_id}/history/{item_id}/delete")
def delete_history(channel_id: str, item_id: str, conn=Depends(studio_conn)):
    store.remove_scoped(conn, "video_history", channel_id, item_id)
    return {"deleted": item_id}


@router.get("/channels/{channel_id}/recommendations")
def recommendations(channel_id: str, state: str | None = None, conn=Depends(studio_conn)):
    return {"items": store.list_recommendations(conn, channel_id, state)}


@router.post("/channels/{channel_id}/recommendations/generate")
def generate(channel_id: str, conn=Depends(studio_conn), research=Depends(research_conn), settings=Depends(_settings)):
    return recommend.generate(conn, research, settings, channel_id)


class StatusBody(BaseModel):
    status: str


@router.post("/channels/{channel_id}/recommendations/{recommendation_id}/status")
def recommendation_status(channel_id: str, recommendation_id: str, body: StatusBody, conn=Depends(studio_conn)):
    return store.set_recommendation_status(conn, channel_id, recommendation_id, body.status)


class StartBody(BaseModel):
    simulated: bool = True
    idempotency_key: str | None = None


@router.post("/channels/{channel_id}/recommendations/{recommendation_id}/produce", status_code=201)
def produce(channel_id: str, recommendation_id: str, body: StartBody, conn=Depends(studio_conn), settings=Depends(_settings)):
    # Pedido humano pela interface. Mesmo assim, tarefa real fica aguardando autorização explícita.
    return Contract(conn, settings).start_production(channel_id, recommendation_id, body.idempotency_key or uuid.uuid4().hex, "dono_local", body.simulated)


class OwnerRecommendationBody(BaseModel):
    subject: str
    justification: str
    format: str
    duration_seconds: int | None = None
    target_audience: str = ""
    editorial_priority: str = "media"


@router.post("/channels/{channel_id}/recommendations", status_code=201)
def create_recommendation(channel_id: str, body: OwnerRecommendationBody, conn=Depends(studio_conn)):
    return recommend.create_owner_recommendation(conn, channel_id, subject=body.subject, justification=body.justification, video_format=body.format,
                                                 duration_seconds=body.duration_seconds, target_audience=body.target_audience, priority=body.editorial_priority)


@router.post("/channels/{channel_id}/recommendations/{recommendation_id}/titles")
def generate_titles(channel_id: str, recommendation_id: str, conn=Depends(studio_conn)):
    return recommend.generate_titles(conn, channel_id, recommendation_id)


class BriefingBody(BaseModel):
    chosen_title: str
    planned_on: str | None = None


@router.post("/channels/{channel_id}/recommendations/{recommendation_id}/briefing", status_code=201)
def approve_briefing(channel_id: str, recommendation_id: str, body: BriefingBody, conn=Depends(studio_conn)):
    return recommend.approve_briefing(conn, channel_id, recommendation_id, body.chosen_title, body.planned_on)


class DispatchBody(BaseModel):
    idempotency_key: str


@router.post("/channels/{channel_id}/briefings/{briefing_id}/dispatch", status_code=201)
def dispatch(channel_id: str, briefing_id: str, body: DispatchBody, conn=Depends(studio_conn), settings=Depends(_settings)):
    return Contract(conn, settings).dispatch_briefing(channel_id, briefing_id, body.idempotency_key)


@router.get("/channels/{channel_id}/cockpit")
def cockpit(channel_id: str, conn=Depends(studio_conn), settings=Depends(_settings)):
    contract = Contract(conn, settings)
    data = contract.channel_cockpit(channel_id)
    today = date.today()
    open_items = store.list_recommendations(conn, channel_id, "aceita") + store.list_recommendations(conn, channel_id, "nova")
    upcoming = store.list_calendar(conn, channel_id, today.isoformat(), (today + timedelta(days=60)).isoformat())
    next_item = open_items[0] if open_items else None
    briefing = None
    if next_item:
        row = conn.execute("SELECT * FROM briefings WHERE recommendation_id = ?", (next_item["id"],)).fetchone()
        briefing = recommend.briefing_view(row)
    return {**data, "next_recommendation": next_item, "briefing": briefing,
            "upcoming": [e for e in upcoming if e["status"] != "cancelado"][:6]}


@router.post("/channels/{channel_id}/alerts/{event_id}/acknowledge")
def acknowledge(channel_id: str, event_id: int, conn=Depends(studio_conn), settings=Depends(_settings)):
    return Contract(conn, settings).acknowledge_alert(channel_id, event_id)


@router.get("/channels/{channel_id}/pipeline")
def pipeline(channel_id: str, conn=Depends(studio_conn)):
    channel = store.get_channel(conn, channel_id)
    return {"plan": pipelines.plan_for(channel["pipeline_profile"], "", channel_id), "options": pipelines.profile_options()}


@router.get("/channels/{channel_id}/jobs/{job_id}/artifacts/{artifact_id}")
def download_artifact(channel_id: str, job_id: str, artifact_id: str, conn=Depends(studio_conn), settings=Depends(_settings)):
    path, name = Contract(conn, settings).artifact_file(channel_id, job_id, artifact_id)
    # Sempre como download: o conteúdo do arquivo nunca é interpretado pelo navegador.
    return FileResponse(path, media_type="application/octet-stream", filename=name, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/calendar")
def calendar(start: str, end: str, channel_id: str | None = None, conn=Depends(studio_conn)):
    return {"entries": store.list_calendar(conn, channel_id, start, end)}


class CalendarBody(BaseModel):
    scheduled_on: str
    title: str
    format: str
    notes: str = ""
    recommendation_id: str | None = None


@router.post("/channels/{channel_id}/calendar", status_code=201)
def add_calendar(channel_id: str, body: CalendarBody, conn=Depends(studio_conn)):
    return store.add_calendar(conn, channel_id, scheduled_on=body.scheduled_on, title=body.title, format=body.format,
                              notes=body.notes, recommendation_id=body.recommendation_id)


class CalendarPatch(BaseModel):
    scheduled_on: str | None = None
    status: str | None = None


@router.patch("/channels/{channel_id}/calendar/{entry_id}")
def patch_calendar(channel_id: str, entry_id: str, body: CalendarPatch, conn=Depends(studio_conn)):
    return store.update_calendar(conn, channel_id, entry_id, scheduled_on=body.scheduled_on, status=body.status)


@router.post("/channels/{channel_id}/calendar/{entry_id}/delete")
def delete_calendar(channel_id: str, entry_id: str, conn=Depends(studio_conn)):
    store.remove_scoped(conn, "calendar_entries", channel_id, entry_id)
    return {"deleted": entry_id}


@router.get("/jobs")
def jobs(channel_id: str | None = None, state: str | None = Query(default=None), conn=Depends(studio_conn), settings=Depends(_settings)):
    return Contract(conn, settings).list_jobs(channel_id, state)


@router.get("/channels/{channel_id}/jobs/{job_id}")
def job_detail(channel_id: str, job_id: str, conn=Depends(studio_conn), settings=Depends(_settings)):
    return Contract(conn, settings).get_job(job_id, channel_id)


@router.post("/channels/{channel_id}/jobs/{job_id}/{action}")
def job_action(channel_id: str, job_id: str, action: str, conn=Depends(studio_conn), settings=Depends(_settings)):
    contract = Contract(conn, settings)
    actions = {
        "authorize": lambda: contract.authorize_job(job_id, channel_id),
        "cancel": lambda: contract.cancel_job(job_id, channel_id),
        "retry": lambda: contract.retry_job(job_id, channel_id),
        "simulate-step": lambda: simulator.simulate_step(contract, job_id, channel_id),
        "simulate-failure": lambda: simulator.simulate_failure(contract, job_id, channel_id),
    }
    if action not in actions:
        raise store.StudioError("unknown_action", "Ação desconhecida.", 404)
    return actions[action]()
