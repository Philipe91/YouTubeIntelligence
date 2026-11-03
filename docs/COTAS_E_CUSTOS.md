# Cotas e custos

Preços e cotas consultados em 03/11/2026. Confira as fontes antes de decidir: eles mudam.

## YouTube Data API

As APIs não cobram por uso dentro da cota. Limites padrão: 10.000 unidades por dia no balde geral e 100 chamadas de `search.list` por dia no balde próprio ([fonte](https://developers.google.com/youtube/v3/determine_quota_cost)). A cota vira à meia-noite do Pacífico.

O aplicativo para antes do limite, com valores locais de 9.000 e 90, configuráveis por balde em `backend/config/quota.toml` ou no `.env`. Toda tentativa conta, inclusive as que falham. A central de canais e o servidor MCP não consomem cota do YouTube.

| Operação | Chamadas | Balde |
|---|---|---|
| Buscar um nicho (1 página, até 50 vídeos) | 1 `search.list` + 1 `videos.list` + até 1 `channels.list` a cada 50 canais novos | Busca e geral |
| Cadastrar canal | 1 `channels.list` | Geral |
| Coletar 50 vídeos de um canal | 1 `playlistItems.list` + 1 `videos.list` | Geral |
| Snapshot de até 50 vídeos | 1 `videos.list` | Geral |

## Exemplo de consumo diário

Estimativa, não medição: **10 canais monitorados, 500 vídeos**, com a cadência padrão de `scoring.toml`.

| Tarefa | Conta | Unidades/dia |
|---|---|---|
| Snapshots: 20 vídeos com até 48 h, de hora em hora | 24 execuções, 1 lote cada | 24 |
| Snapshots: 30 vídeos de 2 a 7 dias, a cada 6 h | 4 execuções, 1 lote cada | 4 |
| Snapshots: 100 vídeos de 7 a 30 dias, por dia | 2 lotes | 2 |
| Snapshots: 350 vídeos antigos, por semana | 50 por dia, 1 lote | 1 |
| Novos vídeos: 2 vezes por dia, 10 canais | 2 × 10 × 2 chamadas | 40 |
| Atualização de canais | 1 lote | 1 |
| **Total** | | **cerca de 72 de 10.000** |

A folga no balde geral é grande. O recurso escasso é a busca: 100 chamadas por dia, cada uma com até 50 resultados, não necessariamente relevantes. Para ir além, use o [formulário de extensão de cota](https://support.google.com/youtube/contact/yt_api_form).

## YouTube Analytics API

Usada só para canais autorizados, com uma consulta por canal por dia. A cota é registrada à parte no Google Cloud; o MVP não a contabiliza no monitor.

## Claude

| Provedor | Custo |
|---|---|
| `none` | Nenhum |
| `claude_cli` | Consome o limite do seu plano Claude |
| `anthropic` | Por token: Claude Opus 5.5 custa US$ 4 por milhão de entrada e US$ 20 por milhão de saída |

**Medição real:** uma geração com `claude_cli` e 3 ideias para um tema produziu 5.630 tokens de saída. A entrada registrada foi de 2 tokens, valor que não representa o prompt, porque o comando conta o cache à parte.

**Estimativa pela API:** cerca de US$ 0,11 de saída e US$ 0,01 a 0,02 de entrada, supondo de 3.000 a 5.000 tokens de entrada: **perto de US$ 0,13 por geração**. Isso é uma extrapolação de uma única execução. O custo real depende da amostra e do esforço configurado.

O modelo é configurável em `YTI_AI_MODEL`. Modelos mais baratos não foram testados neste projeto.

## vidIQ (opcional)

Nada é consumido sem você conectar. Pelo [artigo de suporte](https://support.vidiq.com/en/articles/15082430), a maioria das ferramentas de pesquisa custa 5 créditos por chamada, e créditos não acumulam entre meses.

## Infraestrutura

Sem servidor nem serviço pago: tudo roda na sua máquina. O espaço em disco do SQLite ficou em cerca de 4 MB no demo, com 22 mil snapshots.
