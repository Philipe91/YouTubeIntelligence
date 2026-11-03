"""Dependências compartilhadas da API."""
from __future__ import annotations

from .config import Settings, get_settings


def settings_dep() -> Settings:
    return get_settings()
