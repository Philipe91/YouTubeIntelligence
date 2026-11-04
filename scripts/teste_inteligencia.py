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


def demo_explorer(page: Page, saida: Path) -> None:
    page.goto(f"{WEB}/explorer?canal={CANAL}&f=long&ordem=idr")
    expect(page.get_by_text("Índice próprio ativo")).to_be_visible()
    primeiro = page.get_by_role("button", name="Guardar para estudo")
    total = primeiro.count()
    assert total >= 2, "esperava vídeos para guardar"
    primeiro.first.click()
    expect(page.get_by_text("Na lista de estudo").first).to_be_visible()
    page.get_by_role("button", name="Guardar para estudo").first.click()
    expect(page.get_by_text("Na lista de estudo")).to_have_count(2)
    tela(page, saida, "24_explorer.png")
    passo("explorer: guardar vídeos para estudo")

    page.get_by_label("Assunto no título").fill("xyzzy inexistente")
    page.get_by_role("button", name="Aplicar").click()
    expect(page.get_by_text("Nenhum vídeo encontrado.")).to_be_visible()
    page.goto(f"{WEB}/explorer?canal={CANAL}&f=short&acima=1&ordem=idr")
    assert "Shorts" in page.locator("main").inner_text() or page.get_by_text("Nenhum vídeo encontrado.").count() == 1
    passo("explorer: filtros e resultado vazio")

    page.goto(f"{WEB}/explorer?aba=estudo&canal={OUTRO}")
    expect(page.get_by_text("A lista de estudo deste canal está vazia.")).to_be_visible()
    page.goto(f"{WEB}/explorer?aba=estudo&canal={CANAL}")
    caixas = page.get_by_role("checkbox")
    caixas.nth(0).check()
    page.get_by_role("button", name="Comparar selecionados").click()
    expect(page.get_by_text("Não dá para comparar esta seleção.")).to_be_visible()
    page.goto(f"{WEB}/explorer?aba=estudo&canal={CANAL}")
    page.get_by_label("Como este vídeo conta a história").first.fill("Abre com uma cena de cotidiano")
    page.get_by_role("button", name="Salvar nota").first.click()
    expect(page.get_by_text("Nota salva.")).to_be_visible()
    page.goto(f"{WEB}/explorer?aba=estudo&canal={CANAL}")
    caixas = page.get_by_role("checkbox")
    caixas.nth(0).check()
    caixas.nth(1).check()
    page.get_by_role("button", name="Comparar selecionados").click()
    page.wait_for_url(re.compile(r"/explorer/comparar"))
    expect(page.get_by_text("Abordagem, por regra").first).to_be_visible()
    expect(page.get_by_text("Abre com uma cena de cotidiano")).to_be_visible()
    tela(page, saida, "25_explorer_comparar.png")
    passo("explorer: isolamento, nota e comparação de títulos")


