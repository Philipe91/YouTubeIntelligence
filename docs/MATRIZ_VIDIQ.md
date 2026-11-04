# Matriz de equivalência com o vidIQ

Pesquisa pública feita em 03/11/2026. Nenhum código privado, endpoint interno, extensão ou asset do vidIQ foi inspecionado. As descrições vêm de páginas da própria empresa, que tendem a favorecer o produto, e de avaliações de terceiros, marcadas como tal. Complementa `docs/RELATORIO_EQUIVALENCIA.md`.

Cada recurso responde às dez perguntas pedidas:

- **Problema**, **Interação**, **Dados** e **Apresenta**: o que o recurso é.
- **Comprovado** e **Inferência**: o que a fonte afirma e o que é dedução nossa.
- **Nossa proposta**, **Limite de API** e **Google**: como fazemos e o que depende de autorização.
- **Estado**: situação no YouTube Intelligence, atualizada a cada etapa.

> **Como ler "feito":** implementado, com testes automáticos e validado no navegador com dados fictícios e com uma API simulada no formato oficial. **Nenhuma consulta com dados reais foi feita**, porque não há chave configurada. A validação real está preparada e pendente. Limites em `docs/INTELIGENCIA.md`.

## Resumo

| Recurso vidIQ | Nosso módulo | Estado | Depende do Google? |
|---|---|---|---|
| Dashboard e feed | Smart Dashboard | Feito | Parte dos cards |
| Outlier Score | Outlier Explorer (IDR) | Feito; score bloqueado em dados reais | Sim, para o score |
| Views Per Hour | VPH observado | Feito; bloqueado em dados reais | Sim |
| Keyword Research | Keyword Intelligence | Feito, sem volume de busca | Índice experimental sim |
| Rising Keywords | Em ascensão | Feito; bloqueado em dados reais | Sim |
| Keywords For You | Para este canal | Feito; parte editorial sempre disponível | Parte |
| Related Keywords | Relacionados | Feito | Coocorrência sim; lista do canal não |
| Matching Terms | Variações | Feito, geradas por regra e sem medição | Não |
| Questions | Perguntas | Feito, por modelo e títulos crus | Não |
| Top Search Terms | Termos do Analytics | Conector só com mock | OAuth do canal |
| Competitor Tracking | Competitor Intelligence | Feito; comparação bloqueada em dados reais | Comparação sim |
| Daily Ideas | Ideias diárias | Feito sob demanda, sem previsão de views | Só a parte com métricas |
| AI Coach | Coach | Feito; sem IA por padrão, Claude testado em 1 pergunta real | Não |
| Channel Audit | Parcial em Analytics | Parcial | OAuth do canal |
| Optimize Score | Title & Thumbnail Lab | Feito como heurística | Não |
| Title Generator | Title Lab | Feito por regras | Não |
| Thumbnail Analysis | Thumbnail Lab | Feito em imagem enviada por você | Não |
| Trend Discovery | Tendências e alertas no feed | Feito; bloqueado em dados reais | Sim |
| Video Scorecard | Detalhe do vídeo | Feito | Parte derivada sim |
| Subscriber Analysis | Série de inscritos | Parcial | OAuth para ganhos e perdas |
| Best Time to Post | Dia da semana observado | Parcial, sem hora | Sim |
| Histórico de pesquisas | Research Center | Feito | Não |

## Dashboard e feed inteligente

