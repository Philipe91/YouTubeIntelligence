from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime

import pytest

from app.config import ComplianceRecord, Settings, get_settings, load_compliance
from app.connectors.quota import ForbiddenMethod, QuotaLedger
from app.metrics.classify import classify_format
from app.policy import LIVE_APPROVED, LIVE_RESTRICTED, compliance_problems, policy_state

from .conftest import APPROVED

TODAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


def live(tmp_path, record):
    return Settings(mode="live", data_dir=tmp_path, compliance=record)


def test_repository_record_starts_not_requested_and_blocks(tmp_path):
    record = load_compliance()
    assert record.status == "not_requested"
    state = policy_state(live(tmp_path, record), TODAY)
    assert state.state == LIVE_RESTRICTED and not state.derived_allowed and state.problems


def test_complete_record_allows_with_unverified_wording(tmp_path):
    state = policy_state(live(tmp_path, APPROVED), TODAY)
    assert state.state == LIVE_APPROVED and state.derived_allowed and state.extended_storage
    assert "não consegue confirmá-la" in state.description


@pytest.mark.parametrize("change", [
    {"status": "requested"}, {"status": "denied"}, {"status": "revoked"}, {"use_case": ""}, {"use_case": "outro"},
    {"amendment_accepted": False}, {"compliance_audit_passed": False}, {"google_case_ref": ""}, {"declared_by": ""},
    {"approved_on": ""}, {"approved_on": "ontem"}, {"approved_on": "2099-01-01"}, {"review_by": ""},
    {"review_by": "2026-11-02"}, {"approved_scopes": ()}, {"approved_scopes": ("extended_storage",)},
])
def test_any_incomplete_record_keeps_blocked(tmp_path, change):
    state = policy_state(live(tmp_path, dataclasses.replace(APPROVED, **change)), TODAY)
    assert state.state == LIVE_RESTRICTED
    assert state.derived_allowed is False


def test_derived_scope_alone_does_not_extend_storage(tmp_path):
    record = dataclasses.replace(APPROVED, approved_scopes=("derived_metrics",))
    state = policy_state(live(tmp_path, record), TODAY)
    assert state.derived_allowed and not state.extended_storage and state.stats_retention == "30 dias"


def test_legacy_environment_variable_never_authorizes(monkeypatch, tmp_path):
    monkeypatch.setenv("YTI_MODE", "live")
    monkeypatch.setenv("YTI_DERIVED_METRICS_APPROVAL_REF", "qualquer-coisa")
    settings = get_settings()
    assert settings.legacy_approval_env_set is True
    assert policy_state(settings, TODAY).derived_allowed is False


@pytest.mark.parametrize("content", ["isto nao e toml ===", ""])
def test_broken_or_empty_file_fails_closed(tmp_path, content):
    path = tmp_path / "c.toml"
    path.write_text(content, encoding="utf-8")
    assert compliance_problems(load_compliance(path), TODAY)


def test_missing_file_fails_closed(tmp_path):
    record = load_compliance(tmp_path / "nao-existe.toml")
    assert record.status == "invalid" and compliance_problems(record, TODAY)


def test_string_true_is_not_accepted_as_boolean(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('amendment_accepted = "true"\ncompliance_audit_passed = "true"\n', encoding="utf-8")
    record = load_compliance(path)
    assert record.amendment_accepted is False and record.compliance_audit_passed is False


def test_demo_is_never_affected_by_record(tmp_path):
    assert policy_state(Settings(mode="demo", data_dir=tmp_path, compliance=ComplianceRecord()), TODAY).derived_allowed


# --- Cotas -----------------------------------------------------------------------------------

def test_buckets_come_from_config_and_cap_at_google(tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path, quota_overrides={"search": 5000, "default": 7000, "analytics": 50})
    limits = settings.quota_limits()
    assert limits["search"] == 100, "nunca acima do limite do Google"
    assert limits["default"] == 7000
    assert limits["analytics"] == 50
    assert limits["batch_stats"] == 0


def test_generic_environment_override(monkeypatch):
    monkeypatch.setenv("YTI_QUOTA_ANALYTICS_DAILY", "33")
    monkeypatch.setenv("YTI_QUOTA_SEARCH_DAILY", "12")
    limits = get_settings().quota_limits()
    assert limits["analytics"] == 33 and limits["search"] == 12


def test_write_methods_are_refused(conn, tmp_path):
    ledger = QuotaLedger(conn, Settings(mode="live", data_dir=tmp_path))
    for method in ("videos.insert", "videos.update", "videos.delete", "thumbnails.set"):
        with pytest.raises(ForbiddenMethod):
            ledger.check(method, NOW)


def test_unknown_method_fails_before_calling(conn, tmp_path):
    with pytest.raises(KeyError):
        QuotaLedger(conn, Settings(mode="live", data_dir=tmp_path)).check("captions.list", NOW)


def test_usage_reports_every_bucket_with_verification_flag(conn, tmp_path):
    rows = {row["bucket"]: row for row in QuotaLedger(conn, Settings(mode="live", data_dir=tmp_path)).usage(NOW)}
    assert set(rows) == {"default", "search", "batch_stats", "analytics"}
    assert rows["default"]["verified"] is True and rows["batch_stats"]["verified"] is False
    assert rows["analytics"]["google_limit"] is None


def test_buckets_are_counted_independently(conn, tmp_path):
    ledger = QuotaLedger(conn, Settings(mode="live", data_dir=tmp_path))
    ledger.record("analytics", "reports.query", "analytics", 1, 200, None, NOW)
    assert ledger.used("analytics", NOW) == 1 and ledger.used("default", NOW) == 0


# --- Classificação de Shorts ---------------------------------------------------------------------

@pytest.mark.parametrize("seconds,published,expected", [
    (120, "2024-10-14T23:00:00Z", "long"),
    (120, "2024-10-15T00:00:00Z", "short"),
    (60, "2020-01-01T00:00:00Z", "short"),
    (61, "2020-01-01T00:00:00Z", "long"),
    (180, "2026-01-01T00:00:00Z", "short"),
    (181, "2026-01-01T00:00:00Z", "long"),
])
def test_three_minute_rule_depends_on_upload_date(seconds, published, expected):
    result = classify_format(seconds, 180, published_at=published, short_cutoff="2024-10-15", legacy_short_max_seconds=60)
    assert result == (expected, "duration")