def demo_competitors(page: Page, saida: Path) -> None:
    base = f"{WEB}/canais/{CANAL}/concorrentes"
    page.goto(base)
    expect(page.get_by_role("link", name="Atlas Animado (fictício)")).to_be_visible()
    expect(page.get_by_role("columnheader", name="Por semana")).to_be_visible()
    page.get_by_label("Canal fictício").select_option(label="Era em Traços (fictício)")
    page.get_by_label("Por que acompanhar").fill("Mesmo público em Portugal")
    page.get_by_role("button", name="Adicionar", exact=True).click()
    expect(page.get_by_role("link", name="Era em Traços (fictício)")).to_be_visible()
    tela(page, saida, "26_concorrentes.png")
    passo("concorrentes: cadastro e comparação editorial")

    page.get_by_role("link", name="Era em Traços (fictício)").click()
    expect(page.get_by_role("heading", name="Calendário de publicação")).to_be_visible()
    expect(page.get_by_role("heading", name="Assuntos recorrentes")).to_be_visible()
    page.get_by_role("button", name="Salvar referência").first.click()
    expect(page.get_by_text("Referência salva").first).to_be_visible()
    tela(page, saida, "27_concorrente_detalhe.png")
    passo("concorrentes: vídeos, calendário, padrões e referência salva")

    page.goto(base)
    page.get_by_label("Oportunidade", exact=True).fill("A rota comercial que ninguém explica")
    page.get_by_label("Por quê", exact=True).fill("Nenhum dos canais aborda o tema")
    page.get_by_role("button", name="Registrar", exact=True).click()
    expect(page.get_by_text("A rota comercial que ninguém explica")).to_be_visible()
    page.get_by_role("button", name="Virar ideia").click()
    expect(page.get_by_text("Virou ideia")).to_be_visible()
    passo("concorrentes: oportunidade vira ideia")

    with page.expect_download() as baixado:
        page.get_by_role("link", name="Baixar relatório com fontes").click()
    texto = Path(baixado.value.path()).read_text(encoding="utf-8")
    assert "Dados fictícios" in texto and "Atlas Animado" in texto and "Era em Traços" in texto
    passo("concorrentes: relatório baixado", bytes=len(texto))

    page.goto(f"{WEB}/canais/{OUTRO}/concorrentes")
    assert page.get_by_role("link", name="Era em Traços (fictício)").count() == 0
    assert page.get_by_text("A rota comercial que ninguém explica").count() == 0
    passo("concorrentes: isolamento entre canais")

    page.goto(f"{WEB}/videos/DEMO_V01l000")
    expect(page.get_by_role("button", name="Guardar para estudo")).to_be_visible()
    page.get_by_role("button", name="Guardar para estudo").click()
    expect(page.get_by_role("alert").filter(has_text="Escolha um canal")).to_be_visible()
    page.get_by_label("Lista de estudo do canal").select_option(OUTRO)
    page.get_by_role("button", name="Guardar para estudo").click()
    expect(page.get_by_text("Guardado na lista de estudo.")).to_be_visible()
    passo("página do vídeo: guardar para estudo")


