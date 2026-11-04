"""Regras comuns: de onde vêm os dados, qual canal pode recebê-los e como reportar falhas da API."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

from ..config import Settings
from ..connectors.quota import BudgetExceeded
from ..connectors.youtube_data import QuotaExceeded, YouTubeApiError, YouTubeDataClient
from ..logging_safe import redact
from ..studio.store import StudioError, get_channel

ClientFactory = Callable[[Settings, sqlite3.Connection], YouTubeDataClient]
DEMO_LINKS = {"chn_demo_cronicas": "DEMO_UC00", "chn_demo_imperios": "DEMO_UC05", "chn_demo_rotas": "DEMO_UC03"}


def data_origin(settings: Settings) -> str:
    return "demo" if settings.mode == "demo" else "youtube"


def default_client(settings: Settings, conn: sqlite3.Connection) -> YouTubeDataClient:
    if not settings.youtube_api_key:
        raise StudioError("api_key_missing", "Configure YOUTUBE_API_KEY para pesquisar no YouTube. Veja o README, seção Modo real.", 424)
    return YouTubeDataClient(settings, conn)


@contextmanager
def youtube_errors() -> Iterator[None]:
    """Traduz falhas da API em erros legíveis. A chave nunca aparece: as mensagens passam por redact."""
    try:
        yield
    except BudgetExceeded as error:
        raise StudioError("quota_local", f"{error} Tente depois da virada do dia de cota, à meia-noite do Pacífico.", 429) from error
    except QuotaExceeded as error:
        raise StudioError("quota_google", redact(error), 429) from error
    except YouTubeApiError as error:
        raise StudioError("youtube_error", redact(error), 502, retryable=True) from error


def compatible(channel: dict, settings: Settings) -> bool:
    """Canal real só recebe dado real; canal fictício só recebe dado fictício."""
    return bool(channel["is_demo"]) == (settings.mode == "demo")


def require_channel(studio: sqlite3.Connection, settings: Settings, channel_id: str | None) -> dict | None:
    """Confere o canal antes de associar dados de pesquisa a ele."""
    if not channel_id:
        return None
    channel = get_channel(studio, channel_id)
    if not compatible(channel, settings):
        message = ("Modo demonstração: canal real não recebe dados fictícios. Ligue o modo real para pesquisar para este canal."
                   if settings.mode == "demo" else "Canal fictício não recebe dados reais do YouTube.")
        raise StudioError("channel_data_mismatch", message, 409)
    return channel


def linked_research_channel(channel: dict) -> str | None:
    """ID do canal no banco de pesquisa. Canal fictício usa o par fictício."""
    return channel.get("youtube_channel_id") or DEMO_LINKS.get(channel["id"])


def csv_cell(value: object) -> str:
    """Texto externo não vira fórmula ao abrir a planilha."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text


def to_csv(header: Iterable[str], rows: Iterable[Iterable[object]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_cell(cell) for cell in row])
    return "﻿" + output.getvalue()


def loads(text: str | None, default):
    return json.loads(text) if text else default


def purge_channel(conn: sqlite3.Connection, channel_id: str) -> None:
    """Apaga do banco de pesquisa o que estava associado a um canal removido."""
    for table in ("research_runs", "keyword_lookups", "study_videos", "editorial_opportunities", "coach_conversations"):
        conn.execute(f"DELETE FROM {table} WHERE managed_channel_id = ?", (channel_id,))
    conn.commit()
