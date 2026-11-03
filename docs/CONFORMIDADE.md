# Auditoria de conformidade

Releitura feita em 03/11/2026 das páginas oficiais. Este documento não é parecer jurídico. As páginas foram lidas por um resumidor automático com citações curtas: confira o texto original antes de decidir.

## Correção ao relatório do MVP

O MVP tratava a exceção de métricas derivadas como um aceite de formulário, liberado por uma variável de ambiente. **Isso estava fraco.** A seção III.L limita a exceção a desenvolvedores **auditados**, com uso analítico, **explicitamente aprovados** pelo pedido padrão de extensão de cota, e a III.D.5 liga a extensão de cota a uma API Compliance Audit. A página de métricas derivadas fala em aceitar a emenda e não descreve o processo de auditoria, então as duas páginas devem ser lidas juntas.

## O que vale hoje

| Tema | Regra | Fonte | No sistema |
|---|---|---|---|
| Métricas derivadas | Proibidas sem a exceção | [III.E.4.h](https://developers.google.com/youtube/terms/developer-policies) | Bloqueadas com dados reais |
| Exceção | Auditado, uso analítico, aprovado explicitamente | III.L, III.D.5 | Registro em `config/compliance.toml` |
| Permitido com a exceção | Scores próprios, rankings e comparações, distintos dos dados da API | [Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy) | Rótulo "calculado", aviso de origem |
| Estatísticas sem autorização do dono | Até 30 dias | III.E.4.b | Apagadas após 30 dias |
| Estatísticas com a exceção | Até 36 meses | Derived Metrics Policy | Só com o escopo `extended_storage` |
| Títulos, nomes, descrições | Atualizar ou apagar em 30 dias, mesmo com a exceção | III.E.4, Derived Metrics Policy | Apagados se não atualizados |
| Agregação | Só canais do mesmo dono | III.E.2 | Comparação bloqueada sem a exceção |
| Projeto de API | Um projeto por cliente | III.D.1.c, III.D.3 | Documentado: não crie vários para somar cota |
| Auditorias | O YouTube pode auditar e pedir contas de teste | III.H | Sem ação no aplicativo |

**Em aberto:** a política não diz se a exceção alcança um uso privado de um único operador, nem como se concilia com a III.E.2. Uma resposta só o Google pode dar.

## Configuração de conformidade

`backend/config/compliance.toml` é a única forma de liberar métricas com dados reais.

- A variável `YTI_DERIVED_METRICS_APPROVAL_REF` **não autoriza mais nada**. Se estiver preenchida, a tela Sistema avisa que foi ignorada.
- Para liberar, tudo precisa estar presente: `status = "approved"`, `use_case = "analytics_reporting"`, emenda aceita, auditoria aprovada, referência do caso, quem declarou, data de aprovação não futura, data de revisão não vencida e o escopo `derived_metrics`.
- Os 36 meses dependem de um escopo separado, `extended_storage`.
- Arquivo ausente, inválido ou vencido mantém tudo bloqueado.
- Só preencha depois da resposta do Google. **O aplicativo não consegue confirmar a aprovação:** o arquivo é uma declaração sua.

## Cotas

`backend/config/quota.toml` define baldes, custos e limites. Sobrescreva com `YTI_QUOTA_<BALDE>_DAILY`. O limite local nunca passa do limite do Google configurado.

| Balde | Limite do Google | Local | Situação |
|---|---|---|---|
| `default` | 10.000 unidades/dia | 9.000 | Confirmado |
| `search` | 100 chamadas/dia | 90 | Confirmado |
| `batch_stats` | 10.000 unidades/dia | 0 | Só no histórico de revisões, ausente da tabela de custos. Sem uso |
| `analytics` | Não informado | 200 | Consulte o Console do Google Cloud |

Método sem custo configurado falha antes da chamada. `videos.insert`, `videos.update`, `videos.delete` e `thumbnails.set` são recusados com erro. A página Getting Started não menciona baldes nem a hora da virada; esses dados vêm da página de custos e do histórico de revisões.

## Classificação de Shorts

Segundo a [ajuda do YouTube](https://support.google.com/youtube/answer/15424877), Short é um vídeo **quadrado ou vertical de até 3 minutos**, enviado desde **15/10/2024** (08/12/2025 para canais oficiais de artista). Envios anteriores acima de 1 minuto seguem longos, e 16:9 fica longo.

| Regra | Situação |
|---|---|
| Até 180 s desde 15/10/2024 | Implementada |
| Antes dessa data, até 60 s | Implementada |
| Proporção | **Não verificada:** a Data API não informa diretamente. Vídeo 16:9 curto pode ser contado como Short, e o rótulo segue "estimado" |
| Data de artistas oficiais | **Não implementada:** não há como identificar esses canais pela regra atual |

## Dados do estúdio

`data/studio.sqlite` guarda seus cadastros e não guarda texto retornado pela API. As fontes de recomendação citam só a sua consulta e um link interno. Views no histórico são digitadas por você e rotuladas assim.
