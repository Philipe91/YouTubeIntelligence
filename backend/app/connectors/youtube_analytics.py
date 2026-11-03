"""YouTube Analytics API v2, apenas para canais próprios autorizados.

CTR e impressões de thumbnail não constam da lista de métricas da API e não são solicitados.
Não testado com conta real: o formato da consulta segue a documentação e foi validado só com mocks.
"""
from __future__ import annotations

import httpx

from ..logging_safe import redact

REPORTS_URL = "https://youtubeanalytics.googleapis.com/v2/reports"
DAILY_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost"
)


class AnalyticsError(RuntimeError):
    pass


def fetch_daily_by_content_type(access_token: str, start_date: str, end_date: str,
                                transport: httpx.BaseTransport | None = None) -> list[dict]:
    with httpx.Client(timeout=60.0, transport=transport) as client:
        response = client.get(
            REPORTS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "ids": "channel==MINE", "startDate": start_date, "endDate": end_date, "metrics": DAILY_METRICS,
                "dimensions": "day,creatorContentType", "sort": "day",
            },
        )
    if response.status_code != 200:
        raise AnalyticsError(redact(f"Analytics retornou HTTP {response.status_code}."))
    body = response.json()
    columns = [header["name"] for header in body.get("columnHeaders", [])]
    return [dict(zip(columns, row)) for row in body.get("rows", [])]
