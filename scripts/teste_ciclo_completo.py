"""Ciclo completo com dados fictícios: painel real, servidor MCP real, falhas e reinícios de verdade.

Uso, a partir da raiz do projeto, com o frontend já compilado:
    uv run --directory backend --with playwright python ../scripts/teste_ciclo_completo.py --dados <pasta vazia> --saida ../docs/evidencias

Sobe o aplicativo em portas próprias, usa só a pasta --dados e encerra tudo no fim.
Falhou um passo, o script para com erro: nada é dado como concluído sem verificação.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.sync_api import expect as _expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
API_PORT, WEB_PORT = 8011, 3011
API, WEB = f"http://127.0.0.1:{API_PORT}", f"http://127.0.0.1:{WEB_PORT}"
CANAL = "chn_demo_imperios"
OUTRO_CANAL = "chn_demo_rotas"
CANAL_BOTOES = "chn_demo_cronicas"
LEASE = 30
EVIDENCIA: dict = {"passos": []}


def passo(nome: str, /, **dados) -> None:
    EVIDENCIA["passos"].append({"passo": nome, **dados})
    print(f"ok  {nome}" + (f"  {json.dumps(dados, ensure_ascii=False)}" if dados else ""), flush=True)


def expect(locator):
    return _expect(locator.first)


def ps(script: str, dados: Path | None = None) -> str:
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
    if dados:
        env.update(YTI_DATA_DIR=str(dados), YTI_MODE="demo")
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], capture_output=True, text=True, env=env, timeout=120)
    if done.returncode:
        raise RuntimeError(done.stderr or done.stdout)
    return done.stdout


def ligar(dados: Path) -> None:
    ps(f"& '{ROOT / 'scripts' / 'iniciar.ps1'}' -ApiPort {API_PORT} -WebPort {WEB_PORT}", dados)
    for _ in range(90):
        try:
            urllib.request.urlopen(f"{WEB}/canais", timeout=10)
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("O aplicativo não respondeu.")


def desligar(dados: Path) -> None:
    ps(f"& '{ROOT / 'scripts' / 'parar.ps1'}'", dados)
    for _ in range(20):
        try:
            urllib.request.urlopen(f"{API}/api/filters", timeout=1)
            time.sleep(0.5)
        except Exception:
            return
    raise RuntimeError("A API continuou respondendo depois de desligar.")


class AgenteMcp:
    """Fala com o servidor MCP real, em subprocesso, como o Claude Code faria."""

    def __init__(self, dados: Path):
        env = {**os.environ, "YTI_DATA_DIR": str(dados), "YTI_MODE": "demo", "PYTHONPATH": str(BACKEND)}
        self.params = StdioServerParameters(command=sys.executable, args=["-m", "app.studio.mcp_server"], env=env, cwd=str(BACKEND))
        self.loop = asyncio.new_event_loop()
        self.pronto = threading.Event()
        self.sessao: ClientSession | None = None
        self.erro: BaseException | None = None
        self.thread = threading.Thread(target=self._rodar, daemon=True)
        self.thread.start()
        if not self.pronto.wait(60) or self.sessao is None:
            raise RuntimeError(f"Servidor MCP não iniciou: {self.erro}")

    def _rodar(self) -> None:
        try:
            self.loop.run_until_complete(self._principal())
        except BaseException as erro:  # noqa: BLE001 - encerrar à força derruba o cliente, e isso é esperado
            self.erro = erro
        finally:
            self.pronto.set()

    async def _principal(self) -> None:
        self.parar = asyncio.Event()
        async with stdio_client(self.params) as (leitura, escrita):
            async with ClientSession(leitura, escrita) as sessao:
                await sessao.initialize()
                self.sessao = sessao
                self.pronto.set()
                await self.parar.wait()

    def ferramentas(self) -> set[str]:
        resultado = asyncio.run_coroutine_threadsafe(self.sessao.list_tools(), self.loop).result(30)
        return {tool.name for tool in resultado.tools}

    def bruto(self, nome: str, **argumentos) -> dict:
        resultado = asyncio.run_coroutine_threadsafe(self.sessao.call_tool(nome, argumentos), self.loop).result(30)
        return json.loads(resultado.content[0].text)

    def ok(self, nome: str, **argumentos) -> dict:
        resposta = self.bruto(nome, **argumentos)
        assert resposta["ok"], (nome, resposta)
        return resposta["data"]

    def erro_de(self, nome: str, **argumentos) -> str:
        resposta = self.bruto(nome, **argumentos)
        assert not resposta["ok"], (nome, "deveria ter falhado", resposta)
        return resposta["error"]["code"]

    def fechar(self) -> None:
        self.loop.call_soon_threadsafe(self.parar.set)
        self.thread.join(20)

    def matar(self) -> int:
        """Mata o processo do servidor, sem aviso. Só os filhos deste script, nunca outra sessão do Claude."""
        saida = ps("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
        processos = json.loads(saida)
        arvore = {os.getpid()}
        for _ in range(4):
            arvore |= {p["ProcessId"] for p in processos if p["ParentProcessId"] in arvore}
        alvos = [p["ProcessId"] for p in processos if p["ProcessId"] in arvore and "mcp_server" in (p["CommandLine"] or "")]
        assert alvos, "processo do servidor MCP não encontrado"
        for pid in alvos:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        self.thread.join(10)
        return len(alvos)


def http_status(url: str, dados: Path | None = None) -> int:
    headers = {"X-YTI-Token": (dados / ".api_token").read_text(encoding="ascii").strip()} if dados else {}
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20).status
    except urllib.error.HTTPError as erro:
        return erro.code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dados", required=True, type=Path)
    parser.add_argument("--saida", required=True, type=Path)
    args = parser.parse_args()
    dados, saida = args.dados.resolve(), args.saida.resolve()
    assert not (dados / "studio.sqlite").exists(), "Use uma pasta de dados vazia."
    assert dados != (ROOT / "data").resolve(), "O teste não pode rodar na pasta de dados real."
    dados.mkdir(parents=True, exist_ok=True)
    telas = saida / "telas"
    telas.mkdir(parents=True, exist_ok=True)

    ligar(dados)
    try:
        with sync_playwright() as p:
            navegador = p.chromium.launch(channel="msedge", headless=True)
            pagina = navegador.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            problemas: list[str] = []
            pagina.on("pageerror", lambda erro: problemas.append(str(erro)))
            ciclo(pagina, dados, telas)
            botoes(pagina)
            responsividade(navegador, problemas)
            assert not problemas, problemas
            passo("Sem erros de JavaScript no navegador")
            navegador.close()
    finally:
        desligar(dados)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "ciclo_completo.json").write_text(json.dumps(EVIDENCIA, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nCICLO COMPLETO APROVADO", flush=True)
    return 0


def clicar(pagina, nome: str, escopo=None) -> None:
    (escopo or pagina).get_by_role("button", name=nome, exact=True).first.click()
    pagina.wait_for_timeout(200)
    _expect(pagina.locator("button:disabled")).to_have_count(0, timeout=20000)


def ciclo(pagina, dados: Path, telas: Path) -> None:
    url_canal = f"{WEB}/canais/{CANAL}"

    # 1. Selecionar o canal
    pagina.goto(f"{WEB}/canais", wait_until="networkidle")
    pagina.get_by_role("link", name="Imperios Olvidados (ficticio)").first.click()
    pagina.wait_for_url(f"**/canais/{CANAL}")
    passo("1. Canal selecionado no painel", canal=CANAL)

    # 2. Criar a recomendação
    assunto = "Puente de barcas de Jerjes"
    pagina.locator("summary", has_text="Criar outra recomendação").click()
    pagina.fill('input[name="subject"]', assunto)
    pagina.fill('textarea[name="justification"]', "Tema de teste, com dados fictícios.")
    pagina.select_option('select[name="editorial_priority"]', "alta")
    clicar(pagina, "Criar recomendação")
    expect(pagina.get_by_role("heading", name=assunto)).to_be_visible()
    passo("2. Recomendação criada", assunto=assunto)

    # 3. Três títulos
    clicar(pagina, "Gerar três títulos")
    _expect(pagina.locator('input[type="radio"][name="chosen"]')).to_have_count(4, timeout=15000)
    titulos = [valor for valor in pagina.locator('input[type="radio"][name="chosen"]').evaluate_all("els => els.map(e => e.value)") if valor != "__outro__"]
    assert len(titulos) == 3
    passo("3. Três títulos gerados", titulos=titulos)

    # 4. Escolher e aprovar o briefing
    escolhido = titulos[1]
    pagina.locator(f'input[type="radio"][value="{escolhido}"]').check()
    data_planejada = (date.today() + timedelta(days=3)).isoformat()
    pagina.fill('input[name="planned_on"]', data_planejada)
    clicar(pagina, "Aprovar briefing")
    expect(pagina.get_by_text("Briefing aprovado")).to_be_visible()
    pagina.screenshot(path=str(telas / "01_briefing_aprovado.png"), full_page=True)
    passo("4. Título escolhido e briefing aprovado", titulo=escolhido)

    # 5. Disponibilizar
    agente_sem_tarefa = AgenteMcp(dados)
    assert agente_sem_tarefa.ok("list_available_tasks", agent_id="agente-teste-A", channel_id=CANAL)["tasks"] == []
    clicar(pagina, "Disponibilizar ao Claude Code")
    expect(pagina.get_by_text("Disponível: aguardando um agente")).to_be_visible()
    agente = agente_sem_tarefa
    tarefas = agente.ok("list_available_tasks", agent_id="agente-teste-A", channel_id=CANAL)["tasks"]
    assert len(tarefas) == 1 and tarefas[0]["title"] == escolhido and tarefas[0]["simulated"] is True
    job_id = tarefas[0]["job_id"]
    plano = agente.ok("get_pipeline_plan", job_id=job_id)
    assert plano["real_execution_enabled"] is False and plano["ready_to_execute"] is True
    passo("5. Tarefa disponível pelo MCP", job_id=job_id, estado="NA FILA")

    # 6. Assumir, com tentativa duplicada
    assumida = agente.ok("claim_job", job_id=job_id, agent_id="agente-teste-A", idempotency_key="claim-A1", lease_seconds=LEASE)
    token_1 = assumida["lease_token"]
    assert assumida["briefing"]["chosen_title"] == escolhido and assumida["briefing"]["fictional"] is True
    repetida = agente.ok("claim_job", job_id=job_id, agent_id="agente-teste-A", idempotency_key="claim-A1", lease_seconds=LEASE)
    assert repetida["replayed"] is True and repetida["lease_token"] == token_1
    codigo_duplicada = agente.erro_de("claim_job", job_id=job_id, agent_id="agente-teste-B", idempotency_key="claim-B1")
    assert codigo_duplicada == "job_not_claimable"
    assert agente.ok("list_available_tasks", agent_id="agente-teste-A", channel_id=CANAL)["tasks"] == []
    expect(pagina.get_by_text("agente-teste-A")).to_be_visible(timeout=12000)
    passo("6. Agente assumiu; execução duplicada recusada", repeticao_mesma_chave="devolveu a mesma resposta", segundo_agente=codigo_duplicada, painel="atualizou sozinho")

    # 7. Falha informada, alerta e retomada
    agente.ok("update_progress", job_id=job_id, lease_token=token_1, progress=20, step="Roteiro", idempotency_key="p-20", lease_seconds=LEASE)
    expect(pagina.get_by_text("20%")).to_be_visible(timeout=12000)
    agente.ok("report_failure", job_id=job_id, lease_token=token_1, error="Falha de teste na narração", retryable=True, idempotency_key="falha-1")
    alertas = pagina.get_by_role("region", name="Alertas")
    expect(alertas.get_by_text("Falha de teste na narração")).to_be_visible(timeout=12000)
    pagina.screenshot(path=str(telas / "02_alerta_de_falha.png"), full_page=True)
    clicar(pagina, "Marcar como visto")
    _expect(alertas.get_by_text("Falha de teste na narração")).to_have_count(0, timeout=12000)
    assert agente.erro_de("update_progress", job_id=job_id, lease_token=token_1, progress=30, step="x", idempotency_key="p-30") == "job_not_running"
    token_2 = agente.ok("claim_job", job_id=job_id, agent_id="agente-teste-A", idempotency_key="claim-A2", lease_seconds=LEASE)["lease_token"]
    assert token_2 != token_1
    agente.ok("update_progress", job_id=job_id, lease_token=token_2, progress=40, step="Narração", idempotency_key="p-40", lease_seconds=LEASE)
    expect(pagina.get_by_text("40%")).to_be_visible(timeout=12000)
    passo("7. Falha registrada, alerta visto no painel, tarefa retomada", tentativa=2)

    # 8. Queda geral: mata o servidor MCP e desliga o aplicativo no meio da tarefa
    mortos = agente.matar()
    desligar(dados)
    banco = sqlite3.connect(dados / "studio.sqlite")
    estado = banco.execute("SELECT state, progress, attempts FROM production_jobs WHERE id = ?", (job_id,)).fetchone()
    banco.close()
    assert estado == ("running", 40, 2), estado
    ligar(dados)
    pagina.goto(url_canal, wait_until="networkidle")
    expect(pagina.get_by_text("40%")).to_be_visible()
    passo("8. Queda no meio da tarefa: estado preservado", processos_mcp_mortos=mortos, estado_no_banco=estado)

    # 9. Prazo vence, tarefa volta à fila, outro agente assume e o antigo é barrado
    time.sleep(LEASE + 2)
    agente = AgenteMcp(dados)
    tarefas = agente.ok("list_available_tasks", agent_id="agente-teste-B", channel_id=CANAL)["tasks"]
    assert [t["job_id"] for t in tarefas] == [job_id] and tarefas[0]["attempts"] == 2
    pagina.goto(url_canal, wait_until="networkidle")
    expect(pagina.get_by_role("region", name="Alertas").get_by_text("Prazo vencido")).to_be_visible()
    token_3 = agente.ok("claim_job", job_id=job_id, agent_id="agente-teste-B", idempotency_key="claim-B2")["lease_token"]
    bloqueado = agente.erro_de("update_progress", job_id=job_id, lease_token=token_2, progress=90, step="Agente antigo", idempotency_key="p-antigo")
    assert bloqueado == "lease_lost"
    assert agente.ok("get_job", job_id=job_id)["job"]["progress"] == 0
    passo("9. Recuperação: prazo vencido, outro agente assumiu, token antigo barrado", erro_do_agente_antigo=bloqueado, tentativa=3)

    # 10. Produção simulada e arquivo de teste
    for progresso, etapa in ((20, "Roteiro"), (40, "Narração"), (60, "Animação"), (80, "Renderização"), (100, "Thumbnail")):
        agente.ok("update_progress", job_id=job_id, lease_token=token_3, progress=progresso, step=etapa, idempotency_key=f"b-{progresso}")
    agente.ok("log_event", job_id=job_id, level="info", message="Produção simulada concluída.", idempotency_key="log-1", agent_id="agente-teste-B")
    resultado = agente.ok("write_test_result", job_id=job_id, lease_token=token_3, content=f"Resultado de teste para: {escolhido}", idempotency_key="resultado-1")
    caminho = Path(resultado["path"])
    assert caminho.is_file() and caminho.is_relative_to(dados / "artefatos_teste" / job_id)
    assert agente.erro_de("deliver_artifacts", job_id=job_id, lease_token=token_3, artifacts=[{"kind": "other", "path": str(ROOT / "README.md")}], idempotency_key="entrega-indevida") == "invalid_artifact"
    entregue = agente.ok("deliver_artifacts", job_id=job_id, lease_token=token_3, idempotency_key="entrega-1", artifacts=[
        {"kind": "other", "path": str(caminho), "label": "Resultado de teste"},
        {"kind": "short", "path": f"simulado://{job_id}/video.mp4", "label": "Vídeo simulado"},
    ])
    video = next(a["id"] for a in entregue["artifacts"] if a["kind"] == "short")
    arquivo = next(a for a in entregue["artifacts"] if a["kind"] == "other")
    assert arquivo["sha256"] == resultado["sha256"] == hashlib.sha256(caminho.read_bytes()).hexdigest()
    passo("10. Produção simulada e arquivo de teste gerado", arquivo=caminho.name, sha256=arquivo["sha256"], tamanho_bytes=arquivo["size_bytes"])

    # 11. Pronto para revisão
    pacote = agente.ok("prepare_publish_package", job_id=job_id, title=escolhido, description="Descrição de teste.", tags=["teste"], video_artifact_id=video, idempotency_key="pacote-1", agent_id="agente-teste-B")
    assert pacote["published"] is False and pacote["package"]["state"] == "ready_for_human_review"
    final = agente.ok("get_job", job_id=job_id)
    assert final["job"]["state"] == "package_ready" and final["job"]["state_label"] == "PRONTO PARA REVISÃO"
    pagina_tarefa = f"{url_canal}/tarefas/{job_id}"
    pagina.goto(pagina_tarefa, wait_until="networkidle")
    expect(pagina.get_by_text("PRONTO PARA REVISÃO")).to_be_visible()
    pagina.screenshot(path=str(telas / "03_pronto_para_revisao.png"), full_page=True)
    passo("11. Finalizada como PRONTO PARA REVISÃO", publicado=False)

    # 12. Arquivo pelo painel
    with pagina.expect_download() as download:
        pagina.get_by_role("link", name="Resultado de teste").click()
    baixado = Path(download.value.path())
    assert hashlib.sha256(baixado.read_bytes()).hexdigest() == arquivo["sha256"]
    assert baixado.read_text(encoding="utf-8").startswith("ARQUIVO DE TESTE")
    passo("12. Arquivo baixado pelo painel, com o mesmo SHA-256", nome=download.value.suggested_filename)

    # 13. Reinício depois de concluir
    agente.fechar()
    desligar(dados)
    ligar(dados)
    agente = AgenteMcp(dados)
    depois = agente.ok("get_job", job_id=job_id)
    historico = [(t["number"], t["agent_id"], t["outcome"]) for t in depois["attempt_history"]]
    assert depois["job"]["state"] == "package_ready" and depois["job"]["progress"] == 100
    assert historico == [(1, "agente-teste-A", "falhou"), (2, "agente-teste-A", "prazo_vencido"), (3, "agente-teste-B", "entregue")], historico
    repetida = agente.ok("prepare_publish_package", job_id=job_id, title=escolhido, description="Descrição de teste.", tags=["teste"], video_artifact_id=video, idempotency_key="pacote-1", agent_id="agente-teste-B")
    assert repetida["replayed"] is True, "repetir depois de reiniciar não pode duplicar"
    pagina.goto(pagina_tarefa, wait_until="networkidle")
    expect(pagina.get_by_text("PRONTO PARA REVISÃO")).to_be_visible()
    expect(pagina.get_by_text("Agente parou de responder")).to_be_visible()
    with pagina.expect_download() as download:
        pagina.get_by_role("link", name="Resultado de teste").click()
    assert hashlib.sha256(Path(download.value.path()).read_bytes()).hexdigest() == arquivo["sha256"]
    pagina.goto(f"{url_canal}?aba=calendario", wait_until="networkidle")
    expect(pagina.locator("li", has_text=escolhido).locator('select[name="status"]')).to_have_value("pronto_para_revisao")
    pagina.goto(url_canal, wait_until="networkidle")
    pagina.screenshot(path=str(telas / "04_canal_depois_de_reiniciar.png"), full_page=True)
    passo("13. Consistente depois de reiniciar", historico=historico, arquivo="baixado de novo, mesmo SHA-256", calendario="pronto_para_revisao")

    # 14. Isolamento entre canais
    outro = agente.ok("list_jobs", channel_id=OUTRO_CANAL)["jobs"]
    assert job_id not in [j["id"] for j in outro]
    assert http_status(f"{API}/api/studio/channels/{OUTRO_CANAL}/jobs/{job_id}") == 404
    assert http_status(f"{API}/api/studio/channels/{OUTRO_CANAL}/jobs/{job_id}/artifacts/{arquivo['id']}") == 401, "sem token"
    assert http_status(f"{API}/api/studio/channels/{OUTRO_CANAL}/jobs/{job_id}/artifacts/{arquivo['id']}", dados) == 404, "com token, canal errado"
    recomendacao = depois["job"]["recommendation_id"]
    assert agente.erro_de("start_production", channel_id=OUTRO_CANAL, recommendation_id=recomendacao, idempotency_key="cruzado", agent_id="agente-teste-B") == "recommendation_not_in_channel"
    pagina.goto(f"{WEB}/canais/{OUTRO_CANAL}", wait_until="networkidle")
    texto = pagina.locator("main").inner_text()
    assert escolhido not in texto and assunto not in texto
    pagina.goto(f"{WEB}/canais/{OUTRO_CANAL}/tarefas/{job_id}", wait_until="networkidle")
    assert escolhido not in pagina.locator("main").inner_text()
    passo("14. Isolamento entre canais confirmado")

    # 15. Ausência de publicação
    nomes = agente.ferramentas()
    assert not [nome for nome in nomes if any(palavra in nome for palavra in ("publish", "upload", "insert", "authorize", "cancel")) and nome != "prepare_publish_package"]
    pesquisa = sqlite3.connect(dados / "demo.sqlite")
    chamadas = pesquisa.execute("SELECT COUNT(*) FROM api_calls").fetchone()[0]
    pesquisa.close()
    assert chamadas == 0
    pagina.goto(pagina_tarefa, wait_until="networkidle")
    assert pagina.get_by_role("button", name="Publicar").count() == 0
    assert "nada foi enviado ao YouTube" in pagina.locator("main").inner_text()
    agente.fechar()
    passo("15. Sem publicação: nenhuma ferramenta ou botão, nenhuma chamada à API do YouTube", ferramentas_mcp=len(nomes), chamadas_youtube=chamadas)


def botoes(pagina) -> None:
    """Clica em cada botão do painel e confere o efeito: nada de botão só visual."""
    canal = f"{WEB}/canais/{CANAL_BOTOES}"
    usados: list[str] = []

    def usar(nome: str, escopo=None) -> None:
        clicar(pagina, nome, escopo)
        usados.append(nome)

    pagina.goto(canal, wait_until="networkidle")
    expect(pagina.get_by_text("Aguardando sua autorização")).to_be_visible()
    usar("Autorizar simulação")
    expect(pagina.get_by_text("Na fila")).to_be_visible()
    usar("Avançar simulação")
    expect(pagina.get_by_text("Em execução")).to_be_visible()
    usar("Simular falha")
    expect(pagina.get_by_text("Falha simulada na etapa atual.")).to_be_visible()
    usar("Marcar como visto")
    usar("Cancelar")
    pagina.goto(f"{canal}?aba=fila", wait_until="networkidle")
    expect(pagina.get_by_text("Cancelada")).to_be_visible()

    pagina.goto(f"{canal}?aba=recomendacoes", wait_until="networkidle")
    aberta = pagina.locator("article", has=pagina.get_by_role("button", name="Aceitar", exact=True)).first
    assunto = aberta.get_by_role("heading").inner_text()
    cartao = pagina.locator("article", has=pagina.get_by_role("heading", name=assunto, exact=True))
    usar("Aceitar", cartao)
    expect(cartao.get_by_text("Aceita por você")).to_be_visible()
    usar("Descartar", cartao)
    expect(cartao.get_by_text("Descartada")).to_be_visible()
    usar("Reabrir", cartao)
    expect(cartao.get_by_text("Nova", exact=True)).to_be_visible()
    usar("Gerar recomendações")
    usar("Enviar para produção simulada")
    pagina.goto(f"{canal}?aba=fila", wait_until="networkidle")
    expect(pagina.get_by_text("Aguardando sua autorização")).to_be_visible()
    usar("Autorizar simulação")
    usar("Avançar simulação")
    pagina.goto(canal, wait_until="networkidle")

    pagina.goto(f"{canal}?aba=calendario", wait_until="networkidle")
    formulario = pagina.locator("form", has=pagina.get_by_role("button", name="Adicionar ao calendário"))
    formulario.locator('input[name="title"]').fill("Item de teste do calendário")
    usar("Adicionar ao calendário")
    expect(pagina.locator("main").get_by_text("Item de teste do calendário")).to_be_visible()
    linha = pagina.locator("li", has_text="Item de teste do calendário")
    linha.locator('select[name="status"]').select_option("cancelado")
    usar("Salvar", linha)
    pagina.reload(wait_until="networkidle")
    _expect(pagina.locator("li", has_text="Item de teste do calendário").locator('select[name="status"]')).to_have_value("cancelado")
    usar("Remover", pagina.locator("li", has_text="Item de teste do calendário"))
    _expect(pagina.locator("main").get_by_text("Item de teste do calendário")).to_have_count(0, timeout=10000)

    pagina.goto(f"{canal}?aba=historico", wait_until="networkidle")
    pagina.fill('input[name="title"]', "Vídeo de teste do histórico")
    pagina.fill('input[name="published_on"]', "2026-10-01")
    usar("Registrar vídeo")
    linha = pagina.locator("tr", has_text="Vídeo de teste do histórico")
    expect(linha).to_be_visible()
    usar("Remover", linha)
    _expect(pagina.locator("tr", has_text="Vídeo de teste do histórico")).to_have_count(0, timeout=10000)

    pagina.goto(f"{canal}?aba=concorrentes", wait_until="networkidle")
    pagina.fill('input[name="name"]', "Concorrente de teste")
    usar("Associar concorrente")
    linha = pagina.locator("li", has_text="Concorrente de teste")
    expect(linha).to_be_visible()
    usar("Remover", linha)
    _expect(pagina.locator("li", has_text="Concorrente de teste")).to_have_count(0, timeout=10000)

    pagina.goto(f"{canal}?aba=configuracoes", wait_until="networkidle")
    pagina.fill('input[name="tone"]', "Tom de teste")
    usar("Salvar perfil")
    expect(pagina.get_by_text("Perfil salvo.")).to_be_visible()
    pagina.select_option('select[name="auto_package"]', "off")
    usar("Salvar automação")
    expect(pagina.get_by_text("Automação salva.")).to_be_visible()
    pagina.select_option('select[name="pipeline_profile"]', "brother_quill")
    usar("Salvar pipeline")
    pagina.reload(wait_until="networkidle")
    _expect(pagina.locator('select[name="pipeline_profile"]')).to_have_value("brother_quill")
    _expect(pagina.locator('select[name="auto_package"]')).to_have_value("off")
    assert pagina.get_by_text("Só descrito").count() >= 1

    pagina.goto(f"{WEB}/canais/novo", wait_until="networkidle")
    pagina.fill('input[name="name"]', "Canal temporário de teste")
    usar("Cadastrar canal")
    pagina.wait_for_url("**/canais/chn_*")
    url = pagina.url.split("?")[0]
    pagina.goto(f"{url}?aba=configuracoes", wait_until="networkidle")
    pagina.fill('input[name="confirm_name"]', "nome errado")
    usar("Remover canal")
    expect(pagina.get_by_role("alert")).to_contain_text("nome exato")
    pagina.fill('input[name="confirm_name"]', "Canal temporário de teste")
    pagina.get_by_role("button", name="Remover canal").click()
    pagina.wait_for_url("**/canais")
    assert "Canal temporário de teste" not in pagina.locator("main").inner_text()
    passo("16. Botões do painel testados, um a um, com efeito no backend", botoes=sorted(set(usados)))


def responsividade(navegador, problemas: list[str]) -> None:
    estouros = {}
    for largura in (390, 768):
        pagina = navegador.new_page(viewport={"width": largura, "height": 844})
        pagina.on("pageerror", lambda erro: problemas.append(str(erro)))
        for caminho in (f"/canais/{CANAL}", f"/canais/{CANAL}?aba=calendario", f"/canais/{CANAL_BOTOES}?aba=configuracoes", "/fila", "/videos?f=indeterminate", "/metodologia"):
            pagina.goto(WEB + caminho, wait_until="networkidle")
            if pagina.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"):
                estouros[f"{largura}:{caminho}"] = True
        pagina.close()
    assert not estouros, estouros
    passo("17. Sem estouro horizontal em 390 e 768 px")


if __name__ == "__main__":
    sys.exit(main())