def demo_ideas_coach(page: Page, saida: Path) -> None:
    page.goto(f"{WEB}/ideias?canal={OUTRO}")
    page.get_by_role("button", name="Gerar ideias").click()
    expect(page.get_by_text("Ideia para vídeo").first).to_be_visible()
    page.goto(f"{WEB}/ideias?canal={CANAL}")
    page.get_by_role("button", name="Gerar ideias").click()
    cartao = page.locator("article").first
    expect(cartao.get_by_text("Títulos")).to_be_visible()
    for campo in ("Justificativa", "Referências", "Conceito de thumbnail", "Hook inicial", "Formato", "Público", "Dificuldade estimada", "Confiança na evidência", "Recomendada em"):
        expect(cartao.get_by_text(campo, exact=True).first).to_be_visible()
    assert cartao.locator("ol li").count() == 3
    assert "previsão" not in page.locator("main").inner_text().lower().replace("não há previsão de views", "")
    tela(page, saida, "30_ideias.png")
    passo("ideias: todos os campos pedidos, sem previsão de views")

    assunto = cartao.locator("h2").inner_text()
    cartao.get_by_role("button", name="Favoritar").click()
    expect(page.locator("article").filter(has_text=assunto).get_by_text("Favorita", exact=True)).to_be_visible()
    alvo = page.locator("article").filter(has_text=assunto)
    alvo.get_by_label("Data no calendário").fill("2031-03-14")
    alvo.get_by_role("button", name="Pôr no calendário").click()
    expect(page.locator("article").filter(has_text=assunto)).to_have_count(0)
    calendario = page.request.get(f"http://127.0.0.1:{API_PORT}/api/studio/calendar", params={"start": "2031-03-01", "end": "2031-03-31", "channel_id": CANAL}).json()["entries"]
    assert len(calendario) == 1 and calendario[0]["recommendation_id"]
    passo("ideias: favoritar e pôr no calendário cria item real")

    page.goto(f"{WEB}/ideias?canal={CANAL}&filtro=salvas")
    expect(page.locator("article").filter(has_text=assunto).get_by_text("Calendário: 14/03/2031")).to_be_visible()
    page.goto(f"{WEB}/ideias?canal={CANAL}&filtro=novas")
    outra = page.locator("article").first
    assunto_outra = outra.locator("h2").inner_text()
    outra.get_by_role("button", name="Rejeitar").click()
    expect(page.locator("article").filter(has_text=assunto_outra)).to_have_count(0)
    page.goto(f"{WEB}/ideias?canal={CANAL}&filtro=rejeitadas")
    expect(page.locator("article").filter(has_text=assunto_outra)).to_be_visible()
    page.locator("article").filter(has_text=assunto_outra).get_by_role("button", name="Restaurar").click()
    expect(page.locator("article").filter(has_text=assunto_outra)).to_have_count(0)
    page.goto(f"{WEB}/ideias?canal={CANAL}&filtro=novas")
    page.locator("article").first.get_by_role("button", name="Salvar").click()
    passo("ideias: salvar, rejeitar e restaurar")

    page.goto(f"{WEB}/coach?canal={CANAL}")
    expect(page.get_by_text("Responde por regras, sem IA e sem custo.")).to_be_visible()
    page.get_by_role("button", name="Qual assunto devo produzir para este canal?").click()
    page.wait_for_url(re.compile(r"conversa=cnv_"))
    expect(page.get_by_role("heading", name="Observações").first).to_be_visible()
    expect(page.get_by_role("heading", name="Recomendações").first).to_be_visible()
    expect(page.get_by_role("heading", name="Fontes").first).to_be_visible()
    page.get_by_text("Ferramentas usadas").first.click()
    expect(page.get_by_text("ideias", exact=True).first).to_be_visible()
    expect(page.get_by_text("Sem custo de IA").first).to_be_visible()
    tela(page, saida, "31_coach.png")
    passo("coach: resposta separada, com fontes, ferramentas e custo")

    page.get_by_label("Sua pergunta").fill("Quais concorrentes merecem acompanhamento?")
    page.get_by_role("button", name="Perguntar").click()
    expect(page.get_by_text("Atlas Animado (fictício) tem", exact=False).first).to_be_visible()
    page.goto(f"{WEB}/coach?canal={OUTRO}")
    expect(page.get_by_text("Nenhuma conversa neste canal.")).to_be_visible()
    page.goto(f"{WEB}/coach?canal={CANAL}")
    expect(page.get_by_role("link", name="Qual assunto devo produzir", exact=False)).to_be_visible()
    passo("coach: histórico por canal")

    page.get_by_role("link", name="Qual assunto devo produzir", exact=False).click()
    page.get_by_label("Título da conversa").fill("Próximos assuntos")
    page.get_by_role("button", name="Renomear").click()
    expect(page.get_by_role("link", name="Próximos assuntos")).to_be_visible()
    page.get_by_role("button", name="Apagar conversa").click()
    page.wait_for_url(re.compile(r"/coach\?canal="))
    expect(page.get_by_role("link", name="Próximos assuntos")).to_have_count(0)
    passo("coach: renomear e apagar conversa")


def imagens_teste(pasta: Path) -> tuple[Path, Path, Path]:
    from PIL import Image, ImageDraw

    pasta.mkdir(parents=True, exist_ok=True)
    boa = Image.new("RGB", (1280, 720), (15, 20, 40))
    ImageDraw.Draw(boa).rectangle((880, 240, 1180, 480), fill=(255, 210, 0))
    boa.save(pasta / "boa.png")
    Image.new("RGB", (1280, 720), (128, 128, 128)).save(pasta / "lisa.jpg")
    (pasta / "falsa.png").write_text("isto não é uma imagem", encoding="utf-8")
    return pasta / "boa.png", pasta / "lisa.jpg", pasta / "falsa.png"


