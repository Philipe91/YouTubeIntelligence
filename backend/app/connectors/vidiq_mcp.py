"""Conexão opcional com o vidIQ MCP. Isolada: nenhum módulo principal depende dela.

Sem chamadas reais no MVP. Cada chamada consome créditos da sua conta vidIQ, por isso o
uso recomendado é no próprio Claude Code, sob pedido:
    claude mcp add --transport http vidiq https://mcp.vidiq.com/mcp
"""
from __future__ import annotations

from typing import Protocol


class VidiqProvider(Protocol):
    def status(self) -> dict: ...


class DisabledVidiqProvider:
    def status(self) -> dict:
        return {
            "enabled": False,
            "note": "Desligado. O aplicativo funciona sem vidIQ.",
            "how_to_enable": "claude mcp add --transport http vidiq https://mcp.vidiq.com/mcp",
        }
