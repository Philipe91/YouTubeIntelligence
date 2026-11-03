# Pendências

Situação em 03/11/2026.

## Depende de você

| Item | Motivo |
|---|---|
| Decidir sobre o pedido ao Google (uso analítico) | Sem o aceite, scores e VPH ficam bloqueados com dados reais |
| Chave da YouTube Data API | Nenhuma coleta real foi feita |
| Cliente OAuth e autorização dos seus canais | Analytics real não foi testado |
| Plano ou chave para IA, se quiser além do teste feito | `claude_cli` foi testado uma vez com dados fictícios; `anthropic` só com mock |

## Não validado com serviços reais

Tudo abaixo passou em testes com mocks e nunca falou com o serviço verdadeiro:

- YouTube Data API: formato real das respostas, comportamento de cota e `forHandle`.
- Fluxo OAuth no navegador, incluindo o `keyring`. A função `run_browser_flow` não tem teste automatizado.
- YouTube Analytics: a combinação `day,creatorContentType` com essas métricas segue a documentação, mas o Google pode recusá-la.
- `AnthropicProvider`: chamada real, incluindo o parâmetro `fallbacks`.

## Não implementado

| Item | Situação |
|---|---|
| Classificação de Short por vídeo via Analytics | Só existe por duração. Vídeo comum de até 180 s é contado como Short, inclusive nos seus canais |
| Alertas por e-mail (Trend Alerts) | Só há painel |
| Chat estilo AI Coach | Só há geração estruturada |
| Comentários e transcrições | Sem conector; o tratamento como dados não confiáveis cobre hoje títulos e descrições |
| Curva de retenção | Só a porcentagem média |
| vidIQ MCP | Só interface desligada, sem chamadas |
| `videos.batchGetStats` | Não usado; a documentação não informa o máximo de IDs |
| Plugin vidIQ para Claude Code | Citado pela página oficial; não encontrei instruções nem repositório |
| Cadastro de canal e busca pela interface | Só pela linha de comando |
| Agendamento no Windows | Documentado; a tarefa não foi criada |
| Repositório git | Não inicializado; há `.gitignore` pronto |

## Limitações conhecidas

- **Pontos em aberto da política:** não está claro se a exceção cobre um uso privado de um único operador, nem como ela se concilia com a proibição de agregar dados de donos diferentes (III.E.2). Vale perguntar no pedido ao Google. Este projeto não é parecer jurídico.
- **Totais de canais próprios no modo restrito:** somas e média ponderada por dia continuam visíveis. A agregação do mesmo dono é permitida, mas a média ponderada pode ser lida como métrica derivada.
- **Primeiros dias:** IDR por idade depende de snapshots acumulados. No início, muitos vídeos terão amostra insuficiente ou comparação só por faixa de idade.
- **Limite de 30 dias:** sem aprovação, o histórico de terceiros não passa de 30 dias.
- **Tendências por palavras:** contagem de termos em títulos, sem semântica. Pode trazer termos genéricos.
- **Relevância por palavras:** o demo mostra relevância 100 em muitos temas porque o vocabulário do nicho é pequeno e combina com as buscas.
- **Pesos do ranking:** escolhidos por julgamento, sem calibração com resultados reais.
- **API local sem login:** protegida só por escutar em 127.0.0.1. Qualquer programa da sua máquina pode acessá-la.
- **Atribuição:** o rodapé cita o YouTube em texto. A política pede o uso das marcas do YouTube em páginas com conteúdo dele, o que não foi implementado.
