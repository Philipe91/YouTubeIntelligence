# Relatório do ciclo completo

Situação em 03/11/2026. Branch `multicanal`. Evidências em `docs/evidencias/`.

**O que está provado:** o ciclo de automação funciona de ponta a ponta com **produção simulada e dados fictícios**.

**O que não está pronto:** a automação de produção real. Nenhum vídeo é gerado, e nenhum pipeline real está ligado.

## Como repetir

Com o frontend compilado e uma pasta vazia, fora de `data/`:

```powershell
uv run --directory backend --with playwright python ../scripts/teste_ciclo_completo.py --dados C:\temp\ciclo --saida ../docs/evidencias
```

Sobe o app em portas próprias e encerra tudo no fim. Se um passo falha, o script para com erro. Dura cerca de 3 minutos e requer o Microsoft Edge.

## Passos verificados

Navegador real no painel e servidor MCP real em subprocesso. Resultado em `docs/evidencias/ciclo_completo.json`.

| # | Passo | Verificação |
|---|---|---|
| 1 | Selecionar canal | Clique no painel |
| 2 | Criar recomendação | Formulário grava e aparece como próximo vídeo |
| 3 | Gerar três títulos | 3 opções, mais "Outro" |
| 4 | Escolher título e aprovar | Briefing estruturado gravado |
| 5 | Disponibilizar | `list_available_tasks` vazio antes e com a tarefa depois |
| 6 | Agente assume | Painel mostra o agente sozinho. Mesma chave devolve a mesma resposta; segundo agente recebe `job_not_claimable` |
| 7 | Falha | Alerta aparece sozinho, "Marcar como visto" funciona, tentativa 2 assume |
| 8 | **Queda real** | `taskkill` no servidor MCP e desligamento do app no meio da tarefa. Banco segue com `running`, 40%, tentativa 2 |
| 9 | **Recuperação** | Prazo vence, tarefa volta à fila, outro agente assume. Token antigo recebe `lease_lost` |
| 10 | Produção simulada | Arquivo real de texto, com SHA-256. Entrega de arquivo fora da pasta da tarefa é recusada |
| 11 | Final | `PRONTO PARA REVISÃO`, `published: false` |
| 12 | Arquivo pelo painel | Download com o mesmo SHA-256 |
| 13 | **Reinício** | Estado, histórico, arquivo e calendário iguais. Repetir a chamada do pacote devolve `replayed: true` |
| 14 | Isolamento | Outro canal não vê tarefa nem arquivo: API 404, MCP recusa, tela sem o conteúdo |
| 15 | Sem publicação | Sem ferramenta nem botão. Zero chamadas à API do YouTube no registro de cota |
| 16 | Botões | Cada botão clicado com efeito conferido |
| 17 | Responsividade | Sem estouro em 390 e 768 px |

Histórico de execuções registrado depois da queda:

| Tentativa | Agente | Resultado |
|---|---|---|
| 1 | agente-teste-A | Falhou (informada) |
| 2 | agente-teste-A | Agente parou de responder (morto) |
| 3 | agente-teste-B | Entregue |

## Claude Code real

`docs/evidencias/claude_code_real.txt`: o Claude Code, pelo `.mcp.json`, listou a tarefa, assumiu, avançou 5 etapas, gerou o arquivo, entregou e montou o pacote. A conferência direta no banco bate com o relato dele.

Limites: uma execução, modelo Haiku, um caminho feliz, seguindo uma lista de passos que eu escrevi. O agente não produziu conteúdo: só operou o contrato. Queda e recuperação foram testadas com o agente automatizado, não com o Claude.

## O que estes testes não provam

- Nada sobre a qualidade de um vídeo.
- Nada sobre pipelines reais, lentos ou com falhas parciais.
- Nada sobre a API do YouTube: `INDETERMINADO` e o uso do player foram testados só com respostas simuladas.
- **Botões sem clique no teste de navegador:** "Tentar de novo" e "Aprovar briefing de novo". As ações deles estão cobertas nos testes automáticos do backend. "Autorizar produção" só aparece em tarefa real, que a interface não cria.

## Defeitos que os testes encontraram

| Defeito | Como apareceu |
|---|---|
| `prepare_publish_package` não devolvia o estado da tarefa | Claude real relatou estado antigo |
| Reaprovar briefing com data duplicaria o item no calendário | Inspeção da tela |
| `uv run` no MCP custava 39 MB a mais | Medição |

Corrigidos e cobertos por testes.
