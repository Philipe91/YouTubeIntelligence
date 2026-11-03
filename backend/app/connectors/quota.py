"""Registro de cota por balde. O dia de cota do YouTube vira à meia-noite do Pacífico."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..db import to_iso

PACIFIC = ZoneInfo("America/Los_Angeles")

# Custos da documentação (determine_quota_cost, consultada em 03/11/2026).
METHOD_COSTS: dict[str, tuple[str, int]] = {
    "search.list": ("search", 1),
    "videos.list": ("default", 1),
    "channels.list": ("default", 1),
    "playlistItems.list": ("default", 1),
}


class BudgetExceeded(RuntimeError):
    """O limite local configurado acabou; nenhuma chamada foi feita."""


def quota_day(moment: datetime) -> str:
    return moment.astimezone(PACIFIC).date().isoformat()


class QuotaLedger:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.limits = {"default": settings.quota_default_daily, "search": settings.quota_search_daily}

    def used(self, bucket: str, moment: datetime) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(units), 0) AS total FROM api_calls WHERE quota_day = ? AND bucket = ?",
            (quota_day(moment), bucket),
        ).fetchone()
        return int(row["total"])

    def check(self, method: str, moment: datetime) -> None:
        bucket, units = METHOD_COSTS[method]
        limit = self.limits[bucket]
        if self.used(bucket, moment) + units > limit:
            raise BudgetExceeded(f"Limite local de cota atingido no balde '{bucket}' ({limit} unidades por dia).")

    def record(self, api: str, method: str, bucket: str, units: int, status: int | None,
               reason: str | None, moment: datetime) -> None:
        self.conn.execute(
            "INSERT INTO api_calls (called_at, quota_day, api, method, bucket, units, status, error_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (to_iso(moment), quota_day(moment), api, method, bucket, units, status, reason),
        )
        self.conn.commit()

    def usage(self, moment: datetime) -> list[dict]:
        return [
            {"bucket": bucket, "used": self.used(bucket, moment), "limit": limit, "quota_day": quota_day(moment)}
            for bucket, limit in self.limits.items()
        ]
