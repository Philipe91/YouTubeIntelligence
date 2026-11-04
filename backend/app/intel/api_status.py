"""Situação da YouTube Data API: chave, teste de conexão, cota e última validação.

O teste roda no banco real (`live.sqlite`), porque a cota é do projeto no Google, mesmo com o painel em
modo demonstração. Nada do que volta é guardado como pesquisa, e o valor da chave nunca sai daqui.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from ..config import Settings
from ..connectors.quota import BudgetExceeded, QuotaLedger
from ..connectors.youtube_data import QuotaExceeded, YouTubeApiError, YouTubeDataClient
from ..connectors.youtube_shape import check_response
from ..db import connect, migrate, to_iso
from .common import FAILURES, ClientFactory

CHECK_HANDLE = "@YouTube"
CHECK_QUERY = "history documentary"
SETUP_DOC = "docs/CONFIGURAR_YOUTUBE_API.md"
SETUP_STEPS = [
    "No Google Cloud Console, crie um projeto só para este aplicativo.",
    "Em APIs e serviços, ative a YouTube Data API v3.",
    "Em Credenciais, crie uma chave de API e restrinja-a à YouTube Data API v3.",
    "Copie .env.example para .env na raiz do projeto e preencha YOUTUBE_API_KEY. Não cole a chave em conversas, prints ou commits.",
    "Para usar dados reais, defina YTI_MODE=live no mesmo arquivo e reinicie com scripts\\parar.ps1 e scripts\\iniciar.ps1.",
    "Volte aqui e clique em Testar conexão.",
]


def _open_live(settings: Settings) -> sqlite3.Connection:
    conn = connect(settings.live_db_path)
    migrate(conn)
    return conn


def _view(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {"checked_at": row["checked_at"], "ok": bool(row["ok"]), "kind": row["kind"], "message": row["message"], "target": row["target"],
            "details": json.loads(row["details_json"]), "title": FAILURES.get(row["kind"], ("Conexão confirmada", ""))[0] if not row["ok"] else "Conexão confirmada",
            "action": FAILURES.get(row["kind"], ("", ""))[1] if not row["ok"] else ""}


def status(settings: Settings, now: datetime) -> dict:
    """Só leitura. Com a chave ausente e nenhum banco real, nem abre o arquivo."""
    last = validated = None
    quota: list[dict] = []
    if settings.live_db_path.exists() or settings.youtube_api_key:
        conn = _open_live(settings)
        try:
            last = _view(conn.execute("SELECT * FROM api_checks ORDER BY id DESC LIMIT 1").fetchone())
            # Só conta consulta real ao Google, com dados de volta. Teste com API simulada nunca conta.
            validated = _view(conn.execute("SELECT * FROM api_checks WHERE ok = 1 AND target = 'google' ORDER BY id DESC LIMIT 1").fetchone())
            quota = QuotaLedger(conn, settings).usage(now)
        finally:
            conn.close()
    return {
        "mode": settings.mode, "key_configured": bool(settings.youtube_api_key), "target": settings.api_target, "last_check": last, "last_real_validation": validated,
        "validation_state": "validada" if validated else "pendente", "quota": quota, "setup_steps": SETUP_STEPS, "setup_doc": SETUP_DOC,
        "no_key": {"title": FAILURES["no_key"][0], "action": FAILURES["no_key"][1]},
    }


def _fields(availability: dict[str, int]) -> dict[str, int]:
    return dict(sorted(availability.items()))


def run_check(settings: Settings, factory: ClientFactory, now: datetime, with_search: bool = False) -> dict:
    """1 unidade sem a busca. Com ela, mais 1 chamada do balde de busca e 1 unidade."""
    conn = _open_live(settings)
    details: dict = {"handle": CHECK_HANDLE, "with_search": with_search, "steps": []}
    ok, kind, message = False, "no_key", "YOUTUBE_API_KEY não está configurada."
    client: YouTubeDataClient | None = None
    try:
        if settings.youtube_api_key:
            client = factory(settings, conn)
            data = client.check_channel(CHECK_HANDLE)
            report = check_response("channels.list", data)
            details["steps"].append({"method": "channels.list", "items": len(report.valid_items), "fields": _fields(report.availability)})
            if not report.valid_items:
                raise YouTubeApiError(f"channels.list não encontrou {CHECK_HANDLE}.", 200, kind="not_found")
            if with_search:
                found = client.search_videos(CHECK_QUERY, max_results=1)
                search_report = check_response("search.list", found)
                details["steps"].append({"method": "search.list", "items": len(search_report.valid_items), "fields": _fields(search_report.availability),
                                         "total_results_present": "totalResults" in found.get("pageInfo", {})})
                ids = [item["id"]["videoId"] for item in search_report.valid_items if item["id"].get("videoId")]
                if ids:
                    video_report = check_response("videos.list", client.videos(ids[:1]))
                    details["steps"].append({"method": "videos.list", "items": len(video_report.valid_items), "fields": _fields(video_report.availability)})
            details["provenance"] = client.provenance()
            ok, kind = True, "ok"
            message = "A API respondeu com dados reais." if settings.api_target == "google" else "A API simulada de teste respondeu. Isto não valida o YouTube."
    except BudgetExceeded as error:
        kind, message = "quota_local", str(error)
    except QuotaExceeded as error:
        kind, message = "quota", str(error)
    except YouTubeApiError as error:
        kind, message = (error.kind if error.kind in FAILURES else "api_error"), str(error)
    finally:
        if client is not None:
            client.close()
    conn.execute("INSERT INTO api_checks (checked_at, ok, kind, message, target, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                 (to_iso(now), int(ok), kind, message, settings.api_target, json.dumps(details, ensure_ascii=False)))
    conn.commit()
    result = _view(conn.execute("SELECT * FROM api_checks ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()
    return result


def real_validation_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM api_checks WHERE ok = 1 AND target = 'google' LIMIT 1").fetchone() is not None
