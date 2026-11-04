# Pipelines de produção existentes

Levantamento somente leitura, em 03/11/2026. Nada foi alterado ou executado nesses projetos. Li documentos e pontos de entrada: comandos e argumentos são previsões a confirmar antes de ligar qualquer execução.

## Pode ser integrado

| Projeto | Onde | Etapas que cobre | Situação |
|---|---|---|---|
| **Brother Quill** | `D:\projetos\BROTHER QUILL` | Roteiro, QA, animação, render, mixagem | **Melhor candidato:** canal real no ar, pipeline documentado em `CONTINUAR_AQUI.md` |
| **Remotion / TTS** | `D:\ViralReplicator_motion\remotion` | Narração (`tts.py`, `vs_narrar.py`), timeline | Usado pelo Brother Quill |
| **VoiceStudio** | `D:\VoiceStudio` | Motor de voz local | Precisa estar ligado. Tem `mcp_server.py` próprio, não avaliado |
| **ViralReplicator** | `Documents\ViralReplicator` | `produce_video.py --etapa`, montagem `editor.py`, thumbnails `comfy_batch.py`, clipes `comfy_video.py` | Maior cobertura, inclusive thumbnail. Usa ComfyUI e GPU. **Tem fluxo próprio com Codex:** ler `AGENTS.md` e `docs/gpt-inbox.md` antes de ligar |
| **MoneyPrinterTurbo** | `D:\projetos\MoneyPrinterTurbo` | Roteiro, narração e montagem em uma execução (`cli.py`) | Serve para vídeo curto com banco de imagens. Não separa etapas |

## Não indicado para este fim

| Projeto ou recurso | Motivo |
|---|---|
| **REA** (`rea` 6.4 e skill `reverse-engineer-anything`) | Engenharia reversa. Sem fila, agendamento ou orquestração |
| **Estúdio de Edição** (`EDIÇÃO DE VIDEO`) | Edita material filmado (ASMR, gráfica), com fluxo manual próprio |
| **Cortes de podcast** (`agentes do dinheiro\04-...`) | Corta vídeos existentes; não é produção para canal dark |
| **CENTRAL** | Painel de projetos e Git, sem produção |
| Skills instaladas (`fableboss`, `mobile-app-ui-design`, sincronizadas de documentos) | Nenhuma é de produção de vídeo. `fableboss` é um papel de coordenação |

## Pipeline do Brother Quill

Conforme `CONTINUAR_AQUI.md`:

```
roteiros/gen_<id>.py → tts.py (VoiceStudio ligado) → anim/qa/rodada.sh (QA) → node render.mjs --frames --fps=24 --workers=1
  → node render.mjs --v=<id> --cortes=<json> → mix_longo.py → ffmpeg → upload manual
```

**Atualização:** existe um caminho real para vídeos curtos em `docs/INTEGRACAO_BROTHER_QUILL.md`. O adaptador novo resolve o caminho técnico. Os itens 1 e 2 abaixo continuam abertos para vídeos publicáveis: o roteiro escolhe só entre cenas prontas, e a revisão visual segue humana.

O que impedia ligar direto:

1. **O roteiro é código escrito à mão por vídeo** (`gen_gunther.py` tem cenas e fontes próprias). Falta o passo mais difícil: transformar o briefing nesse roteiro. Isso exige trabalho do Claude e sua revisão.
2. **O QA é parte do processo:** há revisão geométrica e visual obrigatória, com notas de agentes revisores. Não é um passo que se automatiza sem perder qualidade.
3. **Render pesa:** mais de 1 worker estoura a RAM. Precisa de janela de execução, sem o jogo aberto.
4. **Thumbnail:** não encontrei gerador dedicado neste projeto.
5. **Publicar:** é manual, e cada vídeo exige seu OK.

## Como os adaptadores funcionam

`backend/app/studio/pipelines.py` define o que cada pipeline precisa oferecer, sem que o estúdio saiba quem executa.

| Etapa | Identificador |
|---|---|
| Roteiro | `roteiro` |
| Narração | `narracao` |
| Animação | `animacao` |
| Renderização | `renderizacao` |
| Thumbnail | `thumbnail` |

| Adaptador | O que faz hoje |
|---|---|
| `simulado` | Roda de verdade, sem custo. Não gera mídia |
| `comando` | **Só descreve** comando, pasta, requisitos e saída. Executar retorna `pipeline_execution_disabled` |
| `indefinido` | Etapa sem caminho encontrado. Retorna `pipeline_stage_undefined` |
| `brother_quill_v1` | Real. Quem executa é `bq_worker.py`, com as operações de `execucao.toml`. Pedir `run` retorna `use_worker` |

Os perfis ficam em `backend/config/pipelines.toml` e cada canal escolhe um na aba Configurações. `pipelines.py` não importa `subprocess`, e um teste garante isso: a execução fica isolada no worker. O agente vê o plano com `get_pipeline_plan`.

## Para ligar um pipeline real

1. Confirmar os comandos lendo o código de cada etapa.
2. Escrever um adaptador novo, implementando `plan` e `run`, com suas próprias proteções.
3. Seguir o modelo do Brother Quill: o agente envia dados validados, e um worker com comandos fixos executa. Assim, o texto do agente nunca vira comando.
4. Listar o adaptador e as operações em `execucao.toml`.
5. Testar primeiro com um trecho curto, sem o jogo aberto.
