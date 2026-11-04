# Política de dados do YouTube

Releitura feita em 04/11/2026 das páginas oficiais, por um resumidor automático com citações curtas. Não é parecer jurídico: confira o texto original antes de decidir. Este documento complementa `docs/CONFORMIDADE.md`.

Fontes: [Developer Policies](https://developers.google.com/youtube/terms/developer-policies), [Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy), [histórico de revisões](https://developers.google.com/youtube/terms/revision-history), [diretrizes de marca](https://developers.google.com/youtube/terms/branding-guidelines) e [tabela de custos](https://developers.google.com/youtube/v3/determine_quota_cost).

**O que mudou desde a última leitura:** nada que afrouxe o bloqueio. As entradas mais recentes do histórico são de 04/05/2026 e 01/06/2026, e são as que criaram as regras de métricas derivadas já aplicadas aqui. **Achados novos** estão na seção Decisões do dono.

## 1. Uso autorizado de dados públicos

Com a chave de API, o aplicativo lê dados públicos, sem login de ninguém (Non-Authorized Data).

| Pode | Como o aplicativo faz |
|---|---|
| Mostrar título, canal, data, views e inscritos públicos | Telas de pesquisa e descoberta, com o dado cru |
| Filtrar por um número público | Canais pequenos: filtro por inscritos, sem nota. **Sem aprovação, mantém a ordem da busca** |
| Guardar por pouco tempo, para uso imediato | Até 30 dias. Veja a seção 3 |
| Salvar vídeos, canais e temas de interesse | Só o ID. O texto continua sujeito à retenção |
| Deixar o YouTube ordenar | `order=viewCount` é a ordem do próprio YouTube, não um ranking calculado aqui |

Toda linha traz o link para o original (III.F.2.a) e a data da medição (III.E.4.f).

**Proibido, e não feito:** scraping (III.E.6), obter dados da API por outra tecnologia (III.I.14), baixar ou guardar vídeos (III.E.1), escrever no YouTube.

## 2. Métricas derivadas condicionais

A III.E.4.h proíbe criar métricas a partir de dados da API. A III.L abre uma exceção só para **desenvolvedores auditados, com uso analítico, que pediram permissão explicitamente**, a partir de 01/06/2026.

**Enquanto não houver aprovação comprovada, ficam bloqueados no servidor,** sem calcular o valor:

- VPH, IDR, outliers, aceleração e tendências.
- Índice de palavras, relacionados por contagem de títulos e assuntos em ascensão.
- Comparações, cadência e padrões entre canais.
- Rankings calculados, incluindo ordenar canais por inscritos.
- Contagens sobre os resultados da API.

**O aplicativo não confirma a aprovação com o Google:** `backend/config/compliance.toml` é uma declaração sua. Só preencha depois da resposta do Google.

**Corrigido nesta revisão:**

- O Coach recomendava "o concorrente com a publicação mais frequente" mesmo sem aprovação, o que é uma comparação derivada. Agora isso só existe com a aprovação.
- A busca de canais pequenos ordenava pelo número de inscritos no modo real. Agora mantém a ordem da busca.

**Se a aprovação vier,** as regras incluem: distinguir métricas próprias das da API, não apresentar comparação como rivalidade ou "guerra", não inferir atributos protegidos e rotular estimativas financeiras como de terceiros.

## 3. Retenção e atualização dos dados

| Dado | Prazo sem aprovação | Com aprovação de armazenamento | No aplicativo |
|---|---|---|---|
| Estatísticas: views, curtidas, inscritos, comentários | 30 dias (III.E.4.b) | Até 36 meses | Apagadas no prazo |
| Título, nome, descrição | Atualizar ou apagar em 30 dias (III.E.4.d) | Igual | Apagados se não atualizados |
| Total aproximado de resultados | 30 dias, como estatística | Até 36 meses | O número sai, e a pesquisa fica |
| Resposta bruta no cache | Prazo curto: de 15 minutos a 6 horas | Igual | Apagada ao vencer |
| Conversas do Coach, que podem citar títulos | 30 dias | Igual | Apagadas no prazo |
| Histórico do agendador | 30 dias | Igual | Apagado no prazo |
| O que é seu: pesquisas digitadas, notas, temas, perfil | Sem prazo da API | Igual | Fica até você apagar |

- **A retenção não depende do agendador.** Antes, só rodava com o coletor ligado, e sem ele os dados poderiam passar do prazo. Agora roda ao abrir o banco real, no máximo uma vez por dia.
- **Item salvo cujo texto venceu** aparece como removido. Título da API nunca entra no banco do estúdio: para virar ideia, um vídeo salvo pede o assunto com as suas palavras.
- **Dado antigo mostra a data.** A III.E.4.f pede o dado mais atual disponível, e permite o histórico quando apresentado com o contexto de tempo.
- **Cache não é medição.** Resposta do cache mantém a data da busca original, para não criar medições falsas.

## 4. Acesso privado via OAuth

Vale só para os seus canais, com a sua autorização (Authorized Data). **Nunca testado com uma conta real.**

| Regra | Fonte | No aplicativo |
|---|---|---|
| Só quem autorizou vê os dados | III.E.3.b | Aplicativo local, de um operador |
| Identificar o canal do pedido | III.E.3.e | Canal próprio cadastrado por ID ou @nome |
| Conferir a autorização a cada 30 dias | III.E.4.b | Reconfere ao sincronizar. Autorização perdida apaga os dados do canal |
| Revogar pelo aplicativo: revogar o token na hora e apagar em até 7 dias | III.D.2.3.a | `python -m app.cli revoke-channel`, que revoga e apaga na hora |
| Revogado pelo Google: apagar em até 30 dias | III.D.2.3.b | Detectado ao sincronizar, com o erro `invalid_grant` |
| Pedido de exclusão: em até 7 dias | III.E.4.g | Veja abaixo |
| Só leitura | III.E.3.d | Escopos de leitura. Métodos de escrita são recusados no código |

O token fica no cofre do sistema, nunca no banco nem no Git.

**Para apagar os seus dados:** para um canal, `python -m app.cli delete-channel-data <id>`. Para todos os dados reais, desligue o aplicativo e apague `data/live.sqlite`. Isso não apaga nada no YouTube.

## 5. Limitações de provedores externos de volume de busca

**O YouTube não informa volume de busca em nenhuma API pública.** O aplicativo mostra "indisponível", nunca um número inventado. Existe um ponto de ligação (`VolumeProvider`), sem provedor contratado.

Antes de contratar um provedor, confira:

- **De onde vem o número.** Uma estimativa obtida por scraping do YouTube não contorna a III.E.6: usar esse dado pode expor o projeto. Exija do fornecedor uma resposta por escrito.
- **É estimativa, não medida.** Precisa de rótulo próprio e não pode parecer dado do YouTube (III.E.4.h e III.F.2.b).
- **Não misture com dados da API para calcular.** Somar a estimativa a views ou inscritos para criar um índice é uma métrica derivada, e segue bloqueada sem aprovação.
- **Custo e termos.** É um serviço pago, a contratar só com a sua autorização. Autocomplete não oficial fica de fora, pelo mesmo motivo do scraping.

## 6. Decisões do dono

### Nome do aplicativo
As [diretrizes de marca](https://developers.google.com/youtube/terms/branding-guidelines) dizem que **nunca se deve usar o nome YouTube, nem abreviações como YT, no nome geral do aplicativo**, citando "YouTube for Kids" como exemplo proibido. **"YouTube Intelligence" parece se enquadrar nisso,** assim como `yti-producao`, o que pesa num pedido de auditoria. O nome não foi alterado: renomear envolve o repositório no GitHub, e a escolha é sua. Dá para resolver antes do pedido ao Google.

### Uso privado
A política **não traz exceção para clientes privados ou internos**. A definição de API Client alcança qualquer software que você desenvolva. As obrigações da III.A, de exibir os termos e exigir o aceite de uma política de privacidade, valem sem distinção:

- **Feito:** a página **Dados e privacidade**, com os links exigidos, o aviso e a origem de cada dado.
- **Não feito:** a tela de aceite antes do primeiro uso. Faz pouco sentido para um único operador, mas a política não prevê isso. Vale perguntar ao Google junto com o pedido de auditoria.

### Pedido de auditoria
Continua em aberto se a exceção da III.L alcança um uso privado de um único operador. A página de métricas derivadas não fala nisso.

### Um projeto por cliente
A III.D.1.c exige exatamente um projeto de API por cliente. Não crie projetos extras para somar cota.

## 7. Pesquisas agendadas

- **Desligadas com dados reais até você aprovar.** A aprovação exige a chave e uma consulta real confirmada. O agente não consegue aprovar.
- **Nada roda sozinho.** Uma rodada só acontece pelo botão **Rodar as vencidas agora** ou pelo comando abaixo, iniciado à mão:

  ```powershell
  cd backend
  uv run python -m app.cli research-tick
  uv run python -m app.cli research-tick --loop-seconds 3600
  ```

- **Limites:** o que você aprovar, de 1 a 20 buscas por dia; até 5 por rodada; até 10 agendamentos por canal; periodicidade mínima de um dia.
- **Evita gasto à toa:** a mesma pesquisa feita há menos de 6 horas é ignorada, e o que vem do cache não consome o limite aprovado.
- **Pausa sozinho:** falta de cota pausa tudo até a virada do dia de cota. Problema na chave pausa até você retomar. Três falhas seguidas pausam só aquele agendamento.
