"""Smart Dashboard: conteúdo real, isolamento, conformidade e ferramenta do agente."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import demo, main
from app.config import Settings
from app.connectors.youtube_data import YouTubeDataClient
from app.db import connect, migrate, utcnow
from app.intel import competitors, feed, ideas, keywords, research
from app.scheduler import ensure_jobs
from app.studio import store
from tests.conftest import APPROVED
from tests.yt_mock import FakeYouTube

NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)
TOKEN = "segredo-de-teste"
KEY = "AIzaTESTKEY0000000000000000"


@pytest.fixture
def demo_cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def live_cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_default_daily=100, quota_search_daily=5)


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


def seed_live(live_db, studio, settings):
    channel = store.create_channel(studio, {"name": "Canal Vivo", "keywords": ["roma"], "formats": ["long"]})

    def build(cfg, conn):
        return YouTubeDataClient(cfg, conn, transport=FakeYouTube(NOW).transport(), sleep=lambda _s: None, clock=lambda: NOW)

    research.run_search(live_db, studio, settings, kind="videos", query="roma", channel_id=channel["id"], now=NOW, factory=build)
    return channel


def test_demo_feed_has_every_requested_block_with_links(demo_db, studio, demo_cfg):
    ensure_jobs(demo_db)  # A rota da API faz isso antes de montar o feed.
    ideas.generate(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())
    data = feed.build(demo_db, studio, demo_cfg)
    assert data["fictional"] and data["channels"] and data["research"]["opportunities"] and data["research"]["videos"] and data["research"]["trends"]
    assert data["title_suggestions"] and data["pending"] and data["collection"]["jobs"] and data["availability"] and data["compliance"]["derived_allowed"]
    assert all(item["href"].startswith("/") for item in data["pending"] + data["title_suggestions"])
    volume = next(item for item in data["availability"] if item["label"] == "Volume de busca")
    assert volume["state"] == "indisponível"
    assert next(item for item in data["availability"] if item["label"] == "CTR e impressões")["state"] == "indisponível"


def test_saved_recent_and_opportunities_show_up(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow())
    keywords.lookup(demo_db, studio, demo_cfg, "vikings", "chn_demo_cronicas", utcnow())
    competitors.add_opportunity(demo_db, studio, demo_cfg, "chn_demo_cronicas", "Ângulo novo", "", None, utcnow())
    ideas.generate(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())
    ideas.act(studio, "chn_demo_cronicas", ideas.list_ideas(studio, "chn_demo_cronicas", limit=1)["items"][0]["id"], "salvar")
    data = feed.build(demo_db, studio, demo_cfg, "chn_demo_cronicas")
    assert [r["id"] for r in data["recent_searches"]] == [run["id"]] and data["recent_keywords"][0]["term"] == "vikings"
    assert data["open_opportunities"][0]["title"] == "Ângulo novo" and data["saved_ideas"]


def test_feed_is_isolated_by_channel(demo_db, studio, demo_cfg):
    research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow())
    competitors.add_opportunity(demo_db, studio, demo_cfg, "chn_demo_cronicas", "Ângulo novo", "", None, utcnow())
    ideas.generate(demo_db, studio, demo_cfg, "chn_demo_cronicas", utcnow())
    other = feed.build(demo_db, studio, demo_cfg, "chn_demo_rotas")
    assert other["recent_searches"] == [] and other["open_opportunities"] == [] and other["saved_ideas"] == []
    assert not any("Crônicas" in item["channel"] for item in other["pending"] + other["title_suggestions"])


def test_real_channel_in_demo_mode_sees_no_fictional_research(demo_db, studio, demo_cfg):
    real = store.create_channel(studio, {"name": "Real", "keywords": ["roma"]})
    data = feed.build(demo_db, studio, demo_cfg, real["id"])
    assert data["fictional"] is False and "não recebe dados fictícios" in data["research"]["unavailable_reason"]
    assert data["research"]["videos"] == [] and data["recent_searches"] == [] and data["research"]["opportunities"] == []


def test_restricted_feed_is_useful_and_has_no_derived_values(live_db, studio, live_cfg):
    channel = seed_live(live_db, studio, live_cfg)
    data = feed.build(live_db, studio, live_cfg, channel["id"])
    assert data["compliance"]["blocked"] and "Google" in data["compliance"]["reason"]
    assert data["research"]["opportunities"] == [] and data["research"]["trends"] == []
    assert data["research"]["videos"] and all(v["idr"]["value"] is None and v["views"]["value"] is not None for v in data["research"]["videos"])
    assert data["recent_searches"] and data["fictional"] is False


def test_approved_feed_unlocks(live_db, studio, tmp_path):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, quota_default_daily=100, quota_search_daily=5, compliance=APPROVED)
    channel = seed_live(live_db, studio, settings)
    data = feed.build(live_db, studio, settings, channel["id"])
    assert data["compliance"]["derived_allowed"] and data["compliance"]["blocked"] == []


def test_no_key_is_shown_in_collection_and_availability(live_db, studio, tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path)
    ensure_jobs(live_db)
    data = feed.build(live_db, studio, settings)
    assert next(i for i in data["availability"] if i["label"] == "Vídeos e canais")["state"] == "falta chave"
    assert next(j for j in data["collection"]["jobs"] if j["name"] == "snapshots")["note"] == "Precisa de YOUTUBE_API_KEY."


def test_empty_database_does_not_break(live_db, studio, tmp_path):
    settings = Settings(mode="live", data_dir=tmp_path)
    data = feed.build(live_db, studio, settings)
    assert data["research"]["videos"] == [] and data["recent_searches"] == []


def test_api_feed_and_unknown_channel(demo_cfg):
    main.app.dependency_overrides[main.settings_dep] = lambda: demo_cfg
    try:
        client = TestClient(main.app, base_url="http://127.0.0.1")
        assert client.get("/api/intel/feed").status_code == 200
        assert client.get("/api/intel/feed?channel_id=nao_existe").status_code == 404
        assert client.get("/api/intel/feed?format=outro").status_code == 422
    finally:
        main.app.dependency_overrides.clear()


def test_agent_summary_is_read_only_and_scoped(demo_db, studio, demo_cfg):
    run = research.run_search(demo_db, studio, demo_cfg, kind="videos", query="roma", channel_id="chn_demo_cronicas", now=utcnow())
    research.save_run(demo_db, run["id"], "Roma")
    mine = feed.agent_summary(demo_db, studio, demo_cfg, "chn_demo_cronicas")
    assert mine["saved_searches"][0]["id"] == run["id"] and mine["search_volume"] == "indisponivel"
    assert feed.agent_summary(demo_db, studio, demo_cfg, "chn_demo_rotas")["saved_searches"] == []
    real = store.create_channel(studio, {"name": "Real"})
    assert feed.agent_summary(demo_db, studio, demo_cfg, real["id"])["research_available"] is False


def test_mcp_tool_exists_and_answers(tmp_path, monkeypatch):
    monkeypatch.setenv("YTI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("YTI_MODE", "demo")
    from app.studio import mcp_server

    names = {tool.name for tool in asyncio.run(mcp_server.server.list_tools())}
    assert "get_channel_intelligence" in names and not any(word in name for name in names for word in ("publish_video", "upload", "authorize", "shell"))
    answer = mcp_server.get_channel_intelligence("chn_demo_cronicas")
    assert answer["ok"] is True and answer["data"]["channel"]["id"] == "chn_demo_cronicas" and json.dumps(answer, ensure_ascii=False)
    assert mcp_server.get_channel_intelligence("nao_existe")["error"]["code"] == "channel_not_found"
