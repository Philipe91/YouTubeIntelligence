# Fase 0: auditoria e relatório de equivalência

Pesquisa feita em 03/11/2026. As descrições do vidIQ vêm de páginas públicas da empresa; ela é a fonte, e o material comercial tende a favorecer o produto. Nenhum código, endpoint interno ou extensão do vidIQ foi inspecionado.

## 1. Ambiente auditado

| Item | Resultado |
|---|---|
| Python | 3.11.9 (`python`); 3.14.3 via `py`. Projeto fixado em 3.11 |
| Node / npm | 24.15.0 / 11.12.1 |
| uv | 0.12.5, usado para o ambiente do backend |
| git | 2.54; `gh` não instalado |
| REA | 6.4.0, MCP conectado, Ghidra/JDK/JADX/adb configurados em `D:\tools` |
| Credenciais | Nenhuma variável `YOUTUBE*`, `GOOGLE*`, `ANTHROPIC*`, `VIDIQ*` no ambiente |
| vidIQ | Nem MCP nem plugin instalados |
| Disco | D: 55 GB livres, C: 16 GB livres |
| Projetos existentes | Nenhum foi alterado. `D:\projetos\YouTubeIntelligence` foi criado vazio |

**Uso do REA:** deliberadamente nenhum neste projeto. A skill orienta não usá-lo em análise de repositório de código comum, e aplicá-lo à extensão ou ao app do vidIQ contrariaria a regra de não extrair código privado.

## 2. Achado crítico: política da API do YouTube

Este é o achado que mais afeta o projeto. As regras abaixo valem também para clientes privados: a definição de "API Client" não traz exceção para uso interno.

