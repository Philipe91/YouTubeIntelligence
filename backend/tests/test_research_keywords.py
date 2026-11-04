"""Research Center e Keyword Intelligence: modos, isolamento, falhas e conformidade."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import collector, demo, main
from app.config import Settings
from app.connectors.youtube_analytics import fetch_top_search_terms
from app.connectors.youtube_data import YouTubeDataClient
from app.db import connect, migrate, utcnow
from app.intel import keywords, research
from app.intel import router as intel_router
from app.intel.common import csv_cell
from app.studio import store
from tests.conftest import APPROVED
from tests.yt_mock import FakeYouTube, error_response

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
TOKEN = "segredo-de-teste"
HEADERS = {"X-YTI-Token": TOKEN}


@pytest.fixture
def demo_cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def live_cfg(tmp_path):
    return Settings(mode="live", youtube_api_key="AIzaTESTKEY0000000000000000", data_dir=tmp_path, api_token=TOKEN, quota_default_daily=100, quota_search_daily=5)


@pytest.fixture
def approved_cfg(tmp_path):
    return Settings(mode="live", youtube_api_key="AIzaTESTKEY0000000000000000", data_dir=tmp_path, api_token=TOKEN, quota_default_daily=100, quota_search_daily=5, compliance=APPROVED)


@pytest.fixture
def studio(tmp_path, demo_cfg):
    conn = store.open_studio(demo_cfg)
    store.seed_demo_once(conn)
    yield conn
    conn.close()


@pytest.fixture
def real_channel(studio):
    return store.create_channel(studio, {"name": "Canal Real", "language": "pt", "keywords": ["roma"], "topic_backlog": ["Roma antiga e o sal"]})


@pytest.fixture
def demo_db(demo_cfg):
    conn = connect(demo_cfg.db_path)
    migrate(conn)
    demo.seed_demo(conn, utcnow())
    keywords.seed_demo_terms(conn, utcnow())
    yield conn
    conn.close()


@pytest.fixture
def live_db(tmp_path):
    conn = connect(tmp_path / "live.sqlite")
    migrate(conn)
    yield conn
    conn.close()


def factory_for(fake: FakeYouTube):
    def build(settings, conn):
        return YouTubeDataClient(settings, conn, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: NOW)
    return build


# --- Pesquisa em modo demonstração ----------------------------------------------------------------

def test_demo_search_uses_no_network_and_is_marked_fictional(demo_db, studio, demo_cfg):
    def explode(*_args):
        raise AssertionError("o modo demo não pode abrir cliente do YouTube")

    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow(), factory=explode)
    assert run["fictional"] and run["data_origin"] == "demo" and run["result_count"] > 0
    view = research.run_items(demo_db, demo_cfg, run["id"])
    assert view["videos"] and all("roma" in v["title"].lower() for v in view["videos"])
    assert view["search_volume"]["value"] is None and view["search_volume"]["kind"] == "unavailable"


@pytest.mark.parametrize("filters,check", [
    ({"language": "es"}, lambda v: v["language"] == "es"),
    ({"video_format": "short"}, lambda v: v["format"] == "short"),
    ({"video_format": "long"}, lambda v: v["format"] == "long"),
    ({"country": "PT"}, lambda v: v["country"] == "PT"),
])
def test_demo_filters_really_filter(demo_db, studio, demo_cfg, filters, check):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="império" if filters.get("language") == "es" else "roma", channel_id=None, now=utcnow(), **filters)
    videos = research.run_items(demo_db, demo_cfg, run["id"], limit=100)["videos"]
    assert all(check(v) for v in videos)


def test_days_filter_limits_published_date(demo_db, studio, demo_cfg):
    now = utcnow()
    run = research.run_search(demo_db, studio, demo_cfg, kind="recent", query="roma", channel_id=None, now=now, days=7)
    for video in research.run_items(demo_db, demo_cfg, run["id"], limit=100)["videos"]:
        assert datetime.fromisoformat(video["published_at"].replace("Z", "+00:00")) >= now - timedelta(days=7, minutes=1)


def test_channel_search_and_emerging_only_list_raw_values(demo_db, studio, demo_cfg):
    channels = research.run_search(demo_db, studio, demo_cfg, kind="channels", query="história", channel_id=None, now=utcnow())
    assert channels["result_count"] > 0
    emerging = research.run_search(demo_db, studio, demo_cfg, kind="emerging", query="roma", channel_id=None, now=utcnow(), max_subscribers=100_000)
    rows = research.run_items(demo_db, demo_cfg, emerging["id"])["channels"]
    counts = [r["subscribers"]["value"] for r in rows]
    assert counts == sorted(counts) and all(c <= 100_000 for c in counts)
    assert not any("score" in key or "idr" in key for row in rows for key in row)


def test_empty_result_is_not_an_error(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="assunto inexistente xyzzy", channel_id=None, now=utcnow())
    view = research.run_items(demo_db, demo_cfg, run["id"])
    assert run["result_count"] == 0 and view["videos"] == [] and view["total"] == 0


@pytest.mark.parametrize("query", ["", " ", "a", "de da do", "x" * 121])
def test_bad_queries_are_refused(demo_db, studio, demo_cfg, query):
    with pytest.raises(store.StudioError) as error:
        research.run_search(demo_db, studio, demo_cfg, kind="videos", query=query, channel_id=None, now=utcnow())
    assert error.value.code == "invalid_field"


def test_pagination_returns_distinct_pages(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id=None, now=utcnow())
    first = research.run_items(demo_db, demo_cfg, run["id"], limit=2, offset=0)["videos"]
    second = research.run_items(demo_db, demo_cfg, run["id"], limit=2, offset=2)["videos"]
    assert len(first) == 2 and {v["id"] for v in first}.isdisjoint(v["id"] for v in second)


# --- Isolamento e associação ----------------------------------------------------------------------

def test_real_channel_never_receives_fictional_research(demo_db, studio, demo_cfg, real_channel):
    with pytest.raises(store.StudioError) as error:
        research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id=real_channel["id"], now=utcnow())
    assert error.value.code == "channel_data_mismatch"
    with pytest.raises(store.StudioError):
        keywords.lookup(demo_db, studio, demo_cfg, "roma", real_channel["id"], utcnow())


def test_fictional_channel_never_receives_real_data(live_db, studio, live_cfg):
    fake = FakeYouTube(NOW)
    with pytest.raises(store.StudioError) as error:
        research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=NOW, factory=factory_for(fake))
    assert error.value.code == "channel_data_mismatch" and not fake.calls


def test_runs_are_isolated_by_channel(demo_db, studio, demo_cfg):
    mine = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow())
    other = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_rotas", now=utcnow())
    assert [r["id"] for r in research.list_runs(demo_db, channel_id="chn_demo_cronicas")["items"]] == [mine["id"]]
    with pytest.raises(store.StudioError) as error:
        research.run_items(demo_db, demo_cfg, other["id"], channel_id="chn_demo_cronicas")
    assert error.value.status == 404
    with pytest.raises(store.StudioError):
        research.compare_runs(demo_db, mine["id"], other["id"], channel_id="chn_demo_cronicas")
    with pytest.raises(store.StudioError):
        research.save_run(demo_db, other["id"], "x", channel_id="chn_demo_cronicas")
    with pytest.raises(store.StudioError):
        research.export_csv(demo_db, demo_cfg, other["id"], "chn_demo_cronicas")


def test_favorites_are_isolated_by_channel(studio):
    keywords.add_favorite(studio, "chn_demo_cronicas", "vikings", "", utcnow())
    assert [f["term"] for f in keywords.list_favorites(studio, "chn_demo_cronicas")] == ["vikings"]
    assert keywords.list_favorites(studio, "chn_demo_rotas") == []
    with pytest.raises(store.StudioError):
        keywords.remove_favorite(studio, "chn_demo_rotas", "vikings")


def test_for_you_respects_avoid_list_and_only_uses_the_channel(demo_db, studio, demo_cfg):
    store.update_channel(studio, "chn_demo_cronicas", {"avoid": ["peste"]})
    data = keywords.for_channel(demo_db, studio, demo_cfg, "chn_demo_cronicas")
    assert not any("peste" in item["term"].lower() for item in data["items"])
    assert {i["origin"] for i in data["items"]} & {"analytics"}
    other = keywords.for_channel(demo_db, studio, demo_cfg, "chn_demo_rotas")
    assert not any(i["origin"] == "analytics" and "viking" in i["term"] for i in other["items"])


def test_for_you_real_channel_in_demo_uses_only_its_own_profile(demo_db, studio, demo_cfg, real_channel):
    data = keywords.for_channel(demo_db, studio, demo_cfg, real_channel["id"])
    assert data["uses_research"] is False and {i["origin"] for i in data["items"]} <= {"perfil", "backlog", "favorito"}


# --- Salvos, comparação, exportação ---------------------------------------------------------------

def test_save_rerun_compare_and_export(demo_db, studio, demo_cfg):
    first = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow(), video_format="long")
    research.save_run(demo_db, first["id"], "  Minha  pesquisa ")
    assert research.list_runs(demo_db, saved=True)["items"][0]["saved_name"] == "Minha pesquisa"
    second = research.rerun(demo_db, studio, demo_cfg, first["id"], utcnow())
    assert second["filters"]["format"] == "long" and second["id"] != first["id"]
    same = research.compare_runs(demo_db, first["id"], second["id"])
    assert len(same["both"]) == first["result_count"] and same["only_a"] == [] and same["only_b"] == []
    third = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="vikings", channel_id=None, now=utcnow(), video_format="long")
    different = research.compare_runs(demo_db, first["id"], third["id"])
    assert different["only_a"] and different["only_b"] and different["both"] == []
    body, name = research.export_csv(demo_db, demo_cfg, first["id"])
    assert name.startswith("pesquisa_ficticio_") and "idr" not in body.split("\r\n")[0] and "vph" not in body.split("\r\n")[0]
    research.delete_run(demo_db, third["id"])
    with pytest.raises(store.StudioError):
        research.get_run(demo_db, third["id"])


@pytest.mark.parametrize("danger", ["=HYPERLINK(1)", "+1", "-1", "@SUM(1)"])
def test_csv_neutralizes_formulas_in_external_text(danger):
    assert csv_cell(danger).startswith("'")


def test_retention_removed_video_shows_as_removed_not_as_error(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id=None, now=utcnow())
    video_id = demo_db.execute("SELECT item_id FROM research_items WHERE run_id = ? ORDER BY rank LIMIT 1", (run["id"],)).fetchone()["item_id"]
    demo_db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    demo_db.commit()
    assert research.run_items(demo_db, demo_cfg, run["id"])["removed"] == 1


def test_comparison_refuses_mixed_origins(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id=None, now=utcnow())
    other = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="vikings", channel_id=None, now=utcnow())
    demo_db.execute("UPDATE research_runs SET data_origin = 'youtube' WHERE id = ?", (other["id"],))
    demo_db.commit()
    with pytest.raises(store.StudioError) as error:
        research.compare_runs(demo_db, run["id"], other["id"])
    assert error.value.code == "mixed_data_origin"


# --- Modo real com YouTube falso ------------------------------------------------------------------

def real_studio_channel(studio):
    return store.create_channel(studio, {"name": "Canal Vivo", "language": "pt", "keywords": ["roma"]})


def test_live_search_calls_official_api_and_stores_only_ids(live_db, studio, live_cfg):
    fake = FakeYouTube(NOW)
    channel = real_studio_channel(studio)
    run = research.run_search(live_db, studio, live_cfg, kind="videos", query="roma antiga", channel_id=channel["id"], now=NOW, language="pt", country="br", days=60, factory=factory_for(fake))
    assert run["data_origin"] == "youtube" and run["result_count"] == 12 and run["total_results_approx"] == 12345
    search_call = next(c for c in fake.calls if c.url.path.endswith("/search"))
    assert search_call.url.params["relevanceLanguage"] == "pt" and search_call.url.params["regionCode"] == "BR" and "publishedAfter" in search_call.url.params
    columns = {row[1] for row in live_db.execute("PRAGMA table_info(research_items)")}
    assert "title" not in columns
    view = research.run_items(live_db, live_cfg, run["id"])
    assert view["filter_notes"] and view["videos"][0]["source_url"].startswith("https://www.youtube.com/watch?v=")


def test_live_format_filter_is_applied_after_the_api(live_db, studio, live_cfg):
    run = research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id=None, now=NOW, video_format="long", factory=factory_for(FakeYouTube(NOW)))
    assert run["result_count"] == 6
    assert all(v["format"] == "long" for v in research.run_items(live_db, live_cfg, run["id"])["videos"])


def test_live_restricted_shows_raw_data_and_never_derived(live_db, studio, live_cfg):
    run = research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=factory_for(FakeYouTube(NOW)))
    view = research.run_items(live_db, live_cfg, run["id"], limit=100)
    assert view["derived_allowed"] is False
    for video in view["videos"]:
        assert video["views"]["value"] is not None
        assert video["idr"]["value"] is None and video["idr"]["kind"] == "blocked"
        assert video["vph_observed"]["kind"] == "blocked" and video["outlier"] is None and video["acceleration"] is None
    assert research.growing_topics(live_db, live_cfg)["blocked"] is True


def test_live_keyword_restricted_blocks_index_and_related_but_stays_useful(live_db, studio, live_cfg):
    channel = real_studio_channel(studio)
    result = keywords.lookup(live_db, studio, live_cfg, "roma antiga", channel["id"], NOW, factory=factory_for(FakeYouTube(NOW)))
    assert result["run_id"] and result["fetch_error"] is None
    data = keywords.analyze(live_db, studio, live_cfg, "roma antiga", channel["id"], NOW)
    assert data["index"]["blocked"] and data["index"]["formats"] == []
    assert data["related"]["from_titles"] == [] and data["related"]["from_titles_blocked"]
    assert data["rising"]["blocked"]
    assert data["variations"]["items"] and data["questions"]["from_model"] and data["sample"]["total"] == 12
    assert data["volume"]["measured"]["value"] is None and data["volume"]["provider_estimate"]["value"] is None


def test_live_keyword_approved_unlocks_index_with_labels(live_db, studio, approved_cfg):
    keywords.lookup(live_db, studio, approved_cfg, "roma antiga", None, NOW, factory=factory_for(FakeYouTube(NOW)))
    data = keywords.analyze(live_db, studio, approved_cfg, "roma antiga", None, NOW)
    assert not data["index"]["blocked"] and "não buscas" in data["index"]["note"]
    assert data["related"]["from_titles"] and data["volume"]["measured"]["value"] is None


def test_volume_provider_is_labelled_as_third_party_estimate(demo_db, studio, demo_cfg):
    class Provider:
        name = "Provedor X"

        def estimate(self, term, language):
            return 1200

    data = keywords.analyze(demo_db, studio, demo_cfg, "roma", None, utcnow(), provider=Provider())
    assert data["volume"]["provider_estimate"]["value"] == 1200 and data["volume"]["provider_estimate"]["kind"] == "estimated"
    assert data["volume"]["measured"]["value"] is None


def test_no_api_key_is_explained_and_lookup_still_works(tmp_path, studio):
    cfg = Settings(mode="live", youtube_api_key="", data_dir=tmp_path, api_token=TOKEN)
    conn = connect(tmp_path / "live.sqlite")
    migrate(conn)
    with pytest.raises(store.StudioError) as error:
        research.run_search(conn, studio, cfg, kind="videos", query="roma", channel_id=None, now=NOW)
    assert error.value.code == "api_key_missing" and "YOUTUBE_API_KEY" in error.value.message
    result = keywords.lookup(conn, studio, cfg, "roma", None, NOW)
    assert result["fetch_error"]["code"] == "api_key_missing" and result["run_id"] is None
    assert keywords.history(conn, None)["total"] == 1
    conn.close()


@pytest.mark.parametrize("failure,code,status", [
    (error_response(403, "quotaExceeded"), "quota_google", 429),
    (error_response(400, "badRequest"), "youtube_error", 502),
])
def test_api_failures_become_readable_errors_and_leak_no_key(live_db, studio, live_cfg, failure, code, status):
    fake = FakeYouTube(NOW)
    fake.fail_next.append(failure)
    with pytest.raises(store.StudioError) as error:
        research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=factory_for(fake))
    assert error.value.code == code and error.value.status == status and "AIza" not in error.value.message
    assert research.list_runs(live_db)["total"] == 0


def test_local_quota_blocks_before_calling(live_db, studio, tmp_path):
    cfg = Settings(mode="live", youtube_api_key="AIzaTESTKEY0000000000000000", data_dir=tmp_path, quota_default_daily=100, quota_search_daily=0)
    fake = FakeYouTube(NOW)
    with pytest.raises(store.StudioError) as error:
        research.run_search(live_db, studio, cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=factory_for(fake))
    assert error.value.code == "quota_local" and not fake.calls


def test_repeating_a_search_uses_cache_instead_of_quota(live_db, studio, live_cfg):
    fake = FakeYouTube(NOW)
    build = factory_for(fake)
    research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=build)
    first = sum(c.url.path.endswith("/search") for c in fake.calls)
    research.run_search(live_db, studio, live_cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=build)
    assert first == sum(c.url.path.endswith("/search") for c in fake.calls) == 1


def test_live_channel_search_and_emerging(live_db, studio, live_cfg):
    fake = FakeYouTube(NOW)
    original = fake._handle

    def handle(request):
        if request.url.path.endswith("/search") and request.url.params.get("type") == "channel":
            fake.calls.append(request)
            return httpx.Response(200, json={"pageInfo": {"totalResults": 3}, "items": [{"id": {"channelId": "UCfake1"}}]})
        return original(request)

    def build(settings, conn):
        return YouTubeDataClient(settings, conn, transport=httpx.MockTransport(handle), sleep=lambda _s: None, clock=lambda: NOW)

    channels = research.run_search(live_db, studio, live_cfg, kind="channels", query="história", channel_id=None, now=NOW, factory=build)
    rows = research.run_items(live_db, live_cfg, channels["id"])["channels"]
    assert [r["id"] for r in rows] == ["UCfake1"] and rows[0]["subscribers"]["value"] == 50000
    emerging = research.run_search(live_db, studio, live_cfg, kind="emerging", query="roma", channel_id=None, now=NOW, days=60, factory=build)
    assert emerging["result_count"] == 1


# --- Palavras -------------------------------------------------------------------------------------

def test_analyze_does_not_consume_quota_or_write_history(live_db, studio, live_cfg):
    keywords.analyze(live_db, studio, live_cfg, "roma", None, NOW)
    assert live_db.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0] == 0
    assert keywords.history(live_db, None)["total"] == 0


def test_variations_questions_and_language():
    pt = keywords.variations("roma antiga", "pt")
    assert any(i["term"] == "antiga roma" for i in pt) and any("explicado" in i["term"] for i in pt)
    assert len({i["term"] for i in pt}) == len(pt) and "roma antiga" not in {i["term"] for i in pt}
    assert keywords.model_questions("roma", "en")[0] == "What is roma?"
    assert keywords.model_questions("roma", "es")[0].startswith("¿")
    assert keywords.model_questions("roma", "fr")[0] == "What is roma?"


def test_question_titles_come_from_real_rows_not_invented(demo_db, studio, demo_cfg):
    data = keywords.analyze(demo_db, studio, demo_cfg, "roma", None, utcnow())
    assert data["questions"]["from_titles"] and all("?" in q["title"] for q in data["questions"]["from_titles"])


def test_own_terms_states(demo_db, studio, demo_cfg, real_channel):
    assert keywords.own_terms(demo_db, studio, demo_cfg, "chn_demo_cronicas")["available"]
    assert not keywords.own_terms(demo_db, studio, demo_cfg, "chn_demo_imperios")["available"]
    blocked = keywords.own_terms(demo_db, studio, demo_cfg, real_channel["id"])
    assert not blocked["available"] and "fictícios" in blocked["reason"]


def test_analytics_search_terms_query_shape():
    seen = {}

    def handle(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"columnHeaders": [{"name": "insightTrafficSourceDetail"}, {"name": "views"}, {"name": "estimatedMinutesWatched"}], "rows": [["roma", 10, 20]]})

    rows = fetch_top_search_terms("tok", "2026-10-01", "2026-10-28", httpx.MockTransport(handle))
    assert rows == [{"insightTrafficSourceDetail": "roma", "views": 10, "estimatedMinutesWatched": 20}]
    assert seen["filters"] == "insightTrafficSourceType==YT_SEARCH" and seen["sort"] == "-views" and int(seen["maxResults"]) <= 25


def test_search_terms_without_a_term_are_not_stored(live_db, live_cfg):
    live_db.execute("INSERT INTO channels (id, title, is_own, text_refreshed_at, created_at) VALUES ('UCx', 'x', 1, '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')")
    live_db.commit()

    def handle(_request):
        return httpx.Response(200, json={"columnHeaders": [{"name": "insightTrafficSourceDetail"}, {"name": "views"}], "rows": [["roma", 5], ["", 9]]})

    ledger = collector.QuotaLedger(live_db, live_cfg)
    collector._sync_search_terms(live_db, ledger, "tok", "UCx", NOW, httpx.MockTransport(handle))
    assert [r["term"] for r in live_db.execute("SELECT term FROM own_search_terms")] == ["roma"]


def test_search_terms_rejection_does_not_break_daily_sync(live_db, live_cfg):
    live_db.execute("INSERT INTO channels (id, title, is_own, text_refreshed_at, created_at) VALUES ('UCx', 'x', 1, '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')")
    live_db.commit()
    from app.connectors import youtube_analytics
    ledger = collector.QuotaLedger(live_db, live_cfg)
    original = youtube_analytics.fetch_top_search_terms

    def refuse(*_a, **_k):
        raise youtube_analytics.AnalyticsError("recusado")

    youtube_analytics.fetch_top_search_terms = refuse
    try:
        assert collector._sync_search_terms(live_db, ledger, "tok", "UCx", NOW) == 0
    finally:
        youtube_analytics.fetch_top_search_terms = original
    assert live_db.execute("SELECT error_reason FROM api_calls").fetchone()[0] == "AnalyticsError"


# --- API ------------------------------------------------------------------------------------------

@pytest.fixture
def api(demo_cfg):
    main.app.dependency_overrides[main.settings_dep] = lambda: demo_cfg
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_api_requires_token_for_writes_and_supports_full_flow(api):
    body = {"kind": "videos", "query": "roma", "channel_id": "chn_demo_cronicas"}
    assert api.post("/api/intel/research/search", json=body).status_code == 401
    created = api.post("/api/intel/research/search", json=body, headers=HEADERS)
    assert created.status_code == 201
    run_id = created.json()["id"]
    assert api.post(f"/api/intel/research/runs/{run_id}/save", json={"name": "x"}).status_code == 401
    assert api.post(f"/api/intel/research/runs/{run_id}/save", json={"name": "x"}, headers=HEADERS).status_code == 200
    assert api.get(f"/api/intel/research/runs/{run_id}").json()["run"]["saved_name"] == "x"
    assert api.get(f"/api/intel/research/runs/{run_id}?channel_id=chn_demo_rotas").status_code == 404
    export = api.get(f"/api/intel/research/runs/{run_id}/export.csv")
    assert export.headers["content-type"].startswith("text/csv") and "attachment" in export.headers["content-disposition"]
    assert api.post(f"/api/intel/research/runs/{run_id}/delete", headers=HEADERS).status_code == 200
    assert api.get(f"/api/intel/research/runs/{run_id}").status_code == 404


def test_api_keyword_flow_and_validation(api):
    assert api.post("/api/intel/keywords/lookup", json={"term": "roma"}).status_code == 401
    assert api.post("/api/intel/keywords/lookup", json={"term": "x"}, headers=HEADERS).status_code == 400
    assert api.post("/api/intel/keywords/lookup", json={"term": "roma", "channel_id": "chn_demo_cronicas"}, headers=HEADERS).status_code == 200
    data = api.get("/api/intel/keywords/analyze", params={"term": "roma", "channel_id": "chn_demo_cronicas"}).json()
    assert data["fictional"] and not data["index"]["blocked"]
    assert api.post("/api/intel/channels/chn_demo_cronicas/keywords/favorites", json={"term": "roma"}, headers=HEADERS).status_code == 201
    assert api.get("/api/intel/channels/chn_demo_cronicas/keywords/favorites").json()["items"][0]["term"] == "roma"
    assert api.get("/api/intel/channels/chn_demo_rotas/keywords/favorites").json()["items"] == []
    assert api.get("/api/intel/channels/nao_existe/keywords/for-you").status_code == 404


def test_context_separates_compatible_channels(api):
    created = api.post("/api/studio/channels", json={"fields": {"name": "Meu real"}}, headers=HEADERS).json()
    data = api.get("/api/intel/context").json()
    assert data["mode"] == "demo" and created["id"] in [c["id"] for c in data["other_channels"]]
    assert created["id"] not in [c["id"] for c in data["channels"]]


def test_deleting_channel_purges_its_research(api, demo_cfg):
    run = api.post("/api/intel/research/search", json={"query": "roma", "channel_id": "chn_demo_imperios"}, headers=HEADERS).json()
    kept = api.post("/api/intel/research/search", json={"query": "roma", "channel_id": "chn_demo_rotas"}, headers=HEADERS).json()
    api.post("/api/intel/keywords/lookup", json={"term": "roma", "channel_id": "chn_demo_imperios"}, headers=HEADERS)
    assert api.post("/api/studio/channels/chn_demo_imperios/delete", json={"confirm_name": store.DEMO_CHANNELS[2]["name"]}, headers=HEADERS).status_code == 200
    conn = connect(demo_cfg.db_path)
    assert conn.execute("SELECT 1 FROM research_runs WHERE id = ?", (run["id"],)).fetchone() is None
    assert conn.execute("SELECT 1 FROM research_runs WHERE id = ?", (kept["id"],)).fetchone() is not None
    assert conn.execute("SELECT 1 FROM keyword_lookups WHERE managed_channel_id = 'chn_demo_imperios'").fetchone() is None
    conn.close()


def test_retention_removes_old_coach_conversations_in_live(live_db, live_cfg):
    from app.policy import apply_retention

    old = "2026-01-01T00:00:00Z"
    live_db.execute("INSERT INTO coach_conversations (id, managed_channel_id, title, created_at, updated_at) VALUES ('c1', 'x', 't', ?, ?)", (old, old))
    live_db.commit()
    assert apply_retention(live_db, live_cfg, NOW)["coach_conversations"] == 1
