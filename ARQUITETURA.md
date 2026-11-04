# Arquitetura

## 1. Visão geral

Aplicativo local: tudo roda na sua máquina, sem serviço pago obrigatório.

```
 Next.js (localhost:3000)
      │ fetch via proxy /api
      ▼
 FastAPI (127.0.0.1:8000)
      │
      ├── services ──► metrics/   funções puras, determinísticas, testadas
      │            └─► ai/        geração separada; só recebe evidências prontas
      ├── policy.py               trava de política e retenção
      ├── collector.py ──► connectors/youtube_data.py      (chave de API)
      │                └─► connectors/youtube_analytics.py (OAuth, só canais próprios)
      ├── connectors/vidiq_mcp.py opcional, isolado, desligado por padrão
      └── SQLite: data/demo.sqlite  |  data/live.sqlite
```

| Decisão | Motivo |
|---|---|
| Next.js + FastAPI | Pedidos no brief; Node 24, Python 3.11 e uv disponíveis |
| `sqlite3` + migrações SQL numeradas | Sem ORM: menos dependências e migrações legíveis |
| **Um arquivo de banco por modo** | Dado fictício não tem como se misturar com dado real |
| Scheduler próprio com tabela `jobs` | Baixo custo; roda como processo ou pelo Agendador de Tarefas |
| Gráficos em SVG próprio | Sem biblioteca pesada; controle total dos rótulos de procedência |

## 2. Camadas

1. **Conectores:** falam com APIs externas. Cuidam de cache, retry, rate limit e registro de cota.
2. **Coletor:** grava dados crus e snapshots. Não calcula nada.
3. **Métricas (`app/metrics/`):** funções puras, sem I/O, com a mesma entrada produzindo a mesma saída. Toda saída carrega amostra, confiança e explicação.
4. **IA (`app/ai/`):** recebe um pacote de evidências. Nunca escreve em tabelas de métricas. Toda saída é gravada à parte e marcada como gerada.
5. **API e dashboard:** apresentam cada valor com seu rótulo de procedência.

### Procedência

Todo número exposto segue o envelope:

```json
{"value": 123.4, "kind": "measured", "source": "videos.list", "as_of": "...", "reason": null}
```

| `kind` | Significado | Exemplo |
|---|---|---|
| `measured` | Veio direto da API | views, retenção média de canal próprio |
| `calculated` | Conta determinística sobre valores medidos | VPH observado, IDR |
| `estimated` | Aproximação ou proxy | formato por duração, demanda |
| `unavailable` | Não existe fonte, e o motivo é informado | CTR, volume de busca |
| `blocked` | Bloqueado pela política | IDR sobre dado real sem aprovação |

## 3. Estados de política

Definidos em `app/policy.py`, com base nas regras descritas em `docs/RELATORIO_EQUIVALENCIA.md` §2.

| Estado | Como ativar | Dados | Métricas derivadas | Retenção |
|---|---|---|---|---|
| `demo` | Padrão | Fictícios, `data/demo.sqlite` | Liberadas | Sem limite (não há dado da API) |
| `live_restricted` | `YTI_MODE=live` | API real, `data/live.sqlite` | **Bloqueadas** | Tudo de terceiros: 30 dias |
| `live_approved` | `YTI_MODE=live` + registro completo em `config/compliance.toml` | API real | Liberadas, com aviso de origem | 36 meses só com o escopo `extended_storage`; textos: 30 dias com refresh |

O registro é uma declaração sua de que o Google aprovou o uso. O app não consegue verificá-la e registra isso na tela Sistema. Detalhes em `docs/CONFORMIDADE.md`.

## 3a. Estúdio multicanal

`app/studio/` gerencia seus canais, em banco próprio (`data/studio.sqlite`), independente do modo e sem dados da API.

| Módulo | Função |
|---|---|
| `store.py` | Canais, concorrentes, histórico, calendário, recomendações. Consultas limitadas por canal |
| `recommend.py` | Cruza pesquisas com o perfil editorial. Canal real nunca usa dado fictício |
| `contract.py` | Contrato `yti.agent.v1`: estados, idempotência, lease, recuperação |
| `pipelines.py` | Adaptadores por etapa. Só o simulado executa; os demais apenas descrevem |
| `simulator.py` | Agente simulado, uma etapa por chamada, sem render. Gera só um texto de teste |
| `mcp_server.py` | Servidor MCP stdio para o Claude Code. Sem ferramentas de autorizar ou publicar |
| `status.py` | Estado do YouTube e do Claude, só leitura e sem rede |
| `router.py` | API usada pelo dashboard |