| Regra | Efeito no sistema | Fonte |
|---|---|---|
| III.E.4.h: não usar dados da API "to create new or derived data or metrics" | Outlier, VPH, aceleração e ranking de oportunidades, calculados com dados reais, **violam a regra padrão** | [Developer Policies](https://developers.google.com/youtube/terms/developer-policies) |
| III.E.2: não agregar dados de donos de conteúdo diferentes | Comparar concorrentes com dados reais é restrito na regra padrão | idem |
| III.E.4.b e d: estatísticas de canais sem autorização do dono têm limite de 30 dias | Snapshots de concorrentes só valem 30 dias; a linha de base histórica fica curta | idem |
| III.L + política de métricas derivadas (desde 01/06/2026) | Exceção para desenvolvedores com uso analítico que aceitem a emenda: permite scores próprios, rankings e comparações entre canais, com retenção de 36 meses para estatísticas e métricas derivadas. Títulos, nomes e descrições seguem em 30 dias | [Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy) |
| III.E.6: scraping proibido | Nenhum coletor por scraping. Tudo vem das APIs oficiais | Developer Policies |
| III.E.4.e, g: exibir dados atuais; apagar em até 7 dias após revogação ou pedido | Job de refresh e rotina de exclusão por canal | idem |

**Consequência no produto:** o sistema tem três estados, descritos em `ARQUITETURA.md` §3. O cálculo de métricas sobre dados reais fica bloqueado até você registrar uma referência de aprovação do Google. O modo demo, com dados fictícios, usa todas as funções sem violar nada.

Pontos que a leitura não resolveu e valem consulta ao Google no pedido: se a exceção cobre plenamente um uso privado de um único operador e como ela se concilia com a III.E.2. A política de derivadas cita comparações entre canais, mas não menciona a agregação entre donos.

## 3. Outras restrições das APIs que moldam o sistema

| Fato | Consequência | Fonte |
|---|---|---|
| Cota padrão: 10.000 unidades/dia; `search.list` tem balde próprio, com 100 chamadas/dia a 1 unidade por chamada (mudança de 01/06/2026) | Monitor de cota por balde. A descoberta por busca é o recurso escasso | [Quota](https://developers.google.com/youtube/v3/determine_quota_cost), [Revision history](https://developers.google.com/youtube/v3/revision_history) |
| `videos.list`, `channels.list`, `playlistItems.list`: 1 unidade | Snapshot de até 50 vídeos custa 1 unidade | idem |
| `videos.batchGetStats` (03/06/2026): balde próprio de 10.000/dia; a documentação não informa o máximo de IDs | Candidato a otimização futura. O MVP usa `videos.list` | [Docs](https://developers.google.com/youtube/v3/docs/videos/batchGetStats) |
| Não há campo "é Short" na Data API; `videoDuration=short` significa menos de 4 min | Por vídeo: duração até 180 s, rotulada como estimada. Totais de canais próprios por `creatorContentType` | [search.list](https://developers.google.com/youtube/v3/docs/search/list), [dimensões](https://developers.google.com/youtube/analytics/dimensions) |
| Contagem mudou: Shorts em 31/03/2025; todos os formatos em 24/08/2026 | Intervalos e comparações que cruzam essas datas recebem alerta | [videos](https://developers.google.com/youtube/v3/docs/videos) |
| Analytics API não lista impressões de thumbnail nem CTR | CTR aparece como "indisponível", nunca estimado | [métricas](https://developers.google.com/youtube/analytics/metrics) |
| Nenhuma API pública entrega volume de busca | Volume de busca aparece como "indisponível". A demanda usa um proxy rotulado | Docs acima |
| `pageInfo.totalResults` é aproximado | Peso baixo na concorrência, com rótulo de estimativa | search.list |

## 4. vidIQ MCP e plugin para Claude Code

- Endpoint: `https://mcp.vidiq.com/mcp`. Instalação no Claude Code: `claude mcp add --transport http vidiq https://mcp.vidiq.com/mcp`, depois `/mcp` para entrar na conta. ([vidIQ/Claude](https://vidiq.com/claude/))
- A página cita "52 tools": 46 principais e 6 utilitárias gratuitas. Ela lista só cinco utilitárias, então a contagem pode estar imprecisa.
- Disponível em todos os planos (Free, Boost, Max), usando o mesmo saldo de créditos do app. Uma FAQ antiga da própria empresa dizia "somente Max"; prevalece o artigo de suporte.
- Créditos: 5 por chamada na maioria das ferramentas de pesquisa; 10 em análise de Shorts; 25 em análise de vídeo longo; 22 por thumbnail; 14 por 1.000 caracteres de voz; 9 por minuto de vídeo-fonte em clipes. Créditos não acumulam entre meses. ([Suporte](https://support.vidiq.com/en/articles/15082430))
- Limitações: Channel Analytics só para canais conectados; a escrita em vídeos exige login e aprovação; não envia vídeos novos.
- **Plugin para Claude Code:** a página oficial o menciona, mas não encontrei instruções de instalação nem repositório. **Não verificado além dessa menção.** A conexão MCP acima é o caminho documentado.

## 5. Tabela de equivalência

Esforço: P (até 1 dia), M (2 a 4 dias), G (1 semana ou mais). "Fontes" são as nossas. Todos os algoritmos são próprios e nenhum é apresentado como fórmula do vidIQ.

| Função vidIQ (o que é documentado) | Entrada | Algoritmo próprio proposto | Fontes | Limitações | Esforço | Status no MVP |
|---|---|---|---|---|---|---|
| **Outliers:** views comparadas à média do canal em período semelhante; faixas 2x/5x/10x; abas por formato | Vídeo, canal, formato, snapshots | **IDR:** views na idade *a* ÷ mediana dos pares do mesmo canal e formato na mesma idade; z robusto com MAD; n mínimo | `videos.list`, `playlistItems.list`, snapshots | Primeiros dias têm poucos pares medidos; 30 dias de limite sem aprovação | M | Feito |
| **VPH:** velocidade mostrada por vídeo | Dois ou mais snapshots | Δviews ÷ Δhoras. Média histórica (views ÷ idade) separada e rotulada | Snapshots | Exige coleta contínua; o primeiro snapshot não gera VPH | P | Feito |
| **Keyword Research:** score de competição e volume; volume estimado em janela de 30 dias | Termo | Sem volume de busca (indisponível). Demanda = proxy de views/dia dos resultados; concorrência separada | `search.list`, `videos.list`, `channels.list` | Proxy mede atenção ao conteúdo, não buscas; 100 buscas/dia | M | Feito como proxy |
| **Trend Alerts:** e-mail por palavra, categoria ou concorrente, com limite de VPH | Termos, limites | Termos de títulos em vídeos acelerando, com mínimo de vídeos e canais; aceleração entre janelas sucessivas | Snapshots | Termos por n-grama, sem semântica; **no MVP é painel, sem envio de e-mail** | M | Parcial |
| **Competitors:** lista de canais, top vídeos ordenados por views, VPH, outlier | Canal ou @handle | Cadastro, monitoramento, cadência, formatos, títulos, termos com melhor desempenho | `channels.list`, `playlistItems.list` | Comparação entre donos depende da aprovação | M | Feito |
| **Channel Audit:** nota do canal e pontos fracos (descrito por terceiros) | Canal próprio com OAuth | Sem nota única. Métricas medidas por tipo de conteúdo; CTR indisponível | YouTube Analytics API | Sem CTR e sem curva de retenção no MVP | M | Parcial (conector não testado com conta real) |
| **Daily Ideas:** ideias diárias com previsão de views | Canal, nicho | Ideias a partir de oportunidades com evidência citada; **sem previsão de views** | Métricas + Claude | Sem promessa de resultado; custo de IA quando usar API | M | Feito sob demanda |
| **AI Coach:** chat com dados do canal e presets | Pergunta, dados | Não há chat no MVP. Geração estruturada de títulos, hooks, briefing e roteiro | Métricas + Claude | Fora do escopo do MVP | G | Não feito |
| **MCP:** ferramentas para agentes | Agente | Conector opcional e isolado. O app funciona sem ele | vidIQ MCP | Consome seus créditos; precisa da sua conta | P | Interface isolada, sem chamadas reais |

## 6. Fontes

- [vidIQ: Outliers](https://support.vidiq.com/en/articles/9660010-outliers)
- [vidIQ: Keywords Research](https://support.vidiq.com/en/articles/9421214-keywords-research)
- [vidIQ: Trend Alerts](https://vidiq.com/features/trend-alerts/)
- [vidIQ: Daily Ideas](https://vidiq.com/features/daily-ideas/)
- [vidIQ: AI Coach](https://support.vidiq.com/en/articles/8017871-ai-coach)
- [vidIQ: MCP (suporte)](https://support.vidiq.com/en/articles/15082430)
- [vidIQ: Claude](https://vidiq.com/claude/)
- [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [YouTube Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy)
- [YouTube Data API: cotas](https://developers.google.com/youtube/v3/determine_quota_cost)
- [YouTube Data API: histórico de revisões](https://developers.google.com/youtube/v3/revision_history)
- [YouTube Analytics API: métricas](https://developers.google.com/youtube/analytics/metrics)
- [YouTube Analytics API: dimensões](https://developers.google.com/youtube/analytics/dimensions)
