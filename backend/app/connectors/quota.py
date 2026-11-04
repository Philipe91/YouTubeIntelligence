"""Registro de cota por balde, configurado em config/quota.toml.

O dia de cota do YouTube vira à meia-noite do Pacífico. Método desconhecido ou proibido
falha antes de qualquer chamada.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..db import to_iso

PACIFIC = ZoneInfo("America/Los_Angeles")


class BudgetExceeded(RuntimeError):
    """O limite local configurado acabou; nenhuma chamada foi feita."""


class ForbiddenMethod(RuntimeError):
    """Método de escrita ou publicação: este aplicativo não o chama."""


def quota_day(moment: datetime) -> str:
    return moment.astimezone(PACIFIC).date().isoformat()


class QuotaLedger:
    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.config = settings.quota
        self.limits = settings.quota_limits()

    def cost(self, method: str) -> tuple[str, int]:
        if method in self.config["policy"]["forbidden_methods"]:
            raise ForbiddenMethod(f"{method} é um método de escrita e não é usado por este aplicativo.")
        entry = self.config["methods"].get(method)
        if entry is None:
            raise KeyError(f"Método sem custo configurado em quota.toml: {method}")
        return entry["bucket"], entry["units"]

    def used(self, bucket: str, moment: datetime) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(units), 0) AS total FROM api_calls WHERE quota_day = ? AND bucket = ?",
            (quota_day(moment), bucket),
        ).fetchone()
        return int(row["total"])

    def refused_today(self, bucket: str, moment: datetime) -> bool:
        """O Google já disse que acabou. Insistir só gera erro até a virada do dia de cota."""
        row = self.conn.execute(
            "SELECT 1 FROM api_calls WHERE quota_day = ? AND bucket = ? AND error_reason IN ('quotaExceeded', 'dailyLimitExceeded', 'dailyLimitExceededUnreg') LIMIT 1",
            (quota_day(moment), bucket),
        ).fetchone()
        return row is not None

    def check(self, method: str, moment: datetime) -> None:
        bucket, units = self.cost(method)
        limit = self.limits[bucket]
        if self.refused_today(bucket, moment):
            raise BudgetExceeded(f"O Google recusou por cota hoje no balde '{bucket}'. Nada será chamado até a virada do dia de cota.")
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
        rows = []
        for name, limit in self.limits.items():
            bucket = self.config["buckets"][name]
            rows.append({
                "bucket": name, "label": bucket.get("label", name), "used": self.used(name, moment), "limit": limit,
                "google_limit": bucket.get("google_daily"), "verified": bucket.get("verified", False),
                "note": bucket.get("note"), "quota_day": quota_day(moment),
            })
        return rows