- **Problema:** saber o que olhar ao entrar, sem abrir várias ferramentas.
- **Interação:** página inicial com blocos e atalhos.
- **Dados:** canal conectado, ferramentas de pesquisa.
- **Apresenta:** resumos e próximos passos.
- **Comprovado:** a extensão mostra VPH e Outlier na página inicial e tem um menu de ferramentas ([visão geral](https://support.vidiq.com/en/articles/9868197-vidiq-extension-overview)). `Get Started` confere conexão, canais e tarefas interrompidas ([agent skills](https://vidiq.com/agent-skills/)).
- **Inferência:** o conteúdo exato do painel web não está documentado nas páginas lidas.
- **Nossa proposta:** feed por canal, em que cada card abre detalhe real ou executa ação. Inclui status da coleta, disponibilidade de dados e limites de conformidade.
- **Limite de API:** nenhum além dos cards que dependem de dados.
- **Google:** cards com score ficam bloqueados em dados reais.
- **Estado:** feito.

## Outlier Score

- **Problema:** achar vídeos que superaram muito o normal do próprio canal.
- **Interação:** Research > Outliers, abas Videos, Shorts, Channels e Thumbnails; filtros.
- **Dados:** views, período, média do canal.
- **Apresenta:** embed, views, data, score, VPH, engajamento, inscritos e média do canal; envia título ao Create, busca similares, adiciona o canal aos concorrentes.
- **Comprovado:** compara views à média do canal em período semelhante; faixas abaixo de 2x, 2–5x, 5–10x e acima de 10x; filtros de score, views, inscritos, VPH, duração e data ([Outliers](https://support.vidiq.com/en/articles/9660010-outliers)).
- **Inferência:** a fórmula exata e o tamanho da amostra não são publicados.
- **Nossa proposta:** IDR próprio, mediana de pares do mesmo canal e formato na mesma idade, com z robusto e amostra mínima. Explorer com seleção para estudo e comparação lado a lado.
- **Limite de API:** comparar exige snapshots; 30 dias de estatísticas de terceiros sem aprovação.
- **Google:** sim. Sem aprovação, o explorer mostra só dados crus e esconde o score.
- **Estado:** feito.

## Views Per Hour (VPH)

- **Problema:** ver a velocidade atual de um vídeo.
- **Interação:** número sob os vídeos.
- **Dados:** contagem de views ao longo do tempo.
- **Apresenta:** views por hora.
- **Comprovado:** aparece sob a maioria dos vídeos na página inicial ([visão geral](https://support.vidiq.com/en/articles/9868197-vidiq-extension-overview)).
- **Inferência:** se é observado ou média desde a publicação não está documentado.
- **Nossa proposta:** dois valores separados, VPH observado entre snapshots e média histórica.
- **Limite de API:** o primeiro snapshot não gera VPH observado.
- **Google:** sim, é métrica derivada.
- **Estado:** feito; bloqueado em dados reais.

## Keyword Research

- **Problema:** escolher termos com procura e pouca concorrência.
- **Interação:** digita um termo e navega pelas abas.
- **Dados:** estimativa própria de buscas em janela móvel de 30 dias.
- **Apresenta:** volume estimado, competição, score geral de 0 a 100.
- **Comprovado:** volume e competição são estimativas do vidIQ, e as faixas são relativas e mudam por mês ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** a fonte do volume não é divulgada.
- **Nossa proposta:** quatro campos separados: volume medido, estimativa de provedor, índice experimental próprio e indisponível. Sem provedor, volume aparece como indisponível.
- **Limite de API:** nenhuma API pública do YouTube informa volume de busca; `search.list` tem 100 chamadas por dia.
- **Google:** o índice experimental usa dados da API e fica bloqueado em dados reais.
- **Estado:** feito, sem volume. Provedor legítimo depende de contrato seu.

## Rising Keywords

- **Problema:** achar termos em alta.
- **Interação:** aba Rising, com filtro de tópico, idioma e período.
- **Dados:** volume de busca do vidIQ.
- **Apresenta:** termos em ascensão.
- **Comprovado:** destaca palavras cujo volume cresce; idiomas inclusos português e inglês ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** nenhuma adicional.
- **Nossa proposta:** termos de títulos cujos vídeos ganham velocidade em mais de um canal. Mede atenção em vídeos monitorados, não buscas, e diz isso na tela.
- **Limite de API:** cobre só vídeos já coletados.
- **Google:** sim.
- **Estado:** feito; bloqueado em dados reais.

## Keywords For You

- **Problema:** sugerir termos sem precisar pensar em um.
- **Interação:** aba própria, com termos adicionados por Manage.
- **Dados:** dados do canal.
- **Apresenta:** oportunidades.
- **Comprovado:** baseado nos dados do canal e em palavras adicionadas ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** o critério de escolha não é publicado.
- **Nossa proposta:** perfil, backlog, histórico, favoritos e termos do Analytics, cada item com o motivo.
- **Limite de API:** sem OAuth, não há termos reais de descoberta.
- **Google:** só a parte que cruza termos em alta.
- **Estado:** feito.

## Related Keywords

- **Problema:** ampliar o tema com sinônimos.
- **Interação:** aba Related.
- **Dados:** não divulgados.
- **Apresenta:** termo e Related Score.
- **Comprovado:** funciona como um dicionário de sinônimos, com score de proximidade ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** método não divulgado.
- **Nossa proposta:** coocorrência em títulos e palavras do perfil do canal, separadas por origem.
- **Limite de API:** sem semântica; só contagem.
- **Google:** coocorrência sobre dados reais é derivada. As palavras do perfil são suas.
- **Estado:** feito.

## Matching Terms

- **Problema:** achar variações de um termo.
- **Interação:** aba Matching Terms.
- **Dados:** base do vidIQ.
- **Apresenta:** termos com a expressão, em qualquer ordem.
- **Comprovado:** idem ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** nenhuma adicional.
- **Nossa proposta:** variações por regra, em português, inglês e espanhol, marcadas como "sem medição". Autocomplete do YouTube por endpoint não oficial está vetado.
- **Limite de API:** não há API oficial de sugestões.
- **Google:** não; o texto nasce do próprio termo.
- **Estado:** feito.

## Questions

- **Problema:** achar perguntas para virar vídeos.
- **Interação:** aba Questions.
- **Dados:** base do vidIQ.
- **Apresenta:** perguntas sobre o termo.
- **Comprovado:** idem ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** a origem não é informada.
- **Nossa proposta:** perguntas por modelo, marcadas como modelo, mais títulos em forma de pergunta encontrados nos resultados, exibidos crus e com link.
- **Limite de API:** comentários não são coletados.
- **Google:** não para exibição crua.
- **Estado:** feito.

## Top Search Terms

- **Problema:** saber por quais termos as pessoas acham os seus vídeos.
- **Interação:** aba no Keyword Research.
- **Dados:** analytics do canal.
- **Apresenta:** termos e efeito em views e tempo.
- **Comprovado:** idem ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)).
- **Inferência:** provável uso da API oficial de Analytics.
- **Nossa proposta:** relatório oficial de origem de tráfego com `insightTrafficSourceDetail`, até 25 linhas ([relatórios](https://developers.google.com/youtube/analytics/channel_reports)).
- **Limite de API:** a página lida não confirmou o valor `YT_SEARCH` no trecho carregado. Precisa de teste com conta real.
- **Google:** OAuth do canal; não exige a aprovação de derivadas para exibição crua.
- **Estado:** conector com mock, nunca testado com conta real.

## Competitor Tracking

- **Problema:** acompanhar canais parecidos.
- **Interação:** adiciona canal e vê vídeos e crescimento.
- **Dados:** dados públicos do canal.
- **Apresenta:** crescimento, vídeos ordenados por views e VPH.
- **Comprovado:** comparação de períodos, ordenação por VPH e limite de 20 canais por canal conectado, segundo a [página do recurso](https://vidiq.com/features/competitors/) e avaliações. O agente só altera a lista com aprovação ([agent skills](https://vidiq.com/agent-skills/)).
- **Inferência:** limites podem ter mudado, pois as páginas não têm data clara.
- **Nossa proposta:** lista por canal, cadastro por URL, @handle ou ID, vídeos, calendário de publicação, vídeos de referência, oportunidades e relatório com links.
- **Limite de API:** `channels.list` e `playlistItems.list`; agregação entre donos restrita (III.E.2).
- **Google:** rankings, cadência, termos e padrões ficam bloqueados.
- **Estado:** feito.

## Daily Ideas

- **Problema:** não ficar sem ideias.
- **Interação:** arrasta para salvar ou descartar; abre a ideia para pesquisar concorrentes.
- **Dados:** vídeos do canal, canais parecidos, tendências.
- **Apresenta:** previsão de views em faixas, análise de público, demanda, palavras, vídeos semelhantes, títulos.
- **Comprovado:** atualiza diariamente; a previsão é ranking relativo sem garantia ([Daily Ideas](https://vidiq.com/features/daily-ideas/)).
- **Inferência:** método de previsão não publicado.
- **Nossa proposta:** ideias por canal, com todos os campos pedidos, sem previsão de views. Salvar, rejeitar, favoritar e pôr no calendário.
- **Limite de API:** sem dados reais, a ideia é editorial.
- **Google:** só a parte que usa métricas.
- **Estado:** feito, com geração sob demanda: não atualiza sozinho todo dia. O texto é por regras; Claude é opcional pelo Coach ou pelo contrato MCP.

## AI Coach

- **Problema:** perguntar em vez de procurar.
- **Interação:** chat com modos, sugestões, histórico, renomear e apagar.
- **Dados:** analytics, busca, tendências, concorrentes, imagens e vídeos anexados.
- **Apresenta:** respostas, títulos, auditoria.
- **Comprovado:** modos Fast, Deep Thinking e Max; não assiste aos vídeos; dados podem atrasar até 48 h; contexto por conversa ([AI Coach](https://support.vidiq.com/en/articles/8017871-ai-coach)).
- **Inferência:** arquitetura interna desconhecida.
- **Nossa proposta:** consultor por canal com ferramentas internas de leitura, resposta separada em observações, hipóteses e recomendações, fontes verificadas, ferramentas usadas e custo registrado. Sem IA por padrão, com Claude opcional.
- **Limite de API:** só o que o aplicativo já tem no banco.
- **Google:** obedece à mesma trava: em dados reais, as ferramentas não entregam scores.
- **Estado:** feito.

## Channel Audit

- **Problema:** diagnosticar o canal.
- **Interação:** painel na ferramenta; o agente revisa 30 a 90 dias e propõe até três melhorias.
- **Dados:** analytics do canal.
- **Apresenta:** resumo e ações; segundo o blog da empresa, médias de título, descrição e tags.
- **Comprovado:** [Agent skills](https://vidiq.com/agent-skills/); [guia de auditoria](https://vidiq.com/blog/post/youtube-channel-audit/), possivelmente antigo.
- **Inferência:** o detalhe do painel atual não está nas páginas lidas.
- **Nossa proposta:** sem nota única. Analytics por formato e pergunta ao Coach.
- **Limite de API:** CTR e impressões não constam da Analytics API.
- **Google:** OAuth do canal.
- **Estado:** parcial. Ainda sem tela de auditoria própria.

## Optimize Score

- **Problema:** melhorar o pacote antes de publicar.
- **Interação:** lista de sugestões na página de envio do YouTube Studio.
- **Dados:** metadados do vídeo em edição.
- **Apresenta:** score e sugestões.
- **Comprovado:** a extensão tem SEO Scorecard com sugestões ([visão geral](https://support.vidiq.com/en/articles/9868197-vidiq-extension-overview)). Um post do blog cita peso de 48% para a thumbnail, mas sem data clara.
- **Inferência:** a fórmula atual não é pública.
- **Nossa proposta:** não há score único de SEO. O Lab dá notas por critério, com explicação.
- **Limite de API:** sem escrita no YouTube, de propósito.
- **Google:** não; analisa só o seu próprio texto e imagem.
- **Estado:** feito como heurística, sem validação de resultado.

## Title Generator

- **Problema:** gerar títulos.
- **Interação:** digita um tema e recebe opções.
- **Dados:** não divulgados.
- **Apresenta:** títulos; o Packaging Studio também os pontua.
- **Comprovado:** [Agent skills](https://vidiq.com/agent-skills/).
- **Inferência:** uso de modelo de linguagem.
- **Nossa proposta:** alternativas por modelo de texto no idioma do canal, avaliadas por critérios explicados.
- **Limite de API:** nenhum.
- **Google:** não.
- **Estado:** feito por regras.

## Thumbnail Analysis

- **Problema:** saber se a thumbnail funciona.
- **Interação:** envia imagem ou gera por IA e recebe nota.
- **Dados:** a imagem.
- **Apresenta:** notas e prévia ao lado de vídeos que disputam o mesmo termo.
- **Comprovado:** existem geração, refino e nota de thumbnail ([agent skills](https://vidiq.com/agent-skills/)); a prévia é descrita no blog.
- **Inferência:** critérios não publicados.
- **Nossa proposta:** análise por imagem: contraste, brilho, saturação, complexidade, composição e leitura em tamanho pequeno. Prévia em card neutro. Sem geração nesta fase.
- **Limite de API:** nenhum.
- **Google:** não.
- **Estado:** feito. Não detecta texto por OCR nem rostos.

## Trend Discovery

- **Problema:** agir antes que o assunto esfrie.
- **Interação:** Trend Radar, alertas por e-mail.
- **Dados:** tendências e buscas.
- **Apresenta:** urgência e avisos sobre sinais enganosos.
- **Comprovado:** [Agent skills](https://vidiq.com/agent-skills/), [Trend Alerts](https://vidiq.com/features/trend-alerts/).
- **Inferência:** nenhuma adicional.
- **Nossa proposta:** tendências por termo e alertas no feed. Sem e-mail.
- **Limite de API:** só vídeos coletados.
- **Google:** sim.
- **Estado:** feito; bloqueado em dados reais.

## Video Scorecard

- **Problema:** avaliar um vídeo ao abri-lo.
- **Interação:** painel lateral com abas.
- **Dados:** vídeo e canal.
- **Apresenta:** dados do vídeo, do canal e o Coach.
- **Comprovado:** abas Views, Overview e AI Coach ([visão geral](https://support.vidiq.com/en/articles/9868197-vidiq-extension-overview)).
- **Inferência:** nenhuma adicional.
- **Nossa proposta:** página do vídeo com medidas, curva e "guardar para estudo".
- **Limite de API:** só vídeos coletados; sem extensão de navegador.
- **Google:** parte derivada sim.
- **Estado:** feito.

## Subscriber Analysis

- **Problema:** entender a audiência.
- **Interação:** ferramenta "subscriber insights" do canal autorizado.
- **Dados:** analytics privadas.
- **Apresenta:** não detalhado nas páginas lidas.
- **Comprovado:** existe entre as ferramentas de canal autorizado ([agent skills](https://vidiq.com/agent-skills/)). Sem artigo de suporte encontrado.
- **Inferência:** provável uso de analytics do canal.
- **Nossa proposta:** ganhos e perdas por formato no Analytics; inferir atributos protegidos é vetado pela [política](https://developers.google.com/youtube/terms/derived-metrics-policy).
- **Limite de API:** OAuth.
- **Google:** OAuth do canal.
- **Estado:** parcial.

## Best Time to Post

- **Problema:** escolher quando publicar.
- **Interação:** não documentada nas páginas lidas.
- **Dados:** não documentados.
- **Apresenta:** não documentado.
- **Comprovado:** **não encontrei documentação oficial.** A auditoria de canal acompanha a agenda de publicações, segundo o blog.
- **Inferência:** o recurso pode existir ou ter sido renomeado; não confirmei.
- **Nossa proposta:** dia da semana mais usado pelos concorrentes, rotulado como hábito observado, não como melhor horário.
- **Limite de API:** a lista de relatórios lida não traz dimensão por hora, só `day` e `month`. Sem isso, não há como calcular melhor hora com dado medido.
- **Google:** sim, é contagem derivada.
- **Estado:** parcial, sem hora.

## Histórico e organização

- **Problema:** não perder pesquisas.
- **Interação:** aba Saved e exportação em CSV no vidIQ; lista de conversas no Coach.
- **Dados:** pesquisas da conta.
- **Apresenta:** itens salvos.
- **Comprovado:** salvar e exportar palavras na web ([Keywords](https://support.vidiq.com/en/articles/9421214-keywords-research)). O artigo não descreve histórico separado.
- **Inferência:** nenhuma adicional.
- **Nossa proposta:** histórico automático, salvar com nome, comparar duas pesquisas, exportar CSV, associar a canais, favoritos.
- **Limite de API:** títulos da API não ficam copiados: a pesquisa guarda IDs e, sem atualização em 30 dias, o texto sai pela rotina de retenção.
- **Google:** não.
- **Estado:** feito.

## O que não copiamos, de propósito

- Previsão de views, volume mensal inventado e nota que prometa CTR.
- Publicação, edição de vídeos e envio de thumbnails ao YouTube.
- Scraping, autocomplete não oficial, `ytInitialData` ou fontes intermediárias.
- Instagram, TikTok, estimativa de ganhos, geração de vídeo, voz ou imagens. Ficam fora desta fase.
- Marca, cores, faixas e interface do vidIQ.

## Fontes

- [vidIQ: Agent Skills](https://vidiq.com/agent-skills/)
- [vidIQ: extensão](https://support.vidiq.com/en/articles/9868197-vidiq-extension-overview)
- [vidIQ: Keywords Research](https://support.vidiq.com/en/articles/9421214-keywords-research)
- [vidIQ: Outliers](https://support.vidiq.com/en/articles/9660010-outliers)
- [vidIQ: AI Coach](https://support.vidiq.com/en/articles/8017871-ai-coach)
- [vidIQ: Daily Ideas](https://vidiq.com/features/daily-ideas/)
- [vidIQ: Competitors](https://vidiq.com/features/competitors/)
- [vidIQ: Trend Alerts](https://vidiq.com/features/trend-alerts/)
- [vidIQ: guia de auditoria](https://vidiq.com/blog/post/youtube-channel-audit/)
- [YouTube Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy)
- [YouTube Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [YouTube Analytics: relatórios de canal](https://developers.google.com/youtube/analytics/channel_reports)
