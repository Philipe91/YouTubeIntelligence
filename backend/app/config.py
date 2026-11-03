"""Configuração: variáveis de ambiente (.env) e parâmetros de scoring (TOML)."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DEFAULT_SCORING_PATH = BACKEND_DIR / "config" / "scoring.toml"


def load_scoring(path: Path = DEFAULT_SCORING_PATH) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    youtube_api_key: str = ""
    oauth_client_secrets: str = ""
    approval_ref: str = ""
    ai_provider: str = "none"
    ai_model: str = "claude-opus-5-5"
    quota_default_daily: int = 9000
    quota_search_daily: int = 90
    data_dir: Path = ROOT_DIR / "data"
    scoring: dict[str, Any] = field(default_factory=load_scoring)

    @property
    def db_path(self) -> Path:
        # Um arquivo por modo: dado fictício não se mistura com dado real.
        return self.data_dir / ("live.sqlite" if self.mode == "live" else "demo.sqlite")


def get_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env", override=False)
    mode = os.getenv("YTI_MODE", "demo").strip().lower()
    if mode not in {"demo", "live"}:
        raise ValueError("YTI_MODE deve ser 'demo' ou 'live'")
    return Settings(
        mode=mode,
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        oauth_client_secrets=os.getenv("YOUTUBE_OAUTH_CLIENT_SECRETS", "").strip(),
        approval_ref=os.getenv("YTI_DERIVED_METRICS_APPROVAL_REF", "").strip(),
        ai_provider=os.getenv("YTI_AI_PROVIDER", "none").strip().lower(),
        ai_model=os.getenv("YTI_AI_MODEL", "claude-opus-5-5").strip(),
        quota_default_daily=int(os.getenv("YTI_QUOTA_DEFAULT_DAILY", "9000")),
        quota_search_daily=int(os.getenv("YTI_QUOTA_SEARCH_DAILY", "90")),
    )
