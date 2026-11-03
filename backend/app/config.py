"""Configuração: variáveis de ambiente (.env), scoring, cotas e registro de conformidade."""
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
DEFAULT_QUOTA_PATH = BACKEND_DIR / "config" / "quota.toml"
DEFAULT_COMPLIANCE_PATH = BACKEND_DIR / "config" / "compliance.toml"
LEGACY_APPROVAL_ENV = "YTI_DERIVED_METRICS_APPROVAL_REF"


def load_scoring(path: Path = DEFAULT_SCORING_PATH) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_quota(path: Path = DEFAULT_QUOTA_PATH) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


@dataclass(frozen=True)
class ComplianceRecord:
    """Declaração do operador. O aplicativo não consegue confirmá-la com o Google."""

    status: str = "not_requested"
    use_case: str = ""
    amendment_accepted: bool = False
    compliance_audit_passed: bool = False
    google_case_ref: str = ""
    approved_on: str = ""
    review_by: str = ""
    approved_scopes: tuple[str, ...] = ()
    declared_by: str = ""
    load_error: str = ""


def load_compliance(path: Path = DEFAULT_COMPLIANCE_PATH) -> ComplianceRecord:
    """Falha fechada: arquivo ausente ou inválido nunca libera nada."""
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return ComplianceRecord(
            status=str(data.get("status", "not_requested")),
            use_case=str(data.get("use_case", "")),
            amendment_accepted=data.get("amendment_accepted") is True,
            compliance_audit_passed=data.get("compliance_audit_passed") is True,
            google_case_ref=str(data.get("google_case_ref", "")).strip(),
            approved_on=str(data.get("approved_on", "")).strip(),
            review_by=str(data.get("review_by", "")).strip(),
            approved_scopes=tuple(str(item) for item in data.get("approved_scopes", [])),
            declared_by=str(data.get("declared_by", "")).strip(),
        )
    except (OSError, tomllib.TOMLDecodeError, TypeError) as error:
        return ComplianceRecord(status="invalid", load_error=type(error).__name__)


@dataclass(frozen=True)
class Settings:
    mode: str = "demo"
    youtube_api_key: str = ""
    oauth_client_secrets: str = ""
    ai_provider: str = "none"
    ai_model: str = "claude-opus-5-5"
    quota_default_daily: int | None = None
    quota_search_daily: int | None = None
    quota_overrides: dict[str, int] = field(default_factory=dict)
    data_dir: Path = ROOT_DIR / "data"
    artifact_roots: tuple[str, ...] = ()
    legacy_approval_env_set: bool = False
    scoring: dict[str, Any] = field(default_factory=load_scoring)
    quota: dict[str, Any] = field(default_factory=load_quota)
    compliance: ComplianceRecord = field(default_factory=load_compliance)

    @property
    def db_path(self) -> Path:
        # Um arquivo por modo: dado fictício não se mistura com dado real.
        return self.data_dir / ("live.sqlite" if self.mode == "live" else "demo.sqlite")

    @property
    def live_db_path(self) -> Path:
        return self.data_dir / "live.sqlite"

    @property
    def studio_db_path(self) -> Path:
        # Cadastros dos seus canais: independem do modo e não guardam dados da API.
        return self.data_dir / "studio.sqlite"

    def quota_limits(self) -> dict[str, int]:
        """Limite local por balde, nunca acima do limite conhecido do Google."""
        limits: dict[str, int] = {}
        for name, bucket in self.quota["buckets"].items():
            value = self.quota_overrides.get(name, bucket["local_daily"])
            if name == "default" and self.quota_default_daily is not None:
                value = self.quota_default_daily
            if name == "search" and self.quota_search_daily is not None:
                value = self.quota_search_daily
            google = bucket.get("google_daily")
            limits[name] = max(0, min(value, google) if google is not None else value)
        return limits


def get_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env", override=False)
    mode = os.getenv("YTI_MODE", "demo").strip().lower()
    if mode not in {"demo", "live"}:
        raise ValueError("YTI_MODE deve ser 'demo' ou 'live'")
    quota = load_quota()
    overrides: dict[str, int] = {}
    for bucket in quota["buckets"]:
        raw = os.getenv(f"YTI_QUOTA_{bucket.upper()}_DAILY", "").strip()
        if raw:
            overrides[bucket] = int(raw)
    data_dir = os.getenv("YTI_DATA_DIR", "").strip()
    roots = tuple(item.strip() for item in os.getenv("YTI_ARTIFACT_ROOTS", "").split(";") if item.strip())
    extra: dict[str, Any] = {"data_dir": Path(data_dir)} if data_dir else {}
    return Settings(
        mode=mode,
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        oauth_client_secrets=os.getenv("YOUTUBE_OAUTH_CLIENT_SECRETS", "").strip(),
        ai_provider=os.getenv("YTI_AI_PROVIDER", "none").strip().lower(),
        ai_model=os.getenv("YTI_AI_MODEL", "claude-opus-5-5").strip(),
        quota_overrides=overrides,
        artifact_roots=roots,
        legacy_approval_env_set=bool(os.getenv(LEGACY_APPROVAL_ENV, "").strip()),
        quota=quota,
        **extra,
    )
