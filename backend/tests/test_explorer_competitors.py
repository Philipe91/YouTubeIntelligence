"""Outlier Explorer e Competitor Intelligence."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import demo, main
from app.config import Settings
from app.connectors.youtube_data import YouTubeDataClient
from app.collector import videos_due_for_snapshot
from app.db import connect, migrate, utcnow
from app.intel import competitors, explorer, research
from app.studio import store
from tests.conftest import APPROVED
from tests.yt_mock import FakeYouTube, error_response

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
TOKEN = "segredo-de-teste"
HEADERS = {"X-YTI-Token": TOKEN}
KEY = "AIzaTESTKEY0000000000000000"
UC = "UCabcdefghijklmnopqrstuv"


@pytest.fixture
def demo_cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def live_cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_default_daily=100, quota_search_daily=5)


@pytest.fixture
def approved_cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_default_daily=100, quota_search_daily=5, compliance=APPROVED)


@pytest.fixture
def studio(demo_cfg):
    conn = store.open_studio(demo_cfg)
    store.seed_demo_once(conn)
    yield conn
    conn.close()


@pytest.fixture
def demo_db(demo_cfg):
    conn = connect(demo_cfg.db_path)
    migrate(conn)
    demo.seed_demo(conn, utcnow())
    yield conn
    conn.close()


@pytest.fixture
def live_db(tmp_path):
    conn = connect(tmp_path / "live.sqlite")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def real(studio):
    return store.create_channel(studio, {"name": "Canal Vivo", "language": "pt", "keywords": ["roma"], "formats": ["long"]})


def factory_for(fake):
    def build(settings, conn):
        return YouTubeDataClient(settings, conn, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: NOW)
    return build


def seed_live(live_db, studio, settings):
    fake = FakeYouTube(NOW)
    research.run_search(live_db, studio, settings, kind="videos", query="roma", channel_id=None, now=NOW, factory=factory_for(fake))
    return fake


# --- Explorer -------------------------------------------------------------------------------------

def test_explorer_demo_shows_scores_filters_and_paginates(demo_db, demo_cfg):
    data = explorer.search(demo_db, demo_cfg, video_format="long", sort="idr", limit=5)
    assert data["fictional"] and data["derived_allowed"] and len(data["items"]) == 5
    values = [v["idr"]["value"] for v in data["items"] if v["idr"]["value"] is not None]
    assert values == sorted(values, reverse=True)
    second = explorer.search(demo_db, demo_cfg, video_format="long", sort="idr", limit=5, offset=5)
    assert {v["id"] for v in data["items"]}.isdisjoint(v["id"] for v in second["items"])
    above = explorer.search(demo_db, demo_cfg, video_format="long", only_above=True, limit=100)
    threshold = demo_cfg.scoring["outlier"]["band_above"]
    assert above["items"] and all(v["idr"]["value"] >= threshold for v in above["items"])
    assert all(v["format"] == "long" for v in above["items"])
    many = explorer.search(demo_db, demo_cfg, video_format="long", min_views=100000, limit=100)
    assert all(v["views"]["value"] >= 100000 for v in many["items"])


def test_explorer_restricted_stays_useful_without_scores(live_db, studio, live_cfg):
    seed_live(live_db, studio, live_cfg)
    data = explorer.search(live_db, live_cfg, video_format="long", sort="idr", only_above=True, limit=100)
    assert data["sort"] == "views" and len(data["notes"]) == 2 and data["derived_allowed"] is False
    assert len(data["items"]) == 6
    views = [v["views"]["value"] for v in data["items"]]
    assert views == sorted(views, reverse=True)
    for video in data["items"]:
        assert video["idr"]["value"] is None and video["outlier"] is None and video["acceleration"] is None
        assert video["thumbnail_url"] and video["title"] and video["published_at"] and video["channel_title"] and video["source_url"]


def test_explorer_approved_unlocks_with_origin_note(live_db, studio, approved_cfg):
    seed_live(live_db, studio, approved_cfg)
    data = explorer.search(live_db, approved_cfg, video_format="long", sort="idr")
    assert data["derived_allowed"] and data["sort"] == "idr" and "Não é um dado publicado" in data["origin_note"]


def test_explorer_empty_and_invalid(demo_db, demo_cfg):
    assert explorer.search(demo_db, demo_cfg, q="xyzzy inexistente")["total"] == 0
    with pytest.raises(store.StudioError):
        explorer.search(demo_db, demo_cfg, sort="qualquer")


def test_study_list_is_isolated_and_keeps_notes(demo_db, studio, demo_cfg):
    video = demo_db.execute("SELECT id FROM videos LIMIT 1").fetchone()["id"]
    explorer.add_study(demo_db, studio, demo_cfg, "chn_demo_cronicas", video, utcnow(), note="Abertura forte")
    explorer.add_study(demo_db, studio, demo_cfg, "chn_demo_cronicas", video, utcnow())  # Repetir não apaga a nota.
    assert explorer.list_study(demo_db, demo_cfg, "chn_demo_cronicas")["items"][0]["note"] == "Abertura forte"
    assert explorer.list_study(demo_db, demo_cfg, "chn_demo_rotas")["total"] == 0
    with pytest.raises(store.StudioError):
        explorer.remove_study(demo_db, "chn_demo_rotas", video)
    with pytest.raises(store.StudioError):
        explorer.update_study_note(demo_db, "chn_demo_rotas", video, "x")
    explorer.update_study_note(demo_db, "chn_demo_cronicas", video, "Nova nota")
    item = explorer.list_study(demo_db, demo_cfg, "chn_demo_cronicas")["items"][0]
    assert item["note"] == "Nova nota" and item["snapshots"]["count"] >= 1
    explorer.remove_study(demo_db, "chn_demo_cronicas", video)
    assert explorer.list_study(demo_db, demo_cfg, "chn_demo_cronicas")["total"] == 0


def test_study_refuses_real_channel_on_fictional_data(demo_db, studio, demo_cfg, real):
    video = demo_db.execute("SELECT id FROM videos LIMIT 1").fetchone()["id"]
    with pytest.raises(store.StudioError) as error:
        explorer.add_study(demo_db, studio, demo_cfg, real["id"], video, utcnow())
    assert error.value.code == "channel_data_mismatch"


def test_study_unknown_video_is_refused(demo_db, studio, demo_cfg):
    with pytest.raises(store.StudioError) as error:
        explorer.add_study(demo_db, studio, demo_cfg, "chn_demo_cronicas", "nao_existe", utcnow())
    assert error.value.status == 404


def test_study_videos_enter_the_snapshot_queue(live_db, studio, live_cfg, real):
    seed_live(live_db, studio, live_cfg)
    live_db.execute("DELETE FROM search_results")
    live_db.execute("UPDATE channels SET monitored = 0, is_own = 0")
    live_db.commit()
    later = NOW + timedelta(days=10)  # O snapshot da coleta já venceu nessa data.
    assert videos_due_for_snapshot(live_db, live_cfg, later) == []
    explorer.add_study(live_db, studio, live_cfg, real["id"], "vid00", NOW)
    assert videos_due_for_snapshot(live_db, live_cfg, later) == ["vid00"]


def test_compare_needs_study_list_of_the_same_channel(demo_db, studio, demo_cfg):
    ids = [r["id"] for r in demo_db.execute("SELECT id FROM videos LIMIT 3")]
    for video in ids[:2]:
        explorer.add_study(demo_db, studio, demo_cfg, "chn_demo_cronicas", video, utcnow())
    data = explorer.compare_videos(demo_db, demo_cfg, "chn_demo_cronicas", ids[:2])
    assert len(data["columns"]) == 2 and data["columns"][0]["features"]["approach_label"]
    assert "melhor" in data["note"] and "winner" not in data
    with pytest.raises(store.StudioError):
        explorer.compare_videos(demo_db, demo_cfg, "chn_demo_rotas", ids[:2])
    with pytest.raises(store.StudioError):
        explorer.compare_videos(demo_db, demo_cfg, "chn_demo_cronicas", ids)
    with pytest.raises(store.StudioError):
        explorer.compare_videos(demo_db, demo_cfg, "chn_demo_cronicas", ids[:1])


def test_compare_restricted_hides_title_reading(live_db, studio, live_cfg, real):
    seed_live(live_db, studio, live_cfg)
    for video in ("vid00", "vid01"):
        explorer.add_study(live_db, studio, live_cfg, real["id"], video, NOW)
    data = explorer.compare_videos(live_db, live_cfg, real["id"], ["vid00", "vid01"])
    assert data["features_blocked"] and all(c["features"] is None for c in data["columns"]) and data["shared_words"] == []
    assert data["columns"][0]["video"]["views"]["value"] is not None


@pytest.mark.parametrize("title,approach", [("Por que Roma caiu?", "pergunta"), ("3 mitos sobre Roma", "lista"), ("A verdade sobre Roma", "revelacao"), ("Roma explicada", "explicacao"), ("Roma em 5 minutos", "explicacao"), ("Como era viver em Roma", "como_era"), ("Roma caiu em um dia", "narrativa")])
def test_title_reading(title, approach):
    assert explorer.title_features(title)["approach"] == approach


# --- Referências ----------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    (UC, UC), ("@canal.bom", "@canal.bom"), (f"https://www.youtube.com/channel/{UC}", UC), ("https://youtube.com/@canal_bom", "@canal_bom"),
    ("https://m.youtube.com/@canal-bom/videos", "@canal-bom"), ("youtube.com/@canal", "@canal"), (f"https://www.youtube.com/channel/{UC}/videos?x=1", UC),
])
def test_valid_references(text, expected):
    assert competitors.parse_reference(text) == expected


@pytest.mark.parametrize("text", ["", "canal", "https://evil.com/@canal", "https://youtube.com.evil.com/@canal", "https://www.youtube.com/watch?v=abc",
                                  "https://www.youtube.com/channel/abc", "javascript:alert(1)", "@a", "UCcurto", "https://www.youtube.com/"])
def test_invalid_references(text):
    with pytest.raises(store.StudioError) as error:
        competitors.parse_reference(text)
    assert error.value.code == "invalid_reference"


# --- Concorrentes em demo -------------------------------------------------------------------------

def test_demo_overview_links_seeded_competitors_and_shows_comparison(demo_db, studio, demo_cfg):
    data = competitors.overview(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())
    assert data["fictional"] and {i["name"] for i in data["items"]} == {"Atlas Animado (fictício)", "Tinta e Império (fictício)"}
    assert all(i["linked"] and i["videos_collected"] > 0 for i in data["items"])
    assert not data["comparison_blocked"] and len(data["comparison"]) == 2 and data["demo_options"]


def test_demo_add_only_accepts_fictional_channels(demo_db, studio, demo_cfg):
    with pytest.raises(store.StudioError) as error:
        competitors.add(demo_db, studio, demo_cfg, "chn_demo_cronicas", UC, "", "", utcnow())
    assert error.value.code == "demo_reference"
    item = competitors.add(demo_db, studio, demo_cfg, "chn_demo_cronicas", "@demo3", "Era", "nota", utcnow())
    assert item["youtube_ref"] == "DEMO_UC03"
    with pytest.raises(store.StudioError) as error:
        competitors.add(demo_db, studio, demo_cfg, "chn_demo_cronicas", "@demo3", "Outro", "", utcnow())
    assert error.value.code == "duplicate_competitor"


def test_lists_are_isolated_by_channel(demo_db, studio, demo_cfg):
    item = competitors.add(demo_db, studio, demo_cfg, "chn_demo_rotas", "@demo3", "Era", "", utcnow())
    assert "Era" not in {i["name"] for i in competitors.overview(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())["items"]}
    with pytest.raises(store.StudioError):
        competitors.detail(demo_db, studio, demo_cfg, "chn_demo_cronicas", item["id"], utcnow())
    with pytest.raises(store.StudioError):
        competitors.link(demo_db, studio, demo_cfg, "chn_demo_cronicas", item["id"], "@demo3", utcnow())


def test_demo_detail_has_calendar_patterns_and_subjects(demo_db, studio, demo_cfg):
    competitor = store.list_competitors(studio, "chn_demo_cronicas")[0]
    data = competitors.detail(demo_db, studio, demo_cfg, "chn_demo_cronicas", competitor["id"], utcnow())
    assert data["linked"] and data["calendar"] and data["videos"]["items"]
    assert data["editorial"]["long"]["uploads_per_week"] is not None and data["title_patterns"] and data["recurring_subjects"]
    assert [d["day"] for d in data["calendar"]] == sorted((d["day"] for d in data["calendar"]), reverse=True)


def test_unlinked_competitor_is_explained(demo_db, studio, demo_cfg):
    item = store.add_competitor(studio, "chn_demo_rotas", "Nome qualquer", None, "")
    data = competitors.detail(demo_db, studio, demo_cfg, "chn_demo_rotas", item["id"], utcnow())
    assert data["linked"] is False
    assert not next(i for i in competitors.overview(demo_db, studio, demo_cfg, "chn_demo_rotas", utcnow())["items"] if i["id"] == item["id"])["linked"]


def test_real_channel_in_demo_mode_receives_no_fictional_data(demo_db, studio, demo_cfg, real):
    store.add_competitor(studio, real["id"], "Atlas Animado (fictício)", None, "")
    data = competitors.overview(demo_db, studio, demo_cfg, real["id"], utcnow())
    assert data["usable"] is False and data["items"][0]["linked"] is False and data["comparison"] is None
    with pytest.raises(store.StudioError):
        competitors.add(demo_db, studio, demo_cfg, real["id"], "@demo3", "", "", utcnow())


# --- Concorrentes em modo real --------------------------------------------------------------------

def test_live_add_uses_official_api_and_keeps_text_out_of_studio(live_db, studio, live_cfg, real):
    fake = FakeYouTube(NOW)
    item = competitors.add(live_db, studio, live_cfg, real["id"], "https://www.youtube.com/@falso", "", "", NOW, factory_for(fake))
    assert item["name"] == "@falso" and item["youtube_ref"] == "UCfake1"
    assert "Canal Falso" not in str(dict(studio.execute("SELECT * FROM competitors WHERE id = ?", (item["id"],)).fetchone()))
    assert live_db.execute("SELECT monitored FROM channels WHERE id = 'UCfake1'").fetchone()["monitored"] == 1
    assert {c.url.path.rsplit("/", 1)[-1] for c in fake.calls} == {"channels", "playlistItems", "videos"}
    assert competitors.overview(live_db, studio, live_cfg, real["id"], NOW)["items"][0]["channel"]["title"] == "Canal Falso"


def test_live_restricted_blocks_comparison_and_patterns_but_shows_raw(live_db, studio, live_cfg, real):
    item = competitors.add(live_db, studio, live_cfg, real["id"], "@falso", "Rival", "", NOW, factory_for(FakeYouTube(NOW)))
    data = competitors.overview(live_db, studio, live_cfg, real["id"], NOW)
    assert data["comparison"] is None and data["comparison_blocked"] and "Google" in data["reason"]
    assert data["items"][0]["channel"]["subscribers"]["value"] == 50000 and data["items"][0]["videos_collected"] == 12
    detail = competitors.detail(live_db, studio, live_cfg, real["id"], item["id"], NOW)
    assert detail["patterns_blocked"] and detail["editorial"] is None and detail["title_patterns"] == [] and detail["recurring_subjects"] == []
    assert detail["videos"]["total"] == 12 and detail["calendar"] and detail["videos"]["items"][0]["idr"]["value"] is None


def test_live_approved_unlocks_comparison(live_db, studio, approved_cfg, real):
    competitors.add(live_db, studio, approved_cfg, real["id"], "@falso", "", "", NOW, factory_for(FakeYouTube(NOW)))
    data = competitors.overview(live_db, studio, approved_cfg, real["id"], NOW)
    assert data["comparison"] and "Não é um dado publicado" in data["origin_note"]


def test_live_failures_are_readable(live_db, studio, live_cfg, real, tmp_path):
    fake = FakeYouTube(NOW)
    fake.fail_next.append(error_response(403, "quotaExceeded"))
    with pytest.raises(store.StudioError) as error:
        competitors.add(live_db, studio, live_cfg, real["id"], "@falso", "", "", NOW, factory_for(fake))
    assert error.value.code == "quota_google" and store.list_competitors(studio, real["id"]) == []
    no_key = Settings(mode="live", data_dir=tmp_path, api_token=TOKEN)
    with pytest.raises(store.StudioError) as error:
        competitors.add(live_db, studio, no_key, real["id"], "@falso", "", "", NOW)
    assert error.value.code == "api_key_missing"


def test_refresh_needs_link_and_real_mode(live_db, studio, live_cfg, real, demo_db, demo_cfg):
    unlinked = store.add_competitor(studio, real["id"], "Sem vínculo", None, "")
    with pytest.raises(store.StudioError) as error:
        competitors.refresh(live_db, studio, live_cfg, real["id"], unlinked["id"], NOW, factory_for(FakeYouTube(NOW)))
    assert error.value.code == "not_linked"
    seeded = store.list_competitors(studio, "chn_demo_cronicas")[0]
    with pytest.raises(store.StudioError) as error:
        competitors.refresh(demo_db, studio, demo_cfg, "chn_demo_cronicas", seeded["id"], utcnow())
    assert error.value.code == "demo_reference"


def test_report_has_sources_and_respects_the_regime(live_db, studio, live_cfg, approved_cfg, real):
    competitors.add(live_db, studio, live_cfg, real["id"], "@falso", "", "Boa referência", NOW, factory_for(FakeYouTube(NOW)))
    body, name = competitors.report(live_db, studio, live_cfg, real["id"], NOW)
    assert name.endswith(".md") and "Só dados crus" in body and "https://www.youtube.com/channel/UCfake1" in body and "https://www.youtube.com/watch?v=" in body
    assert "IDR" not in body and "Boa referência" in body
    assert "Métricas calculadas" in competitors.report(live_db, studio, approved_cfg, real["id"], NOW)[0]


def test_report_neutralizes_markup_from_external_titles(demo_db, studio, demo_cfg):
    demo_db.execute("UPDATE videos SET title = '[clique](http://x) <script>' WHERE channel_id = 'DEMO_UC01'")
    demo_db.commit()
    body = competitors.report(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())[0]
    assert "[clique](" not in body and "<script>" not in body and "fictícios" in body


# --- Oportunidades --------------------------------------------------------------------------------

def test_opportunity_lifecycle_and_isolation(demo_db, studio, demo_cfg):
    video = demo_db.execute("SELECT id FROM videos LIMIT 1").fetchone()["id"]
    created = competitors.add_opportunity(demo_db, studio, demo_cfg, "chn_demo_cronicas", "O lado comercial de Roma", "Ninguém aborda", video, utcnow())
    row = competitors.list_opportunities(demo_db, "chn_demo_cronicas")[0]
    assert row["video_title"] and row["status"] == "aberta"
    assert competitors.list_opportunities(demo_db, "chn_demo_rotas") == []
    with pytest.raises(store.StudioError):
        competitors.discard_opportunity(demo_db, "chn_demo_rotas", created["id"], utcnow())
    idea = competitors.opportunity_to_idea(demo_db, studio, "chn_demo_cronicas", created["id"], "long", utcnow())
    assert idea["subject"] == "O lado comercial de Roma" and idea["origin"] == "dono"
    with pytest.raises(store.StudioError) as error:
        competitors.opportunity_to_idea(demo_db, studio, "chn_demo_cronicas", created["id"], "long", utcnow())
    assert error.value.code == "opportunity_closed"
    other = competitors.add_opportunity(demo_db, studio, demo_cfg, "chn_demo_cronicas", "Outra", "", None, utcnow())
    competitors.discard_opportunity(demo_db, "chn_demo_cronicas", other["id"], utcnow())
    assert {o["status"] for o in competitors.list_opportunities(demo_db, "chn_demo_cronicas")} == {"virou_ideia", "descartada"}


@pytest.mark.parametrize("title", ["", "ab", "x" * 201])
def test_opportunity_validation(demo_db, studio, demo_cfg, title):
    with pytest.raises(store.StudioError):
        competitors.add_opportunity(demo_db, studio, demo_cfg, "chn_demo_cronicas", title, "", None, utcnow())


# --- API ------------------------------------------------------------------------------------------

@pytest.fixture
def api(demo_cfg):
    main.app.dependency_overrides[main.settings_dep] = lambda: demo_cfg
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_api_flow_and_authorization(api):
    assert api.get("/api/intel/explorer?format=long").status_code == 200
    video = api.get("/api/intel/explorer?format=long&limit=2").json()["items"]
    body = {"video_id": video[0]["id"]}
    assert api.post("/api/intel/channels/chn_demo_cronicas/study", json=body).status_code == 401
    assert api.post("/api/intel/channels/chn_demo_cronicas/study", json=body, headers=HEADERS).status_code == 201
    assert api.get("/api/intel/channels/chn_demo_rotas/study").json()["total"] == 0
    assert api.get("/api/intel/channels/nao_existe/study").status_code == 404
    api.post("/api/intel/channels/chn_demo_cronicas/study", json={"video_id": video[1]["id"]}, headers=HEADERS)
    compare = api.get("/api/intel/channels/chn_demo_cronicas/study/compare", params={"ids": f"{video[0]['id']},{video[1]['id']}"})
    assert compare.status_code == 200 and len(compare.json()["columns"]) == 2
    assert api.post("/api/intel/channels/chn_demo_cronicas/competitors", json={"reference": "@demo3"}).status_code == 401
    created = api.post("/api/intel/channels/chn_demo_cronicas/competitors", json={"reference": "@demo3", "name": "Era"}, headers=HEADERS)
    assert created.status_code == 201
    detail = api.get(f"/api/intel/channels/chn_demo_cronicas/competitors/{created.json()['id']}")
    assert detail.status_code == 200 and detail.json()["linked"]
    assert api.get(f"/api/intel/channels/chn_demo_rotas/competitors/{created.json()['id']}").status_code == 404
    report = api.get("/api/intel/channels/chn_demo_cronicas/competitors/report.md")
    assert report.status_code == 200 and "attachment" in report.headers["content-disposition"]
    opportunity = api.post("/api/intel/channels/chn_demo_cronicas/opportunities", json={"title": "Oportunidade boa"}, headers=HEADERS)
    assert opportunity.status_code == 201
    idea = api.post(f"/api/intel/channels/chn_demo_cronicas/opportunities/{opportunity.json()['id']}/idea", json={"format": "long"}, headers=HEADERS)
    assert idea.status_code == 201


def test_deleting_channel_removes_study_and_opportunities(api, demo_cfg):
    video = api.get("/api/intel/explorer?format=long&limit=1").json()["items"][0]["id"]
    api.post("/api/intel/channels/chn_demo_imperios/study", json={"video_id": video}, headers=HEADERS)
    api.post("/api/intel/channels/chn_demo_imperios/opportunities", json={"title": "Oportunidade boa"}, headers=HEADERS)
    assert api.post("/api/studio/channels/chn_demo_imperios/delete", json={"confirm_name": store.DEMO_CHANNELS[2]["name"]}, headers=HEADERS).status_code == 200
    conn = connect(demo_cfg.db_path)
    for table in ("study_videos", "editorial_opportunities"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE managed_channel_id = 'chn_demo_imperios'").fetchone()[0] == 0
    conn.close()
