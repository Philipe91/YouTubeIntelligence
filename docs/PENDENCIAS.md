# Pendências

Situação em 03/11/2026.

## Depende de você

| Item | Motivo |
|---|---|
| Decidir sobre o pedido ao Google (extensão de cota e auditoria) | Sem aprovação, scores e VPH ficam bloqueados com dados reais. Veja `docs/CONFORMIDADE.md` |
| Chave da YouTube Data API | Nenhuma coleta real foi feita |
| Cliente OAuth e autorização dos seus canais | Analytics e status de autenticação nunca rodaram com conta real |
| Cadastrar seus canais reais | A central já aceita |
| Dizer como ligar o pipeline real de produção | O contrato está pronto; a conexão com o Brother Quill não foi feita, para não alterar aquele projeto |

## Não validado com serviços reais

Tudo abaixo passou em testes com mocks e nunca falou com o serviço verdadeiro:

- YouTube Data API: formato real das respostas, comportamento de cota e `forHandle`.
- Fluxo OAuth no navegador, incluindo o `keyring`. A função `run_browser_flow` não tem teste automatizado.
- YouTube Analytics: a combinação `day,creatorContentType` com essas métricas segue a documentação, mas o Google pode recusá-la.
- `AnthropicProvider`: chamada real, incluindo o parâmetro `fallbacks`.
- Fluxo completo de produção com o Claude Code: o real só executou leituras. As gravações foram testadas com cliente MCP automatizado.

## Não implementado

| Item | Situação |
|---|---|
| Publicação | Fora do escopo, de propósito |
| Pipeline real de produção | Só simulação; tarefa real existe no contrato, mas a interface só cria simuladas |
| Escrita de recomendações pelo aplicativo com IA | Rascunhos por regras. Para texto escrito, use o Claude Code com `submit_recommendation` |
| Arrastar itens no calendário | Altere a data no formulário |
| Importar histórico do YouTube | Histórico é digitado por você |
| Vincular concorrente à coleta | Guarda só a referência; coleta segue pelo `add-channel` |
| Verificar proporção do vídeo | A classificação de Short usa duração e data de envio. Vídeo 16:9 curto pode ser contado como Short |
| Regra de 08/12/2025 para artistas oficiais | Não implementada |
| Classificação de Short por vídeo via Analytics | Só há totais por tipo |
| Alertas por e-mail | Só há painel |
| Chat estilo AI Coach | Só há geração estruturada |
| Comentários e transcrições | Sem conector |
| Curva de retenção | Só a porcentagem média |
| vidIQ MCP | Só interface desligada, sem chamadas |
| `videos.batchGetStats` | Sem uso; limite local zerado |
| Plugin vidIQ para Claude Code | Citado pela página oficial; não encontrei instruções nem repositório |
| Agendamento no Windows | Documentado; a tarefa não foi criada |

## Limitações conhecidas

- **Autorização não é barreira de segurança:** a API local não tem login. Um programa na sua máquina, ou um agente com acesso ao terminal, pode chamar `authorize` ou editar `compliance.toml`.
- **Aprovação não verificável:** o aplicativo não confirma nada com o Google.
- **Recomendação com métrica aprovada:** a justificativa guarda a pontuação em texto. Se a aprovação for revogada, não há rotina que apague essas recomendações.
- **Pontos em aberto da política:** não está claro se a exceção cobre um uso privado de um único operador, nem como ela se concilia com a proibição de agregar dados de donos diferentes (III.E.2). Este projeto não é parecer jurídico.
- **Totais de canais próprios no modo restrito:** somas e média ponderada por dia continuam visíveis. A agregação do mesmo dono é permitida, mas a média ponderada pode ser lida como métrica derivada.
- **Primeiros dias:** IDR por idade depende de snapshots acumulados. No início, muitos vídeos terão amostra insuficiente.
- **Limite de 30 dias:** sem aprovação, o histórico de terceiros não passa de 30 dias.
- **Tendências e relevância por palavras:** contagem de termos, sem semântica.
- **Prioridade editorial por regras:** primeira ideia do backlog é alta, palavras do perfil são baixa. Não mede potencial.
- **Pesos do ranking:** escolhidos por julgamento, sem calibração com resultados reais.
- **Atribuição:** o rodapé cita o YouTube em texto. A política pede o uso das marcas do YouTube em páginas com conteúdo dele, o que não foi implementado.
