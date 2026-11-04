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

BASE_URL = "https://www.googleapis.com/youtube/v3"
MAX_ATTEMPTS = 4
MIN_SECONDS_BETWEEN_CALLS = 0.1
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}
RATE_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}

# Cache curto: a política pede dados atuais, e o snapshot sempre ignora o cache.
CACHE_TTL_SECONDS = {
    "search.list": 6 * 3600,
    "channels.list": 6 * 3600,
    "playlistItems.list": 3600,
    "videos.list": 900,
}


class YouTubeApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, reason: str | None = None):
        super().__init__(redact(message))
        self.status = status
        self.reason = reason


class QuotaExceeded(YouTubeApiError):
    """O Google recusou por falta de cota. Repetir não adianta."""


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
        self._http = httpx.Client(base_url=BASE_URL, timeout=30.0, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _cache_key(self, method: str, params: dict[str, Any]) -> str:
        payload = json.dumps([method, sorted(params.items())], default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _read_cache(self, key: str, now: datetime) -> dict | None:
        row = self.conn.execute(
            "SELECT response_json, expires_at FROM api_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row and from_iso(row["expires_at"]) > now:
            return json.loads(row["response_json"])
        return None

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
                return cached

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
                last_error = YouTubeApiError(f"Falha de rede em {method}: {type(error).__name__}")
                self._backoff(attempt, None)
                continue

            reason = self._error_reason(response)
            self.ledger.record("data", method, bucket, units, response.status_code, reason, self.clock())
            if response.status_code == 200:
                data = response.json()
                self._write_cache(key, data, method, self.clock())
                return data
            if reason in QUOTA_REASONS:
                raise QuotaExceeded(f"Cota do Google esgotada em {method}.", response.status_code, reason)
            retryable = response.status_code in {429, 500, 502, 503, 504} or reason in RATE_REASONS
            message = f"{method} retornou HTTP {response.status_code} ({reason or 'sem motivo'})."
            last_error = YouTubeApiError(message, response.status_code, reason)
            if not retryable:
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

    @staticmethod
    def _error_reason(response: httpx.Response) -> str | None:
        if response.status_code == 200:
            return None
        try:
            errors = response.json().get("error", {}).get("errors", [])
            return errors[0].get("reason") if errors else None
        except (ValueError, AttributeError):
            return None

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
            "part": "snippet,contentDetails,statistics,liveStreamingDetails,player", "id": ",".join(ids), "maxResults": 50,
            "maxHeight": 720,
        }, use_cache=use_cache)

    def channels(self, ids: list[str] | None = None, handle: str | None = None, use_cache: bool = True) -> dict:
        return self.request("channels.list", "/channels", {
            "part": "snippet,contentDetails,statistics", "id": ",".join(ids) if ids else None, "forHandle": handle,
            "maxResults": 50,
        }, use_cache=use_cache)

    def playlist_items(self, playlist_id: str, page_token: str | None = None) -> dict:
        return self.request("playlistItems.list", "/playlistItems", {
            "part": "contentDetails", "playlistId": playlist_id, "maxResults": 50, "pageToken": page_token,
        })
