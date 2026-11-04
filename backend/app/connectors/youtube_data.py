"""YouTube Data API v3: cache, rate limit, retry e controle de cota."""
from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx

from ..config import Settings
from ..db import from_iso, to_iso, utcnow
from ..logging_safe import redact
from .quota import QuotaLedger
from .youtube_shape import check_response

BASE_URL = "https://www.googleapis.com/youtube/v3"
MAX_ATTEMPTS = 4
MIN_SECONDS_BETWEEN_CALLS = 0.1
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}
RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "RATE_LIMIT_EXCEEDED"}
# Formato real, capturado do Google em 04/11/2026: chave inválida volta como HTTP 400, com `reason`
# igual a `badRequest` em errors[] e o motivo verdadeiro em details[].reason.
KEY_INVALID_REASONS = {"API_KEY_INVALID", "keyInvalid", "API_KEY_EXPIRED", "keyExpired"}
KEY_RESTRICTED_REASONS = {"API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED", "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_IOS_APP_BLOCKED", "ipRefererBlocked"}
API_DISABLED_REASONS = {"accessNotConfigured", "SERVICE_DISABLED"}

# Cache curto: a política pede dados atuais, e o snapshot sempre ignora o cache.
CACHE_TTL_SECONDS = {
    "search.list": 6 * 3600,
    "channels.list": 6 * 3600,
    "playlistItems.list": 3600,
    "videos.list": 900,
}


class YouTubeApiError(RuntimeError):
    """`kind` diz o que fazer: chave, cota, rede, formato ou o próprio pedido."""

    kind = "api_error"

    def __init__(self, message: str, status: int | None = None, reason: str | None = None, kind: str | None = None):
        super().__init__(redact(message))
        self.status = status
        self.reason = reason
        if kind:
            self.kind = kind


class QuotaExceeded(YouTubeApiError):
    """O Google recusou por falta de cota. Repetir não adianta."""

    kind = "quota"


class CredentialError(YouTubeApiError):
    """Chave ausente, inválida, restrita ou API desligada no projeto. Repetir não adianta."""


class NetworkError(YouTubeApiError):
    kind = "network"


class ResponseFormatError(YouTubeApiError):
    """HTTP 200 com conteúdo que não dá para usar. Não entra no cache."""

    kind = "format"


def response_reasons(response: httpx.Response) -> tuple[list[str], str]:
    """Todos os motivos que o Google informou, e a mensagem. Corpo fora do padrão devolve listas vazias."""
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return [], ""
    if not isinstance(error, dict):
        return [], ""
    reasons = [item.get("reason") for item in error.get("errors") or [] if isinstance(item, dict)]
    reasons += [item.get("reason") for item in error.get("details") or [] if isinstance(item, dict)]
    if error.get("status"):
        reasons.append(error["status"])
    return [reason for reason in reasons if reason], str(error.get("message") or "")


def classify_failure(status: int, reasons: list[str], message: str) -> str:
    found = set(reasons)
    lowered = message.lower()
    if found & QUOTA_REASONS or ("exceeded your" in lowered and "quota" in lowered):
        return "quota"
    if found & KEY_INVALID_REASONS or "api key not valid" in lowered or "api key expired" in lowered:
        return "key_invalid"
    if found & KEY_RESTRICTED_REASONS:
        return "key_restricted"
    if found & API_DISABLED_REASONS:
        return "api_disabled"
    if "API_KEY_MISSING" in found or "unregistered callers" in lowered:
        return "key_missing"
    if status == 429 or found & RATE_REASONS:
        return "rate_limited"
    if status >= 500:
        return "server"
    if status == 404:
        return "not_found"
    if status == 403:
        return "forbidden"
    return "bad_request"


