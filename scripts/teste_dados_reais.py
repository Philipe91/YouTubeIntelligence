"""Valida no navegador os fluxos da Fase 6, sem chave real e sem acessar o YouTube.

Cenário demo: dados fictícios, sem chave.
Cenário sem chave: modo real sem YOUTUBE_API_KEY, com instruções na tela.
Cenário simulado: modo real falando com uma API simulada neste computador, no formato oficial. Exercita o caminho
inteiro, do clique à chamada HTTP e aos erros, mas NÃO prova que a API do Google responde assim: a tela mostra
"API simulada de teste" e nada disto conta como validação real. Para isso, use scripts/validar_api_real.py.

Uso, a partir da raiz, com o frontend compilado:
    uv run --directory backend --with playwright python ../scripts/teste_dados_reais.py --dados <pasta vazia> --saida ../docs/evidencias
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402
from teste_inteligencia import API_PORT, CANAL, ERROS, EVIDENCIA, OUTRO, WEB, App, abrir, passo, rotas_moveis, tela  # noqa: E402

FAKE_PORT = 8913
FAKE_KEY = "AIzaFAKEONLYFORTEST000000000000"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")
# Valor calculado: "3,2x" ou "120/h". A palavra VPH pode aparecer, no aviso de que ela está bloqueada.
SCORE = re.compile(r"\d+(,\d+)?\s?x\b|\d\s?/\s?h\b|\d+ de 100")


class ApiSimulada:
    """Servidor local com as respostas do simulador dos testes, já no formato oficial."""

    def __init__(self):
        from tests.yt_mock import FakeYouTube

        self.fake = FakeYouTube(datetime.now(UTC))
        for video in self.fake.videos.values():
            video["snippet"]["thumbnails"] = {"medium": {"url": f"http://127.0.0.1:{FAKE_PORT}/thumb/{video['id']}.png"}}
        self.fake.channel["snippet"]["thumbnails"] = {"default": {"url": f"http://127.0.0.1:{FAKE_PORT}/thumb/canal.png"}}
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                if self.path.startswith("/thumb/"):
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.end_headers()
                    self.wfile.write(PNG)
                    return
                try:
                    response = parent.fake._handle(httpx.Request("GET", f"http://127.0.0.1:{FAKE_PORT}{self.path}"))
                except httpx.TransportError:
                    self.close_connection = True
                    self.connection.close()
                    return
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                self.end_headers()
                self.wfile.write(response.content)

        self.server = ThreadingHTTPServer(("127.0.0.1", FAKE_PORT), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def sem_score(page: Page, rotulo: str) -> None:
    assert page.locator("main").get_by_text(SCORE).count() == 0, f"{rotulo}: apareceu valor derivado"


# --- Demo -----------------------------------------------------------------------------------------

def demo(browser, dados: Path, telas: Path) -> None:
    with App(dados, "demo"):
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = abrir(context)

        page.goto(f"{WEB}/sistema")
        expect(page.get_by_text("Validação real pendente")).to_be_visible()
        expect(page.get_by_text("Nenhuma consulta com dados reais")).to_be_visible()
        expect(page.get_by_text("Sem chave configurada")).to_be_visible()
        expect(page.get_by_text("ative a YouTube Data API v3", exact=False)).to_be_visible()
        assert page.get_by_role("button", name="Testar conexão").count() == 0
        tela(page, telas, "40_sistema_sem_chave.png")
        passo("sem chave: pendente, com passos, e o modo demonstração segue funcionando")

        page.goto(f"{WEB}/descobrir")
        page.get_by_label("Nicho e subnicho").select_option("historia/imperios")
        page.get_by_label("Assunto, para afinar o recorte").fill("roma")
        page.get_by_label("O que procurar").select_option("videos")
        page.get_by_label("Período").select_option("")
        page.get_by_label("Para qual canal").select_option(CANAL)
        page.get_by_role("button", name="Descobrir", exact=True).click()
        page.wait_for_url(re.compile(r"/descobrir/run_"))
        for titulo in ("Observado", "Estimado", "Hipóteses editoriais"):
            expect(page.get_by_role("heading", name=titulo, exact=True)).to_be_visible()
        expect(page.get_by_text("Dados fictícios").first).to_be_visible()
        expect(page.get_by_text("Nenhuma chamada à internet")).to_be_visible()
        expect(page.get_by_text("Volume de busca: indisponível")).to_be_visible()
        expect(page.get_by_text("Não são análise de IA", exact=False)).to_be_visible()
        tela(page, telas, "41_descoberta_demo.png")
        passo("descoberta: observado, estimado e hipóteses separados, com dados fictícios rotulados")

        page.get_by_role("button", name="Salvar vídeo").first.click()
        expect(page.get_by_text("Salvo.").first).to_be_visible()
        page.get_by_role("button", name="Salvar título").first.click()
        page.get_by_label("Tema, com as suas palavras").fill("O sal na economia de Roma")
        page.get_by_label("Sua hipótese ou nota").fill("Ângulo pouco usado")
        page.get_by_role("button", name="Salvar tema").click()
        expect(page.get_by_text("Tema salvo.")).to_be_visible()
        page.get_by_role("button", name="Agendar").click()
        expect(page.get_by_role("status").filter(has_text="Agendada.")).to_be_visible()
        page.goto(f"{WEB}/descobrir?aba=salvos&canal={CANAL}")
        expect(page.get_by_text("O sal na economia de Roma")).to_be_visible()
        expect(page.get_by_text("Ângulo pouco usado", exact=False)).to_be_visible()
        tela(page, telas, "42_salvos.png")
        tema = page.locator("li").filter(has_text="O sal na economia de Roma")
        tema.get_by_role("button", name="Virar ideia").click()
        expect(page.locator("li").filter(has_text="O sal na economia de Roma").get_by_text("Virou ideia")).to_be_visible()
        video = page.locator("li").filter(has_text="Vídeo").first
        video.get_by_role("button", name="Virar ideia").click()
        expect(page.get_by_text("Escreva com as suas palavras", exact=False).or_(video.get_by_label("Assunto, com as suas palavras"))).to_be_visible()
        passo("salvar vídeo, título e tema por canal; tema vira ideia; vídeo pede o assunto em palavras suas")

        page.goto(f"{WEB}/descobrir?aba=salvos&canal={OUTRO}")
        expect(page.get_by_text("Nada salvo neste canal.")).to_be_visible()
        passo("salvos: isolados por canal")

        page.goto(f"{WEB}/automacao")
        expect(page.get_by_text("Só dados fictícios")).to_be_visible()
        expect(page.get_by_text("roma", exact=False).first).to_be_visible()
        assert page.get_by_role("button", name="Aprovar limite e ligar").count() == 0
        page.get_by_role("button", name=re.compile("Rodar as vencidas")).click()
        expect(page.get_by_text("Rodada concluída.", exact=False)).to_be_visible()
        page.reload()
        expect(page.get_by_role("cell", name=re.compile("Pesquisou|Usou o cache|Duplicada"))).to_be_visible()
        tela(page, telas, "43_automacao_demo.png")
        passo("agendador em demo: roda sobre dados fictícios e registra o histórico, sem pedir aprovação")

        page.goto(f"{WEB}/lab?canal={CANAL}")
        page.get_by_label("Assunto do vídeo").fill("samurais história")
        page.get_by_role("button", name="Criar projeto").click()
        page.wait_for_url(re.compile(r"projeto=lab_"))
        expect(page.get_by_text("A história dos samurais", exact=True)).to_be_visible()
        expect(page.get_by_text("O que realmente sabemos sobre os samurais?", exact=True)).to_be_visible()
        expect(page.get_by_text("O lado menos conhecido dos samurais", exact=True)).to_be_visible()
        for rotulo in ("Direto.", "Pergunta.", "Recorte."):
            expect(page.get_by_text(rotulo, exact=True)).to_be_visible()
        expect(page.get_by_text("sem medição por trás", exact=False)).to_be_visible()
        assert page.get_by_text("Samurais história", exact=True).count() == 0
        tela(page, telas, "44_titulos.png")
        passo("títulos: o defeito sumiu; três ângulos naturais, com justificativa e sem promessa")

        page.goto(f"{WEB}/ideias?canal={CANAL}")
        page.get_by_role("button", name="Gerar ideias").click()
        expect(page.get_by_text("Direto.", exact=False).first).to_be_visible()
        conteudo = page.locator("main").inner_text()
        for ruim in ("Samurais história", "Vikings história", "pouco contada"):
            assert ruim not in conteudo, ruim
        tela(page, telas, "45_ideias.png")
        passo("ideias: assuntos naturais e justificativa em cada título")

        page.goto(f"{WEB}/coach?canal={CANAL}")
        expect(page.get_by_text("Por regras, sem IA").first).to_be_visible()
        page.get_by_label("Sua pergunta").fill("Quais vídeos encontrei na pesquisa?")
        page.get_by_role("button", name="Perguntar").click()
        page.wait_for_url(re.compile(r"conversa=cnv_"))
        expect(page.get_by_text("Regras, sem IA", exact=True).first).to_be_visible()
        expect(page.get_by_text("Não é análise de IA", exact=False).first).to_be_visible()
        expect(page.get_by_role("heading", name="Dados consultados")).to_be_visible()
        expect(page.get_by_text("Por quê:", exact=False).first).to_be_visible()
        expect(page.get_by_text("Fonte:", exact=False).first).to_be_visible()
        tela(page, telas, "46_coach_regras.png")
        passo("coach: diz que é por regras, com justificativas, fontes e dados consultados")

        page.goto(f"{WEB}/privacidade")
        expect(page.get_by_role("link", name="Termos de Serviço do YouTube")).to_have_attribute("href", "https://www.youtube.com/t/terms")
        expect(page.get_by_role("link", name="Política de Privacidade do Google")).to_be_visible()
        passo("dados e privacidade: links exigidos pela política")
        context.close()
        rotas_moveis(browser, ["/sistema", "/descobrir", "/descobrir?aba=historico", f"/descobrir?aba=salvos&canal={CANAL}", "/automacao", "/privacidade", f"/coach?canal={CANAL}", f"/ideias?canal={CANAL}"])


# --- Modo real sem chave --------------------------------------------------------------------------

def sem_chave(browser, dados: Path, telas: Path) -> None:
    with App(dados, "live"):
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = abrir(context)
        page.goto(f"{WEB}/descobrir")
        expect(page.get_by_text("Sem chave da API do YouTube")).to_be_visible()
        page.get_by_label("Nicho e subnicho").select_option("historia/antiga")
        page.get_by_role("button", name="Descobrir", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Sistema e cotas")).to_be_visible()
        passo("modo real sem chave: a pesquisa explica o que falta, sem inventar resultado")

        page.goto(f"{WEB}/automacao")
        expect(page.get_by_text("Desligado: sem chave")).to_be_visible()
        assert page.get_by_role("button", name="Aprovar limite e ligar").count() == 0
        assert page.get_by_role("button", name=re.compile("Rodar as vencidas")).count() == 0
        tela(page, telas, "47_automacao_sem_chave.png")
        passo("modo real sem chave: agendador desligado e sem botão de aprovar")
        context.close()


# --- API simulada ---------------------------------------------------------------------------------

def preparar_canal(dados: Path) -> str:
    from app.config import Settings
    from app.studio import store

    dados.mkdir(parents=True, exist_ok=True)
    studio = store.open_studio(Settings(mode="live", data_dir=dados, api_token="t"))
    channel = store.create_channel(studio, {"name": "Canal Real de Teste", "language": "pt", "keywords": ["roma", "história"], "avoid": ["política"]})
    studio.close()
    return channel["id"]


def descobrir(page: Page, canal: str, alvo: str = "recent_videos", assunto: str = "roma", formato: str = "") -> None:
    page.goto(f"{WEB}/descobrir")
    page.get_by_label("Nicho e subnicho").select_option("historia/antiga")
    page.get_by_label("Assunto, para afinar o recorte").fill(assunto)
    page.get_by_label("O que procurar").select_option(alvo)
    page.get_by_label("País (sigla)").fill("BR")
    page.get_by_label("Formato do vídeo").select_option(formato)
    page.get_by_label("Para qual canal").select_option(canal)
    page.get_by_role("button", name="Descobrir", exact=True).click()


def simulado(browser, dados: Path, telas: Path) -> None:
    canal = preparar_canal(dados)
    api = ApiSimulada()
    fake = api.fake
    app = App(dados, "live")
    app.env.update({"YOUTUBE_API_KEY": FAKE_KEY, "YTI_YOUTUBE_BASE_URL": f"http://127.0.0.1:{FAKE_PORT}/youtube/v3"})
    try:
        with app:
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            page = abrir(context)

            page.goto(f"{WEB}/sistema")
            expect(page.get_by_text("nada aqui vem do YouTube", exact=False)).to_be_visible()
            assert page.get_by_text("dados reais do YouTube", exact=False).count() == 0, "simulado apresentado como real"
            page.get_by_role("button", name="Testar conexão").click()
            expect(page.get_by_text("Isto não valida o YouTube", exact=False)).to_be_visible()
            expect(page.get_by_text("Nenhuma consulta com dados reais")).to_be_visible()
            assert page.get_by_text("Consulta real confirmada").count() == 0
            tela(page, telas, "48_sistema_simulado.png")
            passo("teste de conexão simulado: nunca conta como validação real")

            page.get_by_role("button", name="Testar com uma busca").click()
            expect(page.get_by_text("search.list", exact=False).first).to_be_visible()
            passo("teste com busca: mostra cada etapa e o formato recebido")

            descobrir(page, canal)
            page.wait_for_url(re.compile(r"/descobrir/run_"))
            run = page.url.rsplit("/", 1)[-1]
            expect(page.get_by_text("API simulada de teste").first).to_be_visible()
            assert page.locator("main").get_by_text("YouTube Data API v3").count() == 0
            expect(page.get_by_text("chamadas novas", exact=False)).to_be_visible()
            expect(page.get_by_text("Dados buscados em", exact=False)).to_be_visible()
            expect(page.get_by_text("Só dados crus")).to_be_visible()
            expect(page.get_by_text("VPH, outliers, índices e rankings seguem bloqueados", exact=False)).to_be_visible()
            links = page.get_by_role("link", name="Abrir no YouTube")
            assert links.count() == 12 and "youtube.com/watch?v=" in links.first.get_attribute("href")
            expect(page.get_by_text("Roma antiga parte 0")).to_be_visible()
            expect(page.get_by_text("Canal Falso").first).to_be_visible()
            expect(page.get_by_text("publicado em", exact=False).first).to_be_visible()
            expect(page.get_by_text("50 mil", exact=False).or_(page.get_by_text("50.000", exact=False)).first).to_be_visible()
            expect(page.get_by_text("cerca de", exact=False).first).to_be_visible()
            expect(page.get_by_text("Longos: confiável", exact=False).or_(page.get_by_text("Shorts: estimado", exact=False)).first).to_be_visible()
            sem_score(page, "descoberta")
            pedido = next(call for call in fake.calls if call.url.path.endswith("/search") and "roma" in call.url.params.get("q", ""))
            assert pedido.url.params["regionCode"] == "BR" and pedido.url.params["relevanceLanguage"] == "pt" and pedido.url.params["order"] == "date"
            tela(page, telas, "49_descoberta_simulada.png")
            passo("descoberta no modo real: link, título, canal, data e números públicos, sem score", resultados=links.count())

            antes = sum(1 for call in fake.calls if call.url.path.endswith("/search"))
            descobrir(page, canal)
            page.wait_for_url(lambda url: "/descobrir/run_" in url and run not in url)
            expect(page.get_by_text("do cache", exact=False)).to_be_visible()
            assert sum(1 for call in fake.calls if call.url.path.endswith("/search")) == antes
            passo("repetir a mesma descoberta usa o cache e não gasta busca")

            descobrir(page, canal, formato="short")
            page.wait_for_url(re.compile(r"/descobrir/run_"))
            expect(page.get_by_text("Shorts: estimado", exact=False).first).to_be_visible()
            assert page.get_by_text("Longos: confiável", exact=False).count() == 0
            expect(page.get_by_text("A API não tem filtro de Shorts", exact=False)).to_be_visible()
            passo("filtro de Shorts: aplicado depois da API, com classificação e aviso")

            page.get_by_role("button", name="Salvar vídeo").first.click()
            expect(page.get_by_text("Salvo.").first).to_be_visible()
            descobrir(page, canal, alvo="emerging_channels", assunto="vikings")
            page.wait_for_url(re.compile(r"/descobrir/run_"))
            expect(page.get_by_text("Canal Falso").first).to_be_visible()
            expect(page.get_by_text("inscritos", exact=False).first).to_be_visible()
            page.get_by_role("button", name="Salvar canal").first.click()
            expect(page.get_by_text("Salvo.").first).to_be_visible()
            sem_score(page, "canais pequenos")
            tela(page, telas, "50_canais_pequenos.png")
            page.goto(f"{WEB}/descobrir?aba=salvos&canal={canal}")
            expect(page.get_by_text("Roma antiga parte", exact=False).first).to_be_visible()
            expect(page.locator("li").filter(has_text="Canal Falso").get_by_role("link", name="Abrir no YouTube")).to_have_attribute("href", re.compile(r"youtube\.com/channel/"))
            passo("canais pequenos e itens salvos associados ao canal real")

            page.goto(f"{WEB}/pesquisa")
            page.get_by_label("Palavra, tema ou nicho").fill("cartago antiga")
            page.get_by_label("Associar ao canal").select_option(canal)
            page.get_by_role("button", name="Pesquisar", exact=True).click()
            page.wait_for_url(re.compile(r"/pesquisa/run_"))
            run_central = page.url.rsplit("/", 1)[-1]
            expect(page.get_by_text("Abrir no YouTube").first).to_be_visible()
            page.get_by_label("Nome").fill("Cartago para o canal")
            page.get_by_role("button", name="Salvar pesquisa").click()
            expect(page.get_by_text("Salva: Cartago para o canal")).to_be_visible()
            sem_score(page, "central")
            passo("central de pesquisa: busca pela API e salvamento", run=run_central)

            page.goto(f"{WEB}/palavras?canal={canal}")
            page.get_by_label(re.compile("termo", re.I)).first.fill("roma antiga")
            page.get_by_role("button", name=re.compile("Analisar")).first.click()
            page.wait_for_url(re.compile(r"termo="))
            expect(page.get_by_text("Bloqueado").first).to_be_visible()
            expect(page.get_by_text("Indisponível").first).to_be_visible()
            sem_score(page, "palavras")
            passo("palavras-chave: amostra real, índice bloqueado e volume indisponível")

            page.goto(f"{WEB}/explorer?canal={canal}&f=long&ordem=idr&acima=1")
            expect(page.get_by_text("A ordenação por IDR e VPH está bloqueada", exact=False)).to_be_visible()
            expect(page.get_by_text("Roma antiga parte", exact=False).first).to_be_visible()
            sem_score(page, "explorer")
            tela(page, telas, "51_explorer_autorizado.png")
            passo("outlier explorer: só os indicadores autorizados")

            page.goto(f"{WEB}/canais/{canal}/concorrentes")
            page.get_by_label(re.compile("Link|@nome|referência", re.I)).first.fill("@falso")
            page.get_by_role("button", name=re.compile("Adicionar")).first.click()
            expect(page.get_by_role("link", name="Canal Falso")).to_be_visible()
            expect(page.get_by_text("Este cálculo está bloqueado")).to_be_visible()
            sem_score(page, "concorrentes")
            passo("monitoramento de concorrentes: adiciona por @nome, sem comparações")

            page.goto(f"{WEB}/automacao")
            expect(page.get_by_text("Desligado: falta sua aprovação")).to_be_visible()
            assert page.get_by_role("button", name=re.compile("Rodar as vencidas")).count() == 0
            antes = len(fake.calls)
            page.locator("select[name=channel_id]").select_option(canal)
            page.get_by_label("Palavra ou tema").fill("egito antigo")
            page.get_by_label("Periodicidade").last.select_option("168")
            page.get_by_role("button", name="Agendar").click()
            # Pelo papel: o texto solto também casaria com "Nenhuma pesquisa agendada.".
            expect(page.get_by_role("status").filter(has_text="Agendada.")).to_be_visible()
            page.reload()
            expect(page.get_by_text("egito antigo").first).to_be_visible()
            assert len(fake.calls) == antes, "agendar não pode chamar a API"
            tela(page, telas, "52_automacao_aguardando.png")
            passo("agendador real: desligado até aprovar; agendar não chama a API")

            page.get_by_label("Buscas automáticas por dia, no máximo").fill("2")
            page.get_by_role("button", name="Aprovar limite e ligar").click()
            expect(page.get_by_text("Ligado", exact=True)).to_be_visible()
            page.get_by_role("button", name=re.compile("Rodar as vencidas")).click()
            expect(page.get_by_text("Rodada concluída.", exact=False)).to_be_visible()
            page.reload()
            expect(page.get_by_role("cell", name="Pesquisou")).to_be_visible()
            assert any(call.url.path.endswith("/search") and "egito" in call.url.params.get("q", "") for call in fake.calls)
            tela(page, telas, "53_automacao_ligada.png")
            passo("agendador real: com os limites aprovados, roda e registra o histórico")

            page.goto(f"{WEB}/coach?canal={canal}")
            page.get_by_label("Sua pergunta").fill("Quais vídeos encontrei na pesquisa?")
            page.get_by_role("button", name="Perguntar").click()
            page.wait_for_url(re.compile(r"conversa=cnv_"))
            expect(page.get_by_text("Regras, sem IA", exact=True).first).to_be_visible()
            expect(page.get_by_text("views públicas medidas em", exact=False).first).to_be_visible()
            assert page.get_by_text("O modelo não explicou", exact=False).count() == 0
            assert page.locator("main").get_by_text(re.compile(r"\b1 resultados\b|\d{4}-\d{2}-\d{2}")).count() == 0
            expect(page.get_by_text("Por quê:", exact=False).first).to_be_visible()
            sem_score(page, "coach")
            tela(page, telas, "54_coach_dados.png")
            passo("coach: cita itens concretos da pesquisa, sem score")

            from tests.yt_mock import REAL_INVALID_KEY, error_response

            fake.fail_next = [httpx.Response(400, json=REAL_INVALID_KEY)]
            descobrir(page, canal, assunto="persas")
            expect(page.get_by_role("alert").filter(has_text="A chave foi recusada")).to_be_visible()
            assert FAKE_KEY not in page.content()
            passo("erro de chave, com o corpo real do Google: mensagem clara e chave nunca na tela")

            fake.fail_next = [httpx.ConnectError("sem rede")] * 4
            descobrir(page, canal, assunto="maias")
            # Quatro tentativas, com espera crescente entre elas: leva alguns segundos de propósito.
            expect(page.get_by_role("alert").filter(has_text="Sem conexão com o Google")).to_be_visible(timeout=40000)
            passo("falha de rede: mensagem clara, depois de novas tentativas")

            fake.fail_next = [error_response(403, "accessNotConfigured")]
            page.goto(f"{WEB}/sistema")
            page.get_by_role("button", name="Testar conexão").click()
            expect(page.get_by_text("A API não está ativada no projeto", exact=False)).to_be_visible()
            tela(page, telas, "55_sistema_erro.png")
            passo("teste de conexão: API desligada no projeto, com o que fazer")

            fake.fail_next = [error_response(403, "quotaExceeded")]
            descobrir(page, canal, assunto="astecas")
            expect(page.get_by_role("alert").filter(has_text="Cota do Google esgotada")).to_be_visible()
            antes = len(fake.calls)
            descobrir(page, canal, assunto="incas")
            expect(page.get_by_role("alert").filter(has_text="Nada será chamado")).to_be_visible()
            assert len(fake.calls) == antes, "depois da recusa de cota, nada pode ser chamado"
            passo("cota esgotada: para de chamar até a virada do dia de cota")

            context.close()
            rotas_moveis(browser, ["/sistema", "/descobrir", f"/descobrir?aba=salvos&canal={canal}", "/automacao", f"/descobrir/{run}", f"/coach?canal={canal}"])
            EVIDENCIA["chamadas_api_simulada"] = len(fake.calls)
            assert all(FAKE_KEY not in str(mensagem) for mensagem in ERROS)
    finally:
        api.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dados", required=True, type=Path)
    parser.add_argument("--saida", required=True, type=Path)
    parser.add_argument("--cenarios", default="demo,semchave,simulado")
    args = parser.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    telas = args.saida.parent / "telas"
    telas.mkdir(exist_ok=True)
    EVIDENCIA["aviso"] = "Validação com API simulada e dados fictícios. Não prova que a API do Google responde assim."
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel="chrome", headless=True)
        try:
            if "demo" in args.cenarios:
                demo(browser, args.dados / "demo", telas)
            if "semchave" in args.cenarios:
                sem_chave(browser, args.dados / "semchave", telas)
            if "simulado" in args.cenarios:
                simulado(browser, args.dados / "simulado", telas)
        finally:
            browser.close()
    EVIDENCIA["erros_de_pagina"] = ERROS
    (args.saida / "dados_reais_navegador.json").write_text(json.dumps(EVIDENCIA, ensure_ascii=False, indent=1), encoding="utf-8")
    if ERROS:
        raise SystemExit("Erros no navegador:\n" + "\n".join(ERROS[:20]))
    print(f"APROVADO: {len(EVIDENCIA['passos'])} passos")


if __name__ == "__main__":
    main()
