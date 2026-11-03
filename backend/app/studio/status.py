"""Estado das integrações. Só leitura e sem chamadas de rede: nada aqui consome cota ou memória extra."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..config import ROOT_DIR, Settings
from ..db import from_iso, utcnow


def _read_only_live(settings: Settings) -> sqlite3.Connection | None:
    path = settings.live_db_path
    if not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def youtube_auth_status(channel: dict, settings: Settings) -> dict:
    """Canal real: depende do OAuth registrado no banco do modo real. O token nunca é lido aqui."""
    if channel["is_demo"]:
        return {"state": "demo", "label": "Canal fictício", "detail": "Não existe no YouTube e não precisa de autenticação."}
    youtube_id = channel["youtube_channel_id"]
    if not youtube_id:
        return {"state": "not_linked", "label": "Sem vínculo", "detail": "Informe o ID do canal (UC...) nas configurações."}
    if not settings.oauth_client_secrets:
        return {"state": "oauth_not_configured", "label": "OAuth não configurado", "detail": "Configure o cliente OAuth e rode authorize-channel. Veja o README."}
    conn = None
    try:
        conn = _read_only_live(settings)
        row = conn.execute("SELECT last_authorization_check_at FROM oauth_channels WHERE channel_id = ?", (youtube_id,)).fetchone() if conn else None
    except sqlite3.Error:
        row = None
    finally:
        if conn:
            conn.close()
    if row is None:
        return {"state": "not_authorized", "label": "Não autorizado", "detail": "Rode authorize-channel com a conta deste canal."}
    days = settings.scoring["retention"]["authorization_check_days"]
    checked = row["last_authorization_check_at"]
    if utcnow() - from_iso(checked) >= timedelta(days=days):
        return {"state": "check_overdue", "label": "Verificação vencida", "detail": f"A autorização precisa ser conferida a cada {days} dias.", "checked_at": checked}
    return {"state": "authorized", "label": "Autorizado", "detail": "Acesso somente leitura.", "checked_at": checked}


def claude_status(conn: sqlite3.Connection, channel_id: str | None = None) -> dict[str, Any]:
    """Sinais locais. Não dispara o Claude nem o servidor MCP."""
    config = Path(ROOT_DIR) / ".mcp.json"
    data: dict[str, Any] = {
        "cli_found": shutil.which("claude") is not None,
        "mcp_configured": config.exists(),
        "contract_version": "yti.agent.v1",
    }
    if channel_id:
        rows = conn.execute("SELECT agent_id, last_operation, last_seen_at FROM agent_activity WHERE channel_id = ? ORDER BY last_seen_at DESC LIMIT 5", (channel_id,)).fetchall()
    else:
        rows = conn.execute("SELECT agent_id, channel_id, last_operation, last_seen_at FROM agent_activity ORDER BY last_seen_at DESC LIMIT 5").fetchall()
    data["recent_agents"] = [dict(r) for r in rows]
    data["simulated_only"] = all(r["agent_id"] == "agente_simulado" for r in rows) if rows else None
    return data