class YouTubeDataClient:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utcnow,
    ):
        if not settings.youtube_api_key:
            raise YouTubeApiError("YOUTUBE_API_KEY não configurada. Veja o README, seção Modo real.")
        self.settings = settings
        self.conn = conn
        self.ledger = QuotaLedger(conn, settings)
        self.sleep = sleep
        self.clock = clock
        self._last_call = 0.0
        self._http = httpx.Client(base_url=settings.youtube_base_url or BASE_URL, timeout=30.0, transport=transport)
        self.trace: list[dict] = []
        self.warnings: list[str] = []
        self.availability: dict[str, dict[str, int]] = {}
        self.last_fetched_at: datetime | None = None

    def close(self) -> None:
        self._http.close()

    def _cache_key(self, method: str, params: dict[str, Any]) -> str:
        payload = json.dumps([method, sorted(params.items())], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _read_cache(self, key: str, now: datetime) -> tuple[dict, datetime] | None:
        row = self.conn.execute(
            "SELECT response_json, fetched_at, expires_at FROM api_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row and from_iso(row["expires_at"]) > now:
            return json.loads(row["response_json"]), from_iso(row["fetched_at"])
        return None

    def provenance(self) -> dict:
        """De onde veio o que esta sessão usou: quantas chamadas novas, quanto do cache e de quando."""
        fetched = [item["fetched_at"] for item in self.trace]
        return {
            "source": "api_simulada_teste" if self.settings.youtube_base_url else "youtube_data_api",
            "api_calls": sum(1 for item in self.trace if item["source"] == "api"),
            "search_api_calls": sum(1 for item in self.trace if item["source"] == "api" and item["method"] == "search.list"),
            "cache_hits": sum(1 for item in self.trace if item["source"] == "cache"),
            "methods": sorted({item["method"] for item in self.trace}),
            "oldest_data_at": min(fetched) if fetched else None,
            "newest_data_at": max(fetched) if fetched else None,
            "warnings": list(dict.fromkeys(self.warnings))[:10],
        }

    def _write_cache(self, key: str, data: dict, method: str, now: datetime) -> None:
        expires = now + timedelta(seconds=CACHE_TTL_SECONDS[method])
        self.conn.execute(
            "INSERT OR REPLACE INTO api_cache (cache_key, response_json, fetched_at, expires_at) VALUES (?, ?, ?, ?)",
            (key, json.dumps(data), to_iso(now), to_iso(expires)),
        )
        self.conn.commit()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            self.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        self._last_call = time.monotonic()

    def request(self, method: str, path: str, params: dict[str, Any], use_cache: bool = True) -> dict:
        clean = {key: value for key, value in params.items() if value is not None}
        key = self._cache_key(method, clean)
        if use_cache:
            cached = self._read_cache(key, self.clock())
            if cached is not None:
                self.last_fetched_at = cached[1]
                self.trace.append({"method": method, "source": "cache", "fetched_at": to_iso(cached[1])})
                return cached[0]

        bucket, units = self.ledger.cost(method)
        last_error: YouTubeApiError | None = None
        for attempt in range(MAX_ATTEMPTS):
            # Toda tentativa consome cota, inclusive as inválidas.
            self.ledger.check(method, self.clock())
            self._throttle()
            try:
                response = self._http.get(path, params={**clean, "key": self.settings.youtube_api_key})
            except httpx.TransportError as error:
                self.ledger.record("data", method, bucket, 0, None, type(error).__name__, self.clock())
                last_error = NetworkError(f"Falha de rede em {method}: {type(error).__name__}")
                self._backoff(attempt, None)
                continue

            reasons, google_message = ([], "") if response.status_code == 200 else response_reasons(response)
            kind = None if response.status_code == 200 else classify_failure(response.status_code, reasons, google_message)
            reason = self._main_reason(reasons)
            if kind == "quota":
                reason = next((item for item in reasons if item in QUOTA_REASONS), "quotaExceeded")
            self.ledger.record("data", method, bucket, units, response.status_code, reason, self.clock())
            if response.status_code == 200:
                return self._accept(method, key, response)
            if kind == "quota":
                raise QuotaExceeded(f"Cota do Google esgotada em {method}.", response.status_code, reason)
            message = f"{method} retornou HTTP {response.status_code} ({reason or 'sem motivo'})."
            if kind in {"key_invalid", "key_restricted", "api_disabled", "key_missing"}:
                raise CredentialError(message, response.status_code, reason, kind)
            last_error = YouTubeApiError(message, response.status_code, reason, kind)
            if kind not in {"rate_limited", "server"}:
                raise last_error
            self._backoff(attempt, response.headers.get("retry-after"))
        raise last_error or YouTubeApiError(f"{method} falhou.")

    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        if attempt >= MAX_ATTEMPTS - 1:
            return
        if retry_after and retry_after.isdigit():
            self.sleep(float(retry_after))
        else:
            self.sleep(2**attempt + random.random())

    def _accept(self, method: str, key: str, response: httpx.Response) -> dict:
        """Só entra no cache o que tem formato utilizável. Item incompleto fica de fora e é relatado."""
        try:
            data = response.json()
        except ValueError as error:
            raise ResponseFormatError(f"{method} devolveu HTTP 200 sem JSON válido.", 200) from error
        report = check_response(method, data)
        if report.fatal:
            raise ResponseFormatError(report.fatal, 200)
        if report.rejected:
            data = {**data, "items": report.valid_items}
            self.warnings.extend(report.problems[:5])
        self.availability[method] = report.availability
        moment = self.clock()
        self._write_cache(key, data, method, moment)
        self.last_fetched_at = moment
        self.trace.append({"method": method, "source": "api", "fetched_at": to_iso(moment)})
        return data

    @staticmethod
    def _main_reason(reasons: list[str]) -> str | None:
        """O motivo específico de details[] vale mais que o genérico `badRequest` de errors[]."""
        generic = {"badRequest", "forbidden", "INVALID_ARGUMENT", "PERMISSION_DENIED"}
        return next((reason for reason in reasons if reason not in generic), reasons[0] if reasons else None)

    def search_videos(self, query: str, language: str | None = None, country: str | None = None,
                      published_after: str | None = None, published_before: str | None = None,
                      order: str = "relevance", max_results: int = 50, page_token: str | None = None) -> dict:
        return self.request("search.list", "/search", {
            "part": "snippet", "type": "video", "q": query, "relevanceLanguage": language, "regionCode": country,
            "publishedAfter": published_after, "publishedBefore": published_before, "order": order,
            "maxResults": max_results, "pageToken": page_token,
        })

    def search_channels(self, query: str, language: str | None = None, country: str | None = None, max_results: int = 25) -> dict:
        return self.request("search.list", "/search", {
            "part": "snippet", "type": "channel", "q": query, "relevanceLanguage": language, "regionCode": country, "maxResults": max_results,
        })

    def videos(self, ids: list[str], use_cache: bool = True) -> dict:
        if len(ids) > 50:
            raise ValueError("videos.list aceita até 50 IDs por chamada")
        return self.request("videos.list", "/videos", {
            # player + maxHeight devolvem o tamanho do player, único sinal público de proporção.
            "part": "snippet,contentDetails,statistics,liveStreamingDetails,player", "id": ",".join(ids),
            "maxHeight": 720,
        }, use_cache=use_cache)

    def check_channel(self, handle: str) -> dict:
        """A consulta mais barata que traz dados reais: 1 unidade, sem cache."""
        return self.request("channels.list", "/channels", {"part": "snippet,contentDetails,statistics", "forHandle": handle}, use_cache=False)

    def channels(self, ids: list[str] | None = None, handle: str | None = None, use_cache: bool = True) -> dict:
        return self.request("channels.list", "/channels", {
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids) if ids else None, "forHandle": handle,
        }, use_cache=use_cache)

    def playlist_items(self, playlist_id: str, page_token: str | None = None) -> dict:
        return self.request("playlistItems.list", "/playlistItems", {
            "part": "contentDetails", "playlistId": playlist_id, "maxResults": 50, "pageToken": page_token,
        })