def demo_lab(page: Page, saida: Path, dados: Path) -> None:
    boa, lisa, falsa = imagens_teste(dados.parent / "imagens_teste")
    page.goto(f"{WEB}/lab?canal={CANAL}")
    page.get_by_label("Assunto do vídeo").fill("Queda de Cartago")
    page.get_by_role("button", name="Criar projeto").click()
    page.wait_for_url(re.compile(r"projeto=lab_"))
    expect(page.get_by_text("não prevê CTR", exact=False).first).to_be_visible()
    assert page.get_by_text("Previsão de CTR").count() == 0
    passo("lab: projeto criado, nota sem promessa de CTR")

    page.get_by_role("button", name="Guardar título").first.click()
    expect(page.get_by_role("heading", name="Variações salvas (1)")).to_be_visible()
    page.get_by_label("Seu título").fill("A QUEDA DE CARTAGO!!! você não vai acreditar")
    page.get_by_label("Thumbnail (opcional)").set_input_files(str(falsa))
    page.get_by_role("button", name="Salvar variação").click()
    expect(page.get_by_role("alert").filter(has_text="a imagem foi recusada")).to_be_visible()
    expect(page.get_by_role("heading", name="Variações salvas (2)")).to_be_visible()
    expect(page.get_by_text("Expressão exagerada", exact=False).first).to_be_visible()
    passo("lab: títulos avaliados; arquivo falso recusado com erro claro")

    page.get_by_label("Seu título").fill("O dia em que Cartago caiu")
    page.get_by_label("Thumbnail (opcional)").set_input_files(str(boa))
    page.get_by_role("button", name="Salvar variação").click()
    expect(page.get_by_role("heading", name="Variações salvas (3)")).to_be_visible()
    imagem = page.locator("img[src*='/lab/imagem/']").first
    expect(imagem).to_be_visible()
    largura = imagem.evaluate("element => element.naturalWidth")
    assert largura > 0, "a imagem salva não carregou"
    expect(page.get_by_text("Hierarquia e composição").first).to_be_visible()
    expect(page.get_by_text("Não lê texto na imagem.").first).to_be_visible()
    tela(page, saida, "34_lab.png")
    passo("lab: imagem real analisada e exibida na prévia", largura=largura)

    primeira_sem_imagem = page.get_by_label("Trocar ou enviar thumbnail").first
    primeira_sem_imagem.set_input_files(str(lisa))
    page.get_by_role("button", name="Enviar imagem").first.click()
    expect(page.locator("img[src*='/lab/imagem/']")).to_have_count(2)
    page.get_by_role("button", name="Favoritar").first.click()
    expect(page.get_by_text("Favorita", exact=True).first).to_be_visible()
    page.get_by_label("Sua nota").first.fill("Melhor para o público atual")
    page.get_by_role("button", name="Salvar nota").first.click()
    expect(page.get_by_text("Nota salva.")).to_be_visible()
    passo("lab: segunda imagem, favorita e nota")

    url = page.url
    page.goto(url.replace(CANAL, OUTRO))
    expect(page.get_by_text("Projeto não encontrado neste canal.")).to_be_visible()
    page.goto(url)
    antes = page.get_by_role("button", name="Apagar variação").count()
    page.get_by_role("button", name="Apagar variação").last.click()
    expect(page.get_by_role("button", name="Apagar variação")).to_have_count(antes - 1)
    passo("lab: isolamento entre canais e apagar variação")


def cenario_demo(browser, dados: Path, saida: Path) -> None:
    with App(dados, "demo"):
        context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
        page = abrir(context)
        run = demo_research(page, saida)
        demo_keywords(page, saida)
        demo_explorer(page, saida)
        demo_competitors(page, saida)
        demo_ideas_coach(page, saida)
        demo_lab(page, saida, dados)
        competidor = page.request.get(f"http://127.0.0.1:{API_PORT}/api/intel/channels/{CANAL}/competitors").json()["items"][0]["id"]
        context.close()
        rotas_moveis(browser, ["/", "/pesquisa", f"/pesquisa/{run}", "/pesquisa?aba=historico", "/palavras", "/palavras?termo=roma", f"/palavras?aba=para-voce&canal={CANAL}",
                               f"/explorer?canal={CANAL}", f"/explorer?aba=estudo&canal={CANAL}", f"/canais/{CANAL}/concorrentes", f"/canais/{CANAL}/concorrentes/{competidor}",
                               f"/ideias?canal={CANAL}", f"/coach?canal={CANAL}", f"/lab?canal={CANAL}"])


