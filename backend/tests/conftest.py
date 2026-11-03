from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import ComplianceRecord, Settings, load_scoring
from app.db import connect, migrate
from app.metrics.core import Snapshot, VideoSeries

T0 = datetime(2026, 9, 1, tzinfo=UTC)

# Registro fictício, só para testar o estado liberado. Não representa aprovação real.
APPROVED = ComplianceRecord(
    status="approved", use_case="analytics_reporting", amendment_accepted=True, compliance_audit_passed=True,
    google_case_ref="caso-de-teste", approved_on="2026-01-01", review_by="2099-01-01",
    approved_scopes=("derived_metrics", "extended_storage"), declared_by="teste",
)


@pytest.fixture
def scoring():
    return load_scoring()


@pytest.fixture
def conn():
    connection = connect(":memory:")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def demo_settings(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path)


@pytest.fixture
def live_settings(tmp_path):
    return Settings(mode="live", youtube_api_key="AIzaTESTKEY0000000000000000", data_dir=tmp_path,
                    quota_default_daily=100, quota_search_daily=5)


def make_series(video_id="v", channel="c", fmt="long", published=T0, points=()):
    """points: pares (horas desde a publicação, views)."""
    return VideoSeries(
        video_id, channel, fmt, published,
        tuple(Snapshot(published + timedelta(hours=h), views) for h, views in points),
    )
