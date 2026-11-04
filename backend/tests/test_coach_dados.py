"""Coach sobre dados concretos: referências, justificativas, rótulo honesto e nenhum derivado sem aprovação."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.connectors.youtube_data import YouTubeDataClient
from app.db import connect, migrate
from app.intel import coach, discovery
from app.studio import store
from tests.yt_mock import FakeYouTube

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
KEY = "AIzaTESTKEY0000000000000000"


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="live", youtube_api_key=KEY, data_dir=tmp_path, api_token="t", quota_default_daily=500, quota_search_daily=20)


@pytest.fixture
def db(cfg):
    conn = connect(cfg.live_db_path)
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def studio(cfg):
    conn = store.open_studio(cfg)
    yield conn
    conn.close()


@pytest.fixture
def real(studio):
    return store.create_channel(studio, {"name": "Canal Real", "language": "pt", "keywords": ["roma"], "positioning": "História sem enrolação"})


def factory(fake):
    return lambda settings, conn: YouTubeDataClient(settings, conn, transport=fake.transport(), sleep=lambda _s: None, clock=lambda: NOW)


def search(db, studio, cfg, channel_id, fake=None):
    return discovery.discover(db, studio, cfg, target="videos", niche=None, subniche=None, free_text="roma antiga", language="pt", country="BR", days=None, video_format=None, max_subscribers=None, channel_id=channel_id, now=NOW, factory=factory(fake or FakeYouTube(NOW)))


def ask(db, studio, cfg, channel_id, question, provider=None):
    created = coach.ask(db, studio, cfg, channel_id, question, None, NOW, provider)
    message = coach.get_conversation(db, channel_id, created["conversation_id"])["messages"][-1]
    return message


def test_answer_uses_concrete_items_from_the_real_search(db, studio, cfg, real):
    fake = FakeYouTube(NOW)
    search(db, studio, cfg, real["id"], fake)
    message = ask(db, studio, cfg, real["id"], "Qual assunto devo produzir para este canal?")
    content = message["content"]
    text = " ".join(item["text"] for item in content["observations"])
    assert "Roma antiga parte 0" in text and "Canal Falso" in text and "50000 views públicas medidas em 2026-11-04" in text
    assert any(source["url"] == "https://www.youtube.com/watch?v=vid00" for source in content["sources"].values())
    assert all(item["refs"] for item in content["observations"])


def test_recommendations_have_reason_and_source(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    content = ask(db, studio, cfg, real["id"], "Quais vídeos encontrei na pesquisa?")["content"]
    assert content["recommendations"]
    for item in content["recommendations"]:
        assert item["why"] and item["refs"] and all(ref in content["sources"] for ref in item["refs"])
    assert "Não é uma nota de qualidade" in content["recommendations"][0]["why"]


def test_answer_declares_rules_and_data_used(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    message = ask(db, studio, cfg, real["id"], "Qual assunto devo produzir?")
    content = message["content"]
    assert message["is_ai"] is False and content["generated_by"]["is_ai"] is False and "Não é análise de IA" in content["generated_by"]["note"]
    assert any(item["tool"] == "resultados_pesquisa" and item["items"] > 0 for item in content["data_used"])
    assert any("sem IA" in item for item in content["limitations"])


def test_provider_status_is_honest(cfg):
    status = coach.provider_status(cfg)
    assert status["is_ai"] is False and status["label"] == "Por regras, sem IA" and "Não é análise de IA" in status["note"]


def test_without_search_answer_says_what_is_missing(db, studio, cfg, real):
    content = ask(db, studio, cfg, real["id"], "Quais vídeos encontrei na pesquisa?")["content"]
    assert any("pesquisa associada a este canal" in item for item in content["limitations"])
    assert next(item for item in content["data_used"] if item["tool"] == "resultados_pesquisa")["items"] == 0


def test_saved_items_reach_the_answer(db, studio, cfg, real):
    created = search(db, studio, cfg, real["id"])
    discovery.save_item(db, studio, cfg, real["id"], item_type="tema", item_id=None, text="Sal na economia de Roma", note="ângulo meu", run_id=created["id"], now=NOW)
    content = ask(db, studio, cfg, real["id"], "Que oportunidades existem para este canal?")["content"]
    assert any("Sal na economia de Roma" in item["text"] and "ângulo meu" in item["text"] for item in content["observations"])
    assert any("vira ideia" in item["text"] and item["why"] for item in content["recommendations"])


def test_no_derived_value_reaches_the_answer_without_approval(db, studio, cfg, real):
    fake = FakeYouTube(NOW)
    store.add_competitor(studio, real["id"], "Referência", "UCfake1", "")
    search(db, studio, cfg, real["id"], fake)
    content = ask(db, studio, cfg, real["id"], "Quais concorrentes merecem acompanhamento?")["content"]
    text = json.dumps(content, ensure_ascii=False).lower()
    for forbidden in ("vph", "idr", "outlier", "acima da média", "nos últimos 90 dias", "mais frequente"):
        assert forbidden not in text, forbidden
    assert not any("Acompanhe de perto" in item["text"] for item in content["recommendations"])
    assert any("bloqueadas" in item for item in content["limitations"])


def test_channel_isolation_in_results(db, studio, cfg, real):
    other = store.create_channel(studio, {"name": "Outro", "language": "pt"})
    search(db, studio, cfg, real["id"])
    assert "Roma antiga parte" not in json.dumps(ask(db, studio, cfg, other["id"], "Quais vídeos encontrei na pesquisa?")["content"], ensure_ascii=False)


class FakeAI(coach.LLMProvider):
    name = "claude_cli"
    model = "claude-teste"

    def __init__(self, answer):
        self._answer = answer
        self.users = []

    def complete(self, system, user, schema):
        self.users.append((system, user))
        if "calls" in schema.get("properties", {}):
            return {"calls": [{"tool": "resultados_pesquisa"}]}, {"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.001}
        return self._answer, {"input_tokens": 2, "output_tokens": 2, "cost_usd": 0.002}


def test_ai_receives_concrete_data_and_is_labelled(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    provider = FakeAI({"observations": [{"text": "O vídeo vid00 tem 50000 views.", "refs": ["video:vid00"]}], "hypotheses": [], "recommendations": [{"text": "Estude o vídeo.", "why": "Tem o ângulo mais próximo do canal.", "refs": ["video:vid00"]}], "limitations": []})
    message = ask(db, studio, cfg, real["id"], "O que estudar?", provider)
    assert message["is_ai"] is True and message["content"]["generated_by"]["is_ai"] is True and "Claude" in message["content"]["generated_by"]["label"]
    system, user = provider.users[-1]
    assert "50000" in user and "Roma antiga parte 0" in user and "why" in system
    assert message["content"]["recommendations"][0]["why"] == "Tem o ângulo mais próximo do canal."


def test_ai_recommendation_without_support_is_marked(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    provider = FakeAI({"observations": [], "hypotheses": [], "recommendations": [{"text": "Faça vídeos curtos.", "refs": []}], "limitations": []})
    item = ask(db, studio, cfg, real["id"], "O que fazer?", provider)["content"]["recommendations"][0]
    assert "Trate como opinião" in item["why"]


def test_ai_invented_reference_is_refused(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    provider = FakeAI({"observations": [{"text": "Dado inventado.", "refs": ["video:naoexiste"]}], "hypotheses": [], "recommendations": [], "limitations": []})
    with pytest.raises(coach.CoachError):
        ask(db, studio, cfg, real["id"], "O que fazer?", provider)


def test_ai_promise_in_justification_is_refused(db, studio, cfg, real):
    search(db, studio, cfg, real["id"])
    provider = FakeAI({"observations": [], "hypotheses": [], "recommendations": [{"text": "Faça isto.", "why": "Vai viralizar com certeza.", "refs": ["video:vid00"]}], "limitations": []})
    with pytest.raises(coach.CoachError):
        ask(db, studio, cfg, real["id"], "O que fazer?", provider)
