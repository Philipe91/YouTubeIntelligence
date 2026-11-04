"""Descoberta e pesquisas no modo real: filtros, proveniência, conformidade, salvamento e isolamento."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import demo, main
from app.config import Settings
from app.connectors.youtube_data import YouTubeDataClient
from app.db import connect, migrate, utcnow
from app.deps import settings_dep
from app.intel import competitors, discovery, keywords, research
from app.intel import router as intel_router
from app.policy import apply_retention
from app.studio import store
from tests.yt_mock import REAL_INVALID_KEY, FakeYouTube, error_response

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
TOKEN = "segredo"
KEY = "AIzaTESTKEY0000000000000000"
DERIVED_KEYS = {"vph_observed", "vph_average", "idr", "acceleration", "outlier"}


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, quota_default_daily=500, quota_search_daily=20)


@pytest.fixture
def demo_cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def db(cfg):
    conn = connect(cfg.live_db_path)
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def demo_db(demo_cfg):
    conn = connect(demo_cfg.db_path)
    migrate(conn)
    demo.seed_demo(conn, utcnow())
    keywords.seed_demo_terms(conn, utcnow())
    yield conn
    conn.close()


@pytest.fixture
def studio(cfg):
    conn = store.open_studio(cfg)
    store.seed_demo_once(conn)
    yield conn
    conn.close()


@pytest.fixture
def real(studio):
    return store.create_channel(studio, {"name": "Canal Real", "language": "pt", "keywords": ["roma", "império"], "avoid": ["política"]})


@pytest.fixture
def other(studio):
    return store.create_channel(studio, {"name": "Outro Canal", "language": "en", "keywords": ["space"]})


def factory_for(fake):
    return lambda settings, conn: YouTubeDataClient(settings, conn, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: NOW)


def run(db, studio, cfg, fake, **kwargs):
    defaults = dict(target="recent_videos", niche="historia", subniche="antiga", free_text=None, language="pt", country="BR", days=30, video_format=None, max_subscribers=None, channel_id=None)
    return discovery.discover(db, studio, cfg, now=NOW, factory=factory_for(fake), **{**defaults, **kwargs})


# --- Catálogo e termo de busca --------------------------------------------------------------------

def test_catalog_lists_niches_and_every_subniche_has_three_languages():
    data = discovery._load_catalog()
    assert len(data) >= 6
    for niche in data.values():
        for sub in niche["subniches"].values():
            assert all(sub.get(lang) for lang in ("pt", "en", "es"))
    assert {t["key"] for t in discovery.catalog()["targets"]} == set(discovery.TARGETS)


@pytest.mark.parametrize("language,expected", [("pt", "história antiga"), ("en", "ancient history"), ("es", "historia antigua"), ("pt-br", "história antiga"), ("fr", "ancient history")])
def test_query_uses_channel_language(language, expected):
    assert discovery.build_query("historia", "antiga", None, language)[0] == expected


def test_query_puts_typed_text_first():
    assert discovery.build_query("historia", "antiga", "queda de Roma", "pt")[0] == "queda de Roma história antiga"
    assert discovery.build_query(None, None, "só isto", "pt")[0] == "só isto"


@pytest.mark.parametrize("niche,sub,text", [(None, None, None), ("historia", None, None), ("inexistente", None, "x"), ("historia", "inexistente", None), (None, "antiga", None)])
def test_query_rejects_invalid_combinations(niche, sub, text):
    with pytest.raises(store.StudioError):
        discovery.build_query(niche, sub, text, "pt")


# --- Parâmetros enviados à API --------------------------------------------------------------------

def test_recent_videos_send_real_filters(db, studio, cfg):
    fake = FakeYouTube(NOW)
    created = run(db, studio, cfg, fake)
    params = fake.calls[0].url.params
    assert params["q"] == "história antiga" and params["relevanceLanguage"] == "pt" and params["regionCode"] == "BR" and params["order"] == "date"
    assert params["publishedAfter"] == "2026-10-05T00:00:00Z"
    assert created["filters"]["niche"] == "História" and created["filters"]["subniche"] == "Mundo antigo" and created["filters"]["discovery"] is True


def test_clicking_again_at_another_time_uses_cache_and_no_new_search(db, studio, cfg):
    """Com a hora exata na data de corte, cada clique gastava 1 das 100 buscas do dia."""
    fake = FakeYouTube(NOW)
    run(db, studio, cfg, fake)
    calls = len(fake.calls)
    later = NOW + timedelta(minutes=40)
    second = discovery.discover(db, studio, cfg, target="recent_videos", niche="historia", subniche="antiga", free_text=None, language="pt", country="BR", days=30, video_format=None,
                                max_subscribers=None, channel_id=None, now=later,
                                factory=lambda s, c: YouTubeDataClient(s, c, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: later))
    # A busca vem do cache. As estatísticas, com prazo menor, são medidas de novo: 1 unidade geral.
    assert sum(1 for call in fake.calls if call.url.path.endswith("/search")) == 1 and len(fake.calls) == calls + 1
    assert second["provenance"]["api_calls"] == 1 and second["provenance"]["cache_hits"] >= 1


@pytest.mark.parametrize("language,country", [("pt-BR", "BR"), ("pt", "br")])
def test_language_and_country_are_normalized(db, studio, cfg, language, country):
    fake = FakeYouTube(NOW)
    run(db, studio, cfg, fake, language=language, country=country)
    assert fake.calls[0].url.params["relevanceLanguage"] == "pt" and fake.calls[0].url.params["regionCode"] == "BR"


@pytest.mark.parametrize("field,value", [("language", "português!"), ("country", "Brasil"), ("max_subscribers", -5), ("video_format", "vertical"), ("days", 0)])
def test_invalid_filters_never_reach_the_api(db, studio, cfg, field, value):
    fake = FakeYouTube(NOW)
    with pytest.raises(store.StudioError):
        research.run_search(db, studio, cfg, kind="videos", query="roma", channel_id=None, now=NOW, factory=factory_for(fake), **{field: value})
    assert fake.calls == []


# --- Resultado real: o que aparece na tela --------------------------------------------------------

def test_every_video_has_link_title_channel_date_and_public_metric(db, studio, cfg):
    fake = FakeYouTube(NOW)
    created = run(db, studio, cfg, fake)
    data = discovery.view(db, studio, cfg, created["id"])
    assert data["videos"]
    for video in data["videos"]:
        assert video["source_url"].startswith("https://www.youtube.com/watch?v=") and video["title"] and video["channel_title"] and video["published_at"]
        assert video["views"]["kind"] == "measured" and video["views"]["as_of"]


def test_restricted_view_has_no_derived_value_at_all(db, studio, cfg):
    fake = FakeYouTube(NOW)
    created = run(db, studio, cfg, fake)
    data = discovery.view(db, studio, cfg, created["id"])
    assert data["blocked_metrics"] and data["derived_allowed"] is False
    for video in data["videos"]:
        assert video["derived_blocked"] is True and video["outlier"] is None and video["acceleration"] is None
        for key in ("vph_observed", "vph_average", "idr"):
            assert video[key]["value"] is None and video[key]["kind"] == "blocked"


def test_separates_observed_estimated_and_hypotheses(db, studio, cfg, real):
    created = run(db, studio, cfg, FakeYouTube(NOW), channel_id=real["id"], free_text="roma")
    data = discovery.view(db, studio, cfg, created["id"])
    assert data["observed"]["videos"] and data["estimates"] and data["hypotheses"]
    labels = {item["label"] for item in data["estimates"]}
    assert "Volume de busca" in labels
    assert next(item for item in data["estimates"] if item["label"] == "Volume de busca")["value"] is None
    approx = next(item for item in data["estimates"] if item["label"].startswith("Resultados"))
    assert "Não é volume" in approx["note"]


def test_hypotheses_do_not_use_api_text_or_numbers(db, studio, cfg, real):
    fake = FakeYouTube(NOW)
    fake.videos["vid00"]["snippet"]["title"] = "TITULO_DA_API_UNICO"
    created = run(db, studio, cfg, fake, channel_id=real["id"], free_text="roma")
    data = discovery.view(db, studio, cfg, created["id"])
    text = json.dumps(data["hypotheses"], ensure_ascii=False)
    assert "TITULO_DA_API_UNICO" not in text and "50000" not in text and "12345" not in text
    assert "Não são análise de IA" in data["hypotheses_note"]


def test_hypotheses_cross_profile_history_and_avoid_list(db, studio, cfg, real):
    created = run(db, studio, cfg, FakeYouTube(NOW), channel_id=real["id"], free_text="roma política")
    kinds = {item["kind"] for item in discovery.view(db, studio, cfg, created["id"])["hypotheses"]}
    assert {"perfil", "evitar"} <= kinds
    store.add_history(studio, real["id"], title="Roma e o sal", format="long", published_on="2026-01-01", url=None, views=None, result_notes="")
    created = run(db, studio, cfg, FakeYouTube(NOW), channel_id=real["id"], free_text="roma")
    texts = [item["text"] for item in discovery.view(db, studio, cfg, created["id"])["hypotheses"]]
    assert any("Roma e o sal" in text for text in texts)


def test_without_channel_hypothesis_asks_for_one(db, studio, cfg):
    created = run(db, studio, cfg, FakeYouTube(NOW))
    assert discovery.view(db, studio, cfg, created["id"])["hypotheses"][0]["kind"] == "falta"


# --- Formato ---------------------------------------------------------------------------------------

def fake_with_formats():
    fake = FakeYouTube(NOW, video_count=4)
    fake.videos["vid00"]["contentDetails"]["duration"] = "PT40S"
    fake.videos["vid00"]["player"] = {"embedWidth": "405", "embedHeight": "720"}
    fake.videos["vid01"]["contentDetails"]["duration"] = "PT12M"
    fake.videos["vid02"]["contentDetails"]["duration"] = "PT50S"
    fake.videos["vid02"]["player"] = {"embedWidth": "480", "embedHeight": "360"}  # 4:3: a documentação avisa que não confirma nada.
    fake.videos["vid03"]["contentDetails"]["duration"] = "PT50S"
    fake.videos["vid03"].pop("player")
    return fake


def test_format_is_reliable_estimated_or_undetermined(db, studio, cfg):
    created = run(db, studio, cfg, fake_with_formats())
    data = discovery.view(db, studio, cfg, created["id"])
    estimates = data["format_estimates"]
    assert estimates["vid00"]["confidence"] == "estimado" and estimates["vid00"]["format"] == "short"
    assert estimates["vid01"]["confidence"] == "confiavel" and estimates["vid01"]["format"] == "long"
    assert estimates["vid02"]["confidence"] == "indeterminado" and estimates["vid03"]["confidence"] == "indeterminado"


@pytest.mark.parametrize("wanted,expected", [("short", {"vid00"}), ("long", {"vid01"}), ("indeterminate", {"vid02", "vid03"})])
def test_format_filter_never_guesses(db, studio, cfg, wanted, expected):
    created = run(db, studio, cfg, fake_with_formats(), video_format=wanted)
    assert {video["id"] for video in research.run_items(db, cfg, created["id"], limit=50)["videos"]} == expected


def test_short_filter_explains_where_undetermined_went(db, studio, cfg):
    created = run(db, studio, cfg, fake_with_formats(), video_format="short")
    assert any("Indeterminado" in note for note in research.run_items(db, cfg, created["id"])["filter_notes"])


# --- Canais emergentes ----------------------------------------------------------------------------

def emerging_fake():
    fake = FakeYouTube(NOW, video_count=3)
    channels = {"UCaaa": 90000, "UCbbb": 500, "UCccc": 5000000, "UCddd": None}
    for vid, channel in zip(list(fake.videos) + ["extra"], channels, strict=False):
        if vid in fake.videos:
            fake.videos[vid]["snippet"]["channelId"] = channel
    fake.videos["vid99"] = json.loads(json.dumps(fake.videos["vid00"]))
    fake.videos["vid99"]["id"] = "vid99"
    fake.videos["vid99"]["snippet"]["channelId"] = "UCddd"
    original = fake._handle

    def handle(request):
        if request.url.path.endswith("/channels") and not fake.fail_next:
            fake.calls.append(request)
            items = []
            for channel in request.url.params["id"].split(","):
                count = channels[channel]
                stats = {"viewCount": "10", "videoCount": "1", "hiddenSubscriberCount": count is None}
                if count is not None:
                    stats["subscriberCount"] = str(count)
                items.append({"id": channel, "snippet": {"title": f"Canal {channel}"}, "statistics": stats, "contentDetails": {"relatedPlaylists": {"uploads": "UU"}}})
            return httpx.Response(200, json={"items": items})
        return original(request)

    fake.transport = lambda: httpx.MockTransport(handle)
    return fake


def test_emerging_filters_by_raw_subscribers_and_keeps_search_order_without_approval(db, studio, cfg):
    created = run(db, studio, cfg, emerging_fake(), target="emerging_channels", max_subscribers=100000)
    data = research.run_items(db, cfg, created["id"])
    ids = [channel["id"] for channel in data["channels"]]
    # UCaaa vem antes de UCbbb, embora seja maior: ordenar por tamanho seria um ranking.
    assert ids == ["UCaaa", "UCbbb"]
    assert all(channel["source_url"].startswith("https://www.youtube.com/channel/") for channel in data["channels"])


def test_emerging_hidden_subscribers_are_not_treated_as_zero(db, studio, cfg):
    created = run(db, studio, cfg, emerging_fake(), target="emerging_channels", max_subscribers=100000)
    assert "UCddd" not in [channel["id"] for channel in research.run_items(db, cfg, created["id"])["channels"]]


# --- Proveniência ---------------------------------------------------------------------------------

def test_run_records_where_and_when_data_came_from(db, studio, cfg):
    created = run(db, studio, cfg, FakeYouTube(NOW))
    data = created["provenance"]
    assert data["source"] == "youtube_data_api" and data["api_calls"] >= 2 and data["newest_data_at"] == "2026-11-04T12:00:00Z" and set(data["methods"]) >= {"search.list", "videos.list"}
    assert created["fictional"] is False and created["simulated"] is False


def test_simulated_api_is_never_presented_as_youtube(tmp_path, db, studio):
    settings = Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token=TOKEN, youtube_base_url="http://127.0.0.1:9/")
    created = run(db, studio, settings, FakeYouTube(NOW))
    assert created["simulated"] is True and created["provenance"]["source"] == "api_simulada_teste"


def test_demo_run_records_fictional_source_and_no_calls(demo_db, studio, demo_cfg):
    def explode(*_a):
        raise AssertionError("o modo demo não abre cliente")
    created = discovery.discover(demo_db, studio, demo_cfg, target="videos", niche="historia", subniche="antiga", free_text="roma", language="pt", country=None, days=None, video_format=None,
                                 max_subscribers=None, channel_id="chn_demo_cronicas", now=utcnow(), factory=explode)
    assert created["fictional"] and created["provenance"]["source"] == "dados_ficticios" and created["provenance"]["api_calls"] == 0 and created["result_count"] > 0


def test_csv_export_keeps_only_raw_data_from_real_run(db, studio, cfg):
    created = run(db, studio, cfg, FakeYouTube(NOW))
    body, name = research.export_csv(db, cfg, created["id"])
    assert "youtube" in name and "idr" not in body.splitlines()[0].lower() and "vph" not in body.splitlines()[0].lower()


# --- Erros chegam legíveis ------------------------------------------------------------------------

@pytest.mark.parametrize("failure,code,status", [
    (httpx.Response(400, json=REAL_INVALID_KEY), "api_credential", 424), (error_response(403, "accessNotConfigured"), "api_credential", 424),
    (error_response(403, "quotaExceeded"), "quota_google", 429), (httpx.Response(200, text="<html>"), "youtube_error", 502),
])
def test_failures_become_clear_errors_and_store_nothing(db, studio, cfg, failure, code, status):
    fake = FakeYouTube(NOW)
    fake.fail_next = [failure]
    with pytest.raises(store.StudioError) as caught:
        run(db, studio, cfg, fake)
    assert caught.value.code == code and caught.value.status == status and KEY not in caught.value.message
    assert db.execute("SELECT COUNT(*) AS n FROM research_runs").fetchone()["n"] == 0


def test_network_failure_is_retryable(db, studio, cfg):
    fake = FakeYouTube(NOW)
    fake.fail_next = [httpx.ConnectError("x")] * 4
    with pytest.raises(store.StudioError) as caught:
        run(db, studio, cfg, fake)
    assert caught.value.retryable and "conexão" in caught.value.message


def test_missing_key_is_clear(tmp_path, studio):
    settings = Settings(mode="live", data_dir=tmp_path, api_token=TOKEN)
    conn = connect(settings.live_db_path)
    migrate(conn)
    with pytest.raises(store.StudioError) as caught:
        discovery.discover(conn, studio, settings, target="videos", niche="historia", subniche="antiga", free_text=None, language="pt", country=None, days=None, video_format=None, max_subscribers=None, channel_id=None, now=NOW)
    assert caught.value.code == "api_key_missing" and "Sistema e cotas" in caught.value.message
    conn.close()


# --- Salvar e associar ----------------------------------------------------------------------------

def test_save_video_title_channel_and_theme_associated_to_channel(db, studio, cfg, real):
    created = run(db, studio, cfg, FakeYouTube(NOW), channel_id=real["id"])
    for item_type, item_id, text in (("video", "vid01", None), ("titulo", "vid01", None), ("canal", "UCfake1", None), ("tema", None, "Sal na economia de Roma")):
        discovery.save_item(db, studio, cfg, real["id"], item_type=item_type, item_id=item_id, text=text, note="nota", run_id=created["id"], now=NOW)
    items = competitors.list_opportunities(db, real["id"])
    assert {item["item_type"] for item in items} == {"video", "titulo", "canal", "tema"}
    assert all(item["niche"] == "História" and item["subniche"] == "Mundo antigo" and item["note"] == "nota" for item in items)
    assert next(i for i in items if i["item_type"] == "canal")["source_url"].startswith("https://www.youtube.com/channel/")
    assert next(i for i in items if i["item_type"] == "video")["source_url"].startswith("https://www.youtube.com/watch")


def test_saving_api_item_stores_only_the_id(db, studio, cfg, real):
    run(db, studio, cfg, FakeYouTube(NOW), channel_id=real["id"])
    discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text="texto ignorado", note="", run_id=None, now=NOW)
    assert db.execute("SELECT title FROM editorial_opportunities").fetchone()["title"] == ""


def test_saving_twice_is_refused(db, studio, cfg, real):
    run(db, studio, cfg, FakeYouTube(NOW))
    discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text=None, note="", run_id=None, now=NOW)
    with pytest.raises(store.StudioError) as caught:
        discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text=None, note="", run_id=None, now=NOW)
    assert caught.value.code == "already_saved"


@pytest.mark.parametrize("item_type,item_id,text,code", [("video", "naoexiste", None, "video_not_found"), ("canal", "naoexiste", None, "channel_not_found"), ("tema", None, "x", "invalid_field"), ("outro", None, "abc", "invalid_field")])
def test_saving_invalid_items_is_refused(db, studio, cfg, real, item_type, item_id, text, code):
    with pytest.raises(store.StudioError) as caught:
        discovery.save_item(db, studio, cfg, real["id"], item_type=item_type, item_id=item_id, text=text, note="", run_id=None, now=NOW)
    assert caught.value.code == code


def test_saved_items_are_isolated_by_channel(db, studio, cfg, real, other):
    run(db, studio, cfg, FakeYouTube(NOW))
    discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text=None, note="", run_id=None, now=NOW)
    assert competitors.list_opportunities(db, other["id"]) == []
    item = competitors.list_opportunities(db, real["id"])[0]
    with pytest.raises(store.StudioError) as caught:
        competitors.discard_opportunity(db, other["id"], item["id"], NOW)
    assert caught.value.status == 404


def test_fictional_channel_cannot_receive_real_data(db, studio, cfg):
    with pytest.raises(store.StudioError) as caught:
        run(db, studio, cfg, FakeYouTube(NOW), channel_id="chn_demo_cronicas")
    assert caught.value.code == "channel_data_mismatch"


def test_real_channel_cannot_receive_fictional_data(demo_db, studio, demo_cfg, real):
    with pytest.raises(store.StudioError) as caught:
        discovery.save_item(demo_db, studio, demo_cfg, real["id"], item_type="tema", item_id=None, text="tema", note="", run_id=None, now=NOW)
    assert caught.value.code == "channel_data_mismatch"


def test_api_video_saved_needs_own_words_to_become_idea(db, studio, cfg, real):
    run(db, studio, cfg, FakeYouTube(NOW))
    discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text=None, note="", run_id=None, now=NOW)
    item = competitors.list_opportunities(db, real["id"])[0]
    with pytest.raises(store.StudioError) as caught:
        competitors.opportunity_to_idea(db, studio, real["id"], item["id"], "long", NOW)
    assert caught.value.code == "subject_required"
    idea = competitors.opportunity_to_idea(db, studio, real["id"], item["id"], "long", NOW, "Um ângulo meu sobre Roma")
    assert idea["subject"] == "Um ângulo meu sobre Roma"
    assert "Roma antiga parte" not in json.dumps(studio.execute("SELECT * FROM recommendations WHERE id = ?", (idea["id"],)).fetchone()["subject"])


def test_retention_removes_api_text_but_saved_item_reports_removed(db, studio, cfg, real):
    run(db, studio, cfg, FakeYouTube(NOW))
    discovery.save_item(db, studio, cfg, real["id"], item_type="video", item_id="vid01", text=None, note="", run_id=None, now=NOW)
    apply_retention(db, cfg, NOW + timedelta(days=40))
    item = competitors.list_opportunities(db, real["id"])[0]
    assert item["removed"] is True and "removido" in item["title"] and item["source_url"] is None


# --- Rotas ----------------------------------------------------------------------------------------

@pytest.fixture
def web(cfg):
    main.app.dependency_overrides[settings_dep] = lambda: cfg
    main.app.dependency_overrides[intel_router.client_factory] = lambda: factory_for(FakeYouTube(NOW))
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_routes_search_view_and_save(web, real):
    assert web.post("/api/intel/discovery/search", json={"niche": "historia", "subniche": "antiga"}).status_code == 401
    headers = {"X-YTI-Token": TOKEN}
    created = web.post("/api/intel/discovery/search", json={"niche": "historia", "subniche": "antiga", "channel_id": real["id"], "language": "pt", "days": 30}, headers=headers)
    assert created.status_code == 201
    run_id = created.json()["id"]
    page = web.get(f"/api/intel/discovery/runs/{run_id}")
    assert page.status_code == 200 and page.json()["videos"] and page.json()["channel"]["name"] == "Canal Real"
    saved = web.post(f"/api/intel/channels/{real['id']}/saved-items", json={"item_type": "tema", "text": "Tema meu", "run_id": run_id}, headers=headers)
    assert saved.status_code == 201
    assert web.get("/api/intel/discovery/catalog").json()["niches"]
    assert web.get("/api/intel/discovery/runs/naoexiste").status_code == 404
