"""API local. Escuta apenas em 127.0.0.1."""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import demo, services
from .ai.generation import GenerationError, generate_for_topic
from .config import Settings
from .db import connect, migrate, utcnow
from .deps import settings_dep
from .logging_safe import install_redaction, redact
from .policy import PolicyBlocked
from .scheduler import ensure_jobs
from .studio import router as studio_router
from .studio.store import StudioError

install_redaction()
log = logging.getLogger("yti.api")

app = FastAPI(title="YouTube Intelligence", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def conn_dep(settings: Settings = Depends(settings_dep)) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        migrate(conn)
        ensure_jobs(conn)
        if settings.mode == "demo" and not demo.is_seeded(conn):
            demo.seed_demo(conn, utcnow())
        yield conn
    finally:
        conn.close()


app.include_router(studio_router.router)


@app.exception_handler(StudioError)
def handle_studio_error(_request, error: StudioError):
    return studio_router.studio_error_response(error)


FormatParam = Query(default=None, pattern="^(short|long|live)$")


@app.get("/api/overview")
def overview(format: str | None = FormatParam, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.overview(conn, settings, format)


@app.get("/api/filters")
def filters(conn=Depends(conn_dep)):
    return services.filters(conn)


@app.get("/api/videos")
def videos(format: str | None = FormatParam, q: str | None = None, niche_id: int | None = None, language: str | None = None,
           country: str | None = None, channel_id: str | None = None, days: int | None = Query(default=None, ge=1),
           sort: str = Query(default="idr", pattern="^(idr|views|vph|recent)$"), limit: int = Query(default=100, ge=1, le=500),
           outliers_only: bool = False, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.list_videos(conn, settings, video_format=format, q=q, niche_id=niche_id, language=language, country=country,
                                channel_id=channel_id, days=days, sort=sort, limit=limit, outliers_only=outliers_only)


@app.get("/api/videos/{video_id}")
def video(video_id: str, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    result = services.video_detail(conn, settings, video_id)
    if result is None:
        raise HTTPException(404, "Vídeo não encontrado.")
    return result


@app.get("/api/channels")
def channels(conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.list_channels(conn, settings)


@app.get("/api/channels/compare")
def compare(format: str = Query(default="long", pattern="^(short|long)$"), conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.compare_channels(conn, settings, format)


@app.get("/api/channels/{channel_id}")
def channel(channel_id: str, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    result = services.channel_detail(conn, settings, channel_id)
    if result is None:
        raise HTTPException(404, "Canal não encontrado.")
    return result


@app.get("/api/trends")
def trends(format: str | None = FormatParam, niche_id: int | None = None, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.trends(conn, settings, format, niche_id)


@app.get("/api/opportunities")
def opportunities(format: str | None = FormatParam, niche_id: int | None = None, language: str | None = None, country: str | None = None,
                  conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.opportunities(conn, settings, video_format=format, niche_id=niche_id, language=language, country=country)


@app.get("/api/opportunities/detail")
def opportunity(topic: str, format: str = Query(pattern="^(short|long)$"), conn=Depends(conn_dep), settings=Depends(settings_dep)):
    result = services.opportunity_detail(conn, settings, topic, format)
    if result is None:
        raise HTTPException(404, "Tema não encontrado.")
    return result


class GenerateRequest(BaseModel):
    topic: str
    format: str


@app.post("/api/generate")
def generate(body: GenerateRequest, conn=Depends(conn_dep), settings=Depends(settings_dep)):
    if body.format not in {"short", "long"}:
        raise HTTPException(422, "Formato inválido.")
    try:
        return generate_for_topic(conn, settings, body.topic, body.format)
    except PolicyBlocked as error:
        raise HTTPException(403, str(error)) from error
    except GenerationError as error:
        raise HTTPException(502, redact(error)) from error


@app.get("/api/own-channels")
def own_channels(days: int = Query(default=28, ge=1, le=365), conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.own_channels(conn, settings, days)


@app.get("/api/system")
def system(conn=Depends(conn_dep), settings=Depends(settings_dep)):
    return services.system_status(conn, settings)