# --- Cenário restrito -----------------------------------------------------------------------------

def preparar_restrito(dados: Path) -> tuple[str, str, str]:
    """Grava no banco real os resultados de um YouTube falso. O aplicativo sobe sem chave depois disso."""
    from tests.yt_mock import FakeYouTube

    from app.config import Settings
    from app.connectors.youtube_data import YouTubeDataClient
    from app.db import connect, migrate
    from app.intel import competitors, explorer, keywords, research
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
    item = competitors.add(conn, studio, settings, channel["id"], "@falso", "Referência de teste", "Mesmo nicho", now, build)
    for video in ("vid00", "vid01"):
        explorer.add_study(conn, studio, settings, channel["id"], video, now)
    studio.close()
    conn.close()
    return run["id"], channel["id"], item["id"]


def cenario_restrito(browser, dados: Path, saida: Path) -> None:
    run, canal, item = preparar_restrito(dados)
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

        page.goto(f"{WEB}/explorer?canal={canal}&f=long&ordem=idr&acima=1")
        expect(page.get_by_text("Só dados crus").first).to_be_visible()
        expect(page.get_by_text("A ordenação por IDR e VPH está bloqueada", exact=False)).to_be_visible()
        expect(page.get_by_text("Roma antiga parte", exact=False).first).to_be_visible()
        assert page.get_by_role("option", name="Índice próprio (IDR)").count() == 0
        assert page.get_by_text(re.compile(r"\d+,\dx")).count() == 0
        tela(page, saida, "28_restrito_explorer.png")
        page.goto(f"{WEB}/explorer/comparar?canal={canal}&ids=vid00&ids=vid01")
        expect(page.get_by_text("Leitura dos títulos bloqueada")).to_be_visible()
        assert page.get_by_text("Abordagem, por regra").count() == 0
        passo("restrito: explorer útil, sem score nem leitura de títulos")

        page.goto(f"{WEB}/canais/{canal}/concorrentes")
        expect(page.get_by_role("link", name="Canal Falso")).to_be_visible()
        expect(page.get_by_text("Este cálculo está bloqueado")).to_be_visible()
        assert page.get_by_role("columnheader", name="Por semana").count() == 0
        page.get_by_role("link", name="Canal Falso").click()
        expect(page.get_by_role("heading", name="Calendário de publicação")).to_be_visible()
        expect(page.get_by_text("Este cálculo está bloqueado")).to_be_visible()
        assert page.get_by_role("heading", name="Assuntos recorrentes").count() == 0
        page.get_by_role("button", name="Atualizar vídeos").click()
        expect(page.get_by_role("alert").filter(has_text="YOUTUBE_API_KEY")).to_be_visible()
        tela(page, saida, "29_restrito_concorrente.png")
        passo("restrito: concorrente com dados crus e sem padrões; falha de chave explicada")

        page.goto(f"{WEB}/ideias?canal={canal}")
        page.get_by_role("button", name="Gerar ideias").click()
        expect(page.get_by_text("Editorial, sem métricas").first).to_be_visible()
        assert page.get_by_text("Métrica própria").count() == 0
        tela(page, saida, "32_restrito_ideias.png")
        passo("restrito: ideias só editoriais")

        page.goto(f"{WEB}/coach?canal={canal}")
        page.get_by_role("button", name="Que oportunidades existem para canais em português e inglês?").click()
        page.wait_for_url(re.compile(r"conversa=cnv_"))
        expect(page.get_by_text("Bloqueado: a política da API", exact=False).first).to_be_visible()
        tela(page, saida, "33_restrito_coach.png")
        passo("restrito: coach responde e explica o que está bloqueado")
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