Contrato em `docs/CONTRATO_AGENTE.md`.

## 4. Banco de dados

Migrações em `backend/migrations/`.

| Tabela | Conteúdo |
|---|---|
| `niches` | Nicho, palavras-chave, idioma, país |
| `channels`, `channel_snapshots` | Canais monitorados e próprios, e suas estatísticas no tempo |
| `videos`, `snapshots` | Vídeo, formato com origem da classificação, e medições de views |
| `searches`, `search_results` | Cada busca executada, com filtros e posição dos resultados |
| `analytics_daily` | Métricas diárias de canais próprios, por tipo de conteúdo |
| `oauth_channels` | Autorização por canal, com data da última verificação (30 dias) |
| `api_calls`, `api_cache` | Registro de cota e cache de respostas |
| `jobs` | Tarefas periódicas |
| `ai_generations` | Saídas geradas, com provedor, modelo e evidências usadas |

## 5. Algoritmos

Parâmetros em `backend/config/scoring.toml`. Todos são próprios; nenhum reproduz fórmula do vidIQ.

### IDR: Índice de Desempenho Relativo

Para um vídeo *V* com idade *a* e formato *f*:

1. Pares: outros vídeos do mesmo canal e formato.
2. Para cada par, views na idade *a*:
   - **medido:** interpolação linear entre snapshots ao redor de *a*, ou snapshot próximo o bastante;
   - **faixa de idade (reserva):** par sem histórico cuja idade atual está entre *a*/1,5 e *a*×1,5.
3. `IDR = views(V) / mediana(pares)`.
4. `z robusto = (ln(1+v) − mediana(ln(1+pares))) / (1,4826 × MAD)`.
5. Menos de 5 pares resulta em "amostra insuficiente", sem valor. A confiança sobe com o tamanho da amostra e a parcela de pares medidos.

### VPH

- **Observado:** `(views₂ − views₁) / horas entre snapshots`. Só existe com dois snapshots.
- **Média histórica:** `views / horas desde a publicação`. Coluna separada, com outro nome: não é velocidade recente.
- Alertas: queda de contagem (sem valor), intervalo curto demais (sem valor), intervalo longo, intervalo que cruza mudança de contagem.

### Aceleração

Compara a taxa nas janelas `[t−J, t]` e `[t−2J, t−J]`, com views interpoladas nas bordas, sem extrapolar. Vídeos novos desaceleram naturalmente, então a tela mostra a idade ao lado. Sem cobertura nas bordas, o resultado é "dados insuficientes".

### Tendências

N-gramas de títulos, com mínimo de vídeos e de canais distintos, ordenados pela parcela de vídeos em aceleração e pela razão das velocidades somadas.

### Oportunidades (experimental)

Quatro indicadores separados, de 0 a 100:

| Indicador | Composição | Rótulo |
|---|---|---|
| Demanda | Log da mediana de views/dia na amostra | estimado (proxy; não é volume de busca) |
| Concorrência | Porte mediano dos canais, oferta recente, `totalResults` aproximado | estimado |
| Relevância | Sobreposição do termo com o vocabulário do nicho e do seu canal | calculado |
| Confiança | Tamanho da amostra, diversidade de canais, cobertura de snapshots | calculado |

`pontuação = 0,4·demanda + 0,3·(100 − concorrência) + 0,3·relevância`. Com confiança abaixo do mínimo, a pontuação fica nula e a linha vai para o fim. A tela mostra a justificativa e nunca promete viralização.

## 6. Segurança

| Risco | Medida |
|---|---|
| Vazamento de chave | Chave só no `.env`, ignorado pelo git; filtro de log remove `key=`, tokens e `Bearer` |
| Tokens OAuth | Refresh token no Gerenciador de Credenciais do Windows, via `keyring`; nunca no SQLite |
| Exposição de rede | API e front escutam só em `127.0.0.1`; CORS restrito |
| Injeção de prompt | Títulos e descrições de terceiros entram em bloco de dados não confiáveis, higienizados; provedor CLI roda sem ferramentas; saída validada |
| Ações em canais | Escopos OAuth somente leitura. Não há código de escrita no YouTube |
| Revogação | `delete-channel-data` e revogação apagam tokens e dados do canal |

## 7. Conexão opcional com vidIQ

`app/connectors/vidiq_mcp.py` define uma interface e uma implementação nula. Nenhum módulo principal importa esse arquivo; só a tela Sistema consulta o estado dele. O uso recomendado é pelo próprio Claude Code, com `claude mcp add`, consumindo seus créditos só quando você pedir.
