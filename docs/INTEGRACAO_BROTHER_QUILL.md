# Integração real com o Brother Quill

Situação em 03/11/2026. **O caminho técnico funciona de ponta a ponta. O vídeo gerado é uma demonstração: não está pronto para publicar**, pelos motivos em [Limitações](#limitações).

## O que acontece

```
Painel                      Claude Code (MCP)                Worker (processo próprio)
──────                      ─────────────────                ─────────────────────────
Recomendação do sistema
Você aprova o briefing
Você autoriza a tarefa ──►  get_job, claim_job
                            escreve o roteiro
                            submit_script  ── valida contra o catálogo
                            start_production_run ─────────►  cópia do commit fixado
                            (a sessão pode terminar)         narração (tts.py)
                                                             cenas e tempos (tl.js)
Etapas e quadros reais ◄──────────────────────────────────   revisão geométrica
                                                             quadros (render.mjs)
                                                             codificação, mixagem
                                                             validação com ffprobe
                                                             entrega com SHA-256
                            validate_video  ── relê o disco
                            prepare_publish_package
Vídeo, revisão             
```

Não há etapa simulada neste caminho. Tarefa real não aceita arquivo `simulado://`, e o simulador recusa tarefa real.

## Peças

| Arquivo | Função |
|---|---|
| `backend/config/execucao.toml` | Chave geral, adaptadores e operações permitidos, commit fixado, limites de duração e memória |
| `backend/config/bq_catalogo.toml` | Cenários, situações, gráficos e efeitos aceitos no roteiro |
| `backend/app/studio/bq_script.py` | Valida o roteiro. Campo desconhecido, valor fora do catálogo ou texto com caractere invisível é recusado |
| `backend/app/studio/bq_worker.py` | Executa as etapas, grava o progresso, confere o arquivo final |
| `backend/app/studio/production.py` | Regras para iniciar, validar e revisar |
| `backend/migrations_studio/003_producao_real.sql` | Roteiro, etapas, validação, revisão |
| `frontend/src/components/production.tsx` | Painel: ideia, título, briefing, etapas, roteiro, vídeo, revisão |

## Segurança

| Proteção | Como funciona |
|---|---|
| Comandos | Montados só no código, em lista de argumentos e sem shell. Um teste garante isso |
| Texto externo | O roteiro vira arquivo JSON e nunca argumento de comando. Um teste envia um texto malicioso e procura por ele nos comandos |
| Operações | `Executor` recusa o que não estiver em `execucao.toml` |
| Adaptadores | Só `brother_quill_v1`, e só em canal com esse perfil |
| API | Escrita e download exigem o token de `data/.api_token`, que só o servidor do painel recebe. Host fora de `127.0.0.1` ou `localhost` é recusado |
| Caminhos | O id da tarefa é validado por padrão, e todo arquivo precisa estar na pasta da tarefa. O download confere pasta e SHA-256 |
| Autorização | O agente não tem ferramenta para autorizar nem revisar. Essas ações só existem na API com token |
| Publicação | Não existe código de publicação. Aprovar o vídeo só grava sua decisão |
| Memória | Recusa iniciar abaixo de 2 GB livres e para abaixo de 0,6 GB. Os quadros prontos são aproveitados na retomada |
| Concorrência | Uma produção real por vez, um worker de render |

**Limite:** o token protege contra outros programas sem acesso à pasta de dados e contra páginas web. Um agente com terminal irrestrito na sua conta consegue lê-lo. Em produção, deixe o Claude Code só com as ferramentas `yti-producao`, como nos testes abaixo (`--allowedTools "mcp__yti-producao__*"`).

## Projeto original

O projeto `D:\projetos\BROTHER QUILL` não é alterado. O worker só executa `git archive` do commit `8638afc` e extrai o resultado em `data/producao/<tarefa>/`. `node_modules` é uma junção para o original, usada só para leitura.

### Correção que precisa da sua decisão

O motor tem um defeito em cenas externas em `anim/src/v44/mundo44.js:134`: a primeira faixa do céu é curta demais, e o papel aparece como uma faixa clara no topo do vídeo. A correção está em `ENGINE_PATCHES`, em `bq_worker.py`, e vale só na cópia de cada tarefa:

```diff
- Math.max(4, hz / 10) + 8 + (i === 9 ? H * 3 : 0)
+ Math.max(4, hz / 10) + 8 + (i === 9 ? H * 3 : 0) + (i === 0 ? H * 3 + Math.abs(hz) : 0)
```

Levá-la ao projeto original depende da sua autorização. Se o commit fixado mudar e o texto não existir mais, a produção para com `engine_patch_failed`.

## Teste supervisionado

Duas produções reais, cada uma com uma sessão do Claude Code para roteiro e outra para validação. Máquina: i5-10400F, 16 GB, com 3,3 GB livres ao iniciar. Evidência em `docs/evidencias/producao_real_mcp.json`. Os vídeos ficam fora do Git.

| | Versão 1 | Versão 2 |
|---|---|---|
| Tarefa | `job_8e8ab76633154d58` | `job_0b0b4cd15f0b4e4f` |
| Arquivo | `data/producao/<tarefa>/final.mp4` | `data/producao/<tarefa>/final.mp4` |
| Resolução, FPS | 1080x1920, 24 | 1080x1920, 24 |
| Duração, quadros | 14,22 s, 341 de 342 | 14,00 s, 336 de 336 |
| Codecs | H.264, AAC | H.264, AAC |
| Tamanho | 21,3 MB | 22,3 MB |
| Do início à entrega | 130 s, cerca de 91 s em quadros | 152 s, cerca de 108 s em quadros |
| Revisão | Ajustes pedidos, como teste do botão | **Aguardando você** |

A versão 1 expôs três defeitos que a validação automática não pega, só a inspeção dos quadros e a medição do áudio:

| Defeito | Correção |
|---|---|
| Trilha mais alta que a narração (−19 contra −20 dB) | Trilha em 0,08, cerca de 10 dB abaixo |
| Faixa clara no topo das cenas externas | Correção do motor, acima |
| Um quadro cortado pelo `-shortest` | Áudio com a duração exata dos quadros |

Também faltava um caminho para refazer: agora "Pedir ajustes" reabre a recomendação, e o mesmo briefing aceita uma nova tarefa.

## Limitações

**Impedem publicar:**

- **A imagem não conta esta história.** Os cenários vieram do vídeo do Gunther. Não há soldados alemães, presentes, enterro nem ninguém saindo da trincheira: a cena mostra soldados parados e andando. O agente escolhe entre situações prontas e não consegue pedir uma ação nova.
- **Erros históricos na imagem.** O capacete Brodie só chegou em 1915 e 1916, e a trincheira tem chuva em todas as situações.
- **Voz errada.** Usa Edge-TTS. A voz do canal (`vs:quill`) exige o VoiceStudio ligado e ainda não foi testada neste caminho.
- **Fatos não conferidos.** As fontes vêm do agente, sem verificação. A lista "Confira antes de usar" é sua.
- **Áudio não ouvido.** Foi medido, não escutado. O agente também não assiste ao vídeo: a validação automática confere o arquivo, não a qualidade.

**Do adaptador:**

- Só `trincheira` e `campo` estão no catálogo. Os gráficos `quill`, `numero`, `documento` e `relogio` passam pelo validador, mas nenhum foi renderizado no teste real.
- Limite de 20 s e 45 palavras, de propósito.
- Só a revisão geométrica é automática. O revisor visual de `anim/qa/REVISOR.md` não está integrado.
- Sem thumbnail, porque o projeto não tem gerador.
- Os efeitos usam os sons de `remotion/public/sq`, mais simples que os de `mix_longo.py`.
- Só Windows: memória por `GlobalMemoryStatusEx`, junção e `taskkill`.
- A retomada depois de queda por memória só foi testada com executor falso.

## Próximos passos para vídeos longos

1. **Revisar a versão 2** e decidir sobre a correção do motor no projeto original.
2. **Voz do canal:** ligar o VoiceStudio sob demanda e medir o custo de memória.
3. **Cenas sob medida:** decidir como criar cenários para cada história. É o maior trabalho que falta, porque hoje isso é código escrito à mão a cada vídeo.
4. **Revisor visual:** agente que leia as folhas de contato com os critérios de `REVISOR.md`, antes do render completo.
5. **Subir os limites aos poucos:** 60 s, depois 3 min, medindo tempo e memória. No ritmo destes testes, de 3 a 4 quadros por segundo, um vídeo de 10 min levaria de 1 h a 1 h 20 min só em quadros. É uma extrapolação, ainda sem medição em vídeo longo, e a memória pode mudar esse número.
6. **Mixagem completa:** usar `mix_longo.py` na cópia, com os sons de `anim/assets/sfx`.
