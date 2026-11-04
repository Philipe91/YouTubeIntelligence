"""Valida os módulos de inteligência no navegador real, nos dois cenários que importam.

Cenário demo: dados fictícios, tudo liberado.
Cenário restrito: modo real sem aprovação do Google e sem chave. O banco é preenchido por um YouTube
falso, em processo, antes de o aplicativo subir. Nenhuma chamada sai para a internet.

Uso, a partir da raiz, com o frontend já compilado:
    uv run --directory backend --with playwright python ../scripts/teste_inteligencia.py --dados <pasta vazia> --saida ../docs/evidencias
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path[:0] = [str(BACKEND)]
API_PORT, WEB_PORT = 8012, 3012
WEB = f"http://127.0.0.1:{WEB_PORT}"
CANAL = "chn_demo_cronicas"
OUTRO = "chn_demo_rotas"
EVIDENCIA: dict = {"passos": [], "cenarios": {}}
ERROS: list[str] = []


def passo(nome: str, **dados) -> None:
    EVIDENCIA["passos"].append({"passo": nome, **dados})
    print(f"ok  {nome}" + (f"  {json.dumps(dados, ensure_ascii=False)}" if dados else ""), flush=True)


def ps(script: str, env: dict) -> str:
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True, env={**os.environ, "NEXT_TELEMETRY_DISABLED": "1", **env}, timeout=120)
    if done.returncode:
        raise RuntimeError(done.stderr or done.stdout)
    return done.stdout


class App:
    def __init__(self, dados: Path, modo: str):
        self.env = {"YTI_DATA_DIR": str(dados), "YTI_MODE": modo}

    def __enter__(self):
        ps(f"& '{ROOT / 'scripts' / 'iniciar.ps1'}' -ApiPort {API_PORT} -WebPort {WEB_PORT}", self.env)
        for _ in range(90):
            try:
                urllib.request.urlopen(f"{WEB}/pesquisa", timeout=10)
                return self
            except Exception:
                time.sleep(1)
        raise RuntimeError("O aplicativo não respondeu.")

    def __exit__(self, *_exc):
        ps(f"& '{ROOT / 'scripts' / 'parar.ps1'}'", self.env)
        time.sleep(1)


def abrir(context) -> Page:
    page = context.new_page()
    page.on("pageerror", lambda error: ERROS.append(f"{page.url}: {error}"))
    page.on("console", lambda message: ERROS.append(f"{page.url}: {message.text}") if message.type == "error" and "favicon" not in message.text and "ERR_" not in message.text else None)
    return page


def sem_estouro(page: Page, rotulo: str) -> None:
    largura = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert largura <= 1, f"{rotulo}: estouro horizontal de {largura}px"


def rotas_moveis(browser, rotas: list[str]) -> None:
    context = browser.new_context(viewport={"width": 390, "height": 800})
    page = abrir(context)
    for rota in rotas:
        page.goto(f"{WEB}{rota}")
        sem_estouro(page, rota)
    context.close()
    passo("celular sem estouro horizontal", rotas=len(rotas))


def tela(page: Page, saida: Path, nome: str) -> None:
    page.screenshot(path=str(saida / nome), full_page=True)


# --- Cenário demo ---------------------------------------------------------------------------------

def demo_research(page: Page, saida: Path) -> str:
    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("roma")
    page.get_by_label("Associar ao canal").select_option(CANAL)
    page.get_by_label("Formato").select_option("long")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    page.wait_for_url(re.compile(r"/pesquisa/run_"))
    run = page.url.rsplit("/", 1)[-1]
    expect(page.get_by_role("heading", name="roma", exact=True)).to_be_visible()
    expect(page.get_by_text("Dados fictícios").first).to_be_visible()
    expect(page.get_by_text("Longos").first).to_be_visible()
    assert page.get_by_text("Shorts,").count() == 0
    expect(page.get_by_text("Indisponível").first).to_be_visible()
    tela(page, saida, "20_pesquisa_resultado.png")
    passo("pesquisa por tema, com filtro de formato real")

    page.get_by_label("Nome").fill("Roma longos")
    page.get_by_role("button", name="Salvar pesquisa").click()
    expect(page.get_by_text("Salva: Roma longos")).to_be_visible()
    page.goto(f"{WEB}/pesquisa?aba=salvas")
    expect(page.get_by_text("Salva como Roma longos")).to_be_visible()
    passo("salvar e recuperar pesquisa")

    with page.expect_download() as baixado:
        page.goto(f"{WEB}/pesquisa/{run}")
        page.get_by_role("link", name="Exportar CSV").click()
    arquivo = baixado.value.path()
    texto = Path(arquivo).read_text(encoding="utf-8-sig")
    assert texto.startswith("tipo,posicao,id,titulo") and "idr" not in texto.splitlines()[0]
    passo("exportar CSV só com dados crus", linhas=len(texto.splitlines()) - 1)

    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("vikings")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    page.wait_for_url(re.compile(r"/pesquisa/run_"))
    page.get_by_role("button", name="Comparar").click()
    page.wait_for_url(re.compile(r"/pesquisa/comparar"))
    expect(page.get_by_role("heading", name="Nas duas")).to_be_visible()
    passo("comparar duas pesquisas")

    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("história")
    page.get_by_label("O que procurar").select_option("channels")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    page.wait_for_url(re.compile(r"/pesquisa/run_"))
    expect(page.get_by_role("columnheader", name="Inscritos")).to_be_visible()
    passo("busca de canais por nicho")

    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("roma")
    page.get_by_label("O que procurar").select_option("emerging")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    page.wait_for_url(re.compile(r"/pesquisa/run_"))
    expect(page.get_by_text("não uma nota de potencial")).to_be_visible()
    passo("canais pequenos em atividade")

    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("assunto inexistente xyzzy")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    page.wait_for_url(re.compile(r"/pesquisa/run_"))
    expect(page.get_by_text("Nenhum vídeo encontrado.")).to_be_visible()
    passo("resultado vazio com orientação")

    page.goto(f"{WEB}/pesquisa")
    page.get_by_label("Palavra, tema ou nicho").fill("de")
    page.get_by_role("button", name="Pesquisar", exact=True).click()
    expect(page.get_by_role("alert").filter(has_text="palavra com significado")).to_be_visible()
    passo("erro de validação na tela")

    page.goto(f"{WEB}/pesquisa?aba=crescimento")
    expect(page.get_by_role("heading", name="Assuntos em crescimento")).to_be_visible()
    page.goto(f"{WEB}/pesquisa?aba=historico&canal={OUTRO}")
    expect(page.get_by_text("Nenhuma pesquisa aqui ainda.")).to_be_visible()
    page.goto(f"{WEB}/pesquisa?aba=historico&canal={CANAL}")
    expect(page.get_by_role("link", name="roma", exact=True).first).to_be_visible()
    passo("histórico isolado por canal")
    return run


def demo_keywords(page: Page, saida: Path) -> None:
    page.goto(f"{WEB}/palavras")
    page.get_by_label("Termo", exact=True).fill("roma")
    page.get_by_label("Associar ao canal").select_option(CANAL)
    page.get_by_role("button", name="Analisar").click()
    page.wait_for_url(re.compile(r"termo=roma"))
    expect(page.get_by_role("heading", name="Volume de busca")).to_be_visible()
    expect(page.get_by_text("Nenhuma API pública do YouTube informa volume de busca.")).to_be_visible()
    expect(page.get_by_text("Nenhum provedor de estimativa está configurado", exact=False)).to_be_visible()
    expect(page.get_by_role("heading", name="Índice experimental")).to_be_visible()
    tela(page, saida, "21_palavras_visao.png")
    passo("volume indisponível separado do índice experimental")

    for aba, texto in (("Relacionados", "Aparecem juntos nos títulos"), ("Variações", "Nenhuma foi medida"), ("Perguntas", "Modelos de pergunta"), ("Em ascensão", "Mede vídeos monitorados"), ("Vídeos encontrados", "Não é a busca completa")):
        page.get_by_role("link", name=aba, exact=True).click()
        expect(page.get_by_text(texto).first).to_be_visible()
    passo("abas do termo")

    page.get_by_role("button", name="Favoritar").click()
    expect(page.get_by_text("Favorita", exact=True)).to_be_visible()
    page.goto(f"{WEB}/palavras?aba=favoritos&canal={CANAL}")
    expect(page.get_by_role("link", name="roma", exact=True)).to_be_visible()
    page.goto(f"{WEB}/palavras?aba=favoritos&canal={OUTRO}")
    expect(page.get_by_text("Nenhuma favorita neste canal.")).to_be_visible()
    passo("favorita isolada por canal")

    page.goto(f"{WEB}/palavras?aba=para-voce&canal={CANAL}")
    expect(page.get_by_text("YouTube Analytics").first).to_be_visible()
    page.goto(f"{WEB}/palavras?aba=descoberta&canal={CANAL}")
    expect(page.get_by_text("Dados fictícios").first).to_be_visible()
    expect(page.get_by_role("columnheader", name="Minutos assistidos")).to_be_visible()
    page.goto(f"{WEB}/palavras?aba=descoberta&canal={OUTRO}")
    expect(page.get_by_text("Termos de descoberta indisponíveis.")).to_be_visible()
    page.goto(f"{WEB}/palavras?aba=historico&canal={CANAL}")
    expect(page.get_by_role("link", name="roma", exact=True).first).to_be_visible()
    passo("listas do canal: sugestões, descoberta e histórico")


def cenario_demo(browser, dados: Path, saida: Path) -> None:
    with App(dados, "demo"):
        context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page = abrir(context)
        run = demo_research(page, saida)
        demo_keywords(page, saida)
        context.close()
        rotas_moveis(browser, ["/", "/pesquisa", f"/pesquisa/{run}", "/pesquisa?aba=historico", "/palavras", "/palavras?termo=roma", f"/palavras?aba=para-voce&canal={CANAL}"])


# --- Cenário restrito -----------------------------------------------------------------------------

def preparar_restrito(dados: Path) -> str:
    """Grava no banco real os resultados de um YouTube falso. O aplicativo sobe sem chave depois disso."""
    from tests.yt_mock import FakeYouTube

    from app.config import Settings
    from app.connectors.youtube_data import YouTubeDataClient
    from app.db import connect, migrate
    from app.intel import keywords, research
    from app.studio import store

    now = datetime.now(UTC)
    fake = FakeYouTube(now)
    settings = Settings(mode="live", youtube_api_key="AIzaFAKEONLYFORTEST000000000000", data_dir=dados, api_token="teste", quota_default_daily=100, quota_search_daily=5)
    conn = connect(settings.db_path)
    migrate(conn)
    studio = store.open_studio(settings)
    channel = store.create_channel(studio, {"name": "Canal Real de Teste", "language": "pt", "keywords": ["roma"], "topic_backlog": ["Roma antiga e o sal"]})

    def build(cfg, db):
        return YouTubeDataClient(cfg, db, transport=fake.transport(), sleep=lambda _s: None)

    run = research.run_search(conn, studio, settings, kind="videos", query="roma antiga", channel_id=channel["id"], now=now, factory=build)
    keywords.lookup(conn, studio, settings, "roma antiga", channel["id"], now, factory=build)
    studio.close()
    conn.close()
    return run["id"]


def cenario_restrito(browser, dados: Path, saida: Path) -> None:
    run = preparar_restrito(dados)
    with App(dados, "live"):
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = abrir(context)
        page.goto(f"{WEB}/pesquisa")
        expect(page.get_by_text("Sem chave da API do YouTube")).to_be_visible()
        page.get_by_label("Palavra, tema ou nicho").fill("cartago")
        page.get_by_role("button", name="Pesquisar", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="YOUTUBE_API_KEY")).to_be_visible()
        passo("restrito: sem chave, erro explicado na tela")

        page.goto(f"{WEB}/pesquisa/{run}")
        expect(page.get_by_text("Só dados crus")).to_be_visible()
        expect(page.get_by_text("Roma antiga parte 1", exact=False).first).to_be_visible()
        expect(page.get_by_role("link", name="Abrir no YouTube").first).to_be_visible()
        assert page.get_by_text(re.compile(r"\d+,\dx")).count() == 0
        tela(page, saida, "22_restrito_pesquisa.png")
        passo("restrito: resultado cru, com link e sem score")

        page.goto(f"{WEB}/palavras?termo=roma%20antiga")
        expect(page.get_by_text("Bloqueado").first).to_be_visible()
        page.get_by_role("link", name="Variações", exact=True).click()
        expect(page.get_by_text("Nenhuma foi medida")).to_be_visible()
        page.get_by_role("link", name="Relacionados", exact=True).click()
        expect(page.get_by_text("Bloqueado").first).to_be_visible()
        page.get_by_role("link", name="Em ascensão", exact=True).click()
        expect(page.get_by_text("Este cálculo está bloqueado")).to_be_visible()
        tela(page, saida, "23_restrito_palavras.png")
        passo("restrito: índice, relacionados e ascensão bloqueados; variações seguem úteis")
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dados", required=True, type=Path)
    parser.add_argument("--saida", required=True, type=Path)
    parser.add_argument("--cenarios", default="demo,restrito")
    args = parser.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    telas = args.saida.parent / "telas"
    telas.mkdir(exist_ok=True)
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel="chrome", headless=True)
        try:
            if "demo" in args.cenarios:
                cenario_demo(browser, args.dados / "demo", telas)
            if "restrito" in args.cenarios:
                cenario_restrito(browser, args.dados / "restrito", telas)
        finally:
            browser.close()
    EVIDENCIA["erros_de_pagina"] = ERROS
    (args.saida / "inteligencia_navegador.json").write_text(json.dumps(EVIDENCIA, ensure_ascii=False, indent=1), encoding="utf-8")
    if ERROS:
        raise SystemExit("Erros no navegador:\n" + "\n".join(ERROS[:20]))
    print(f"APROVADO: {len(EVIDENCIA['passos'])} passos")


if __name__ == "__main__":
    main()
