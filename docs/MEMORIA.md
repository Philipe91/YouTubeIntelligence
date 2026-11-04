# Consumo de memória

Medido em 03/11/2026 com Windows 11, 16 GB de RAM e os dados de demonstração. Conjunto de trabalho somando os processos filhos.

| Componente | Situação | RAM |
|---|---|---|
| API (Python) | Recém-ligada | 77 MB |
| API (Python) | Depois de 28 páginas | 80 MB |
| Interface (`next start`) | Recém-ligada | 138 MB |
| Interface (`next start`) | Depois de 28 páginas | 191 MB |
| Servidor MCP, Python direto (`.mcp.json` atual) | Só com o Claude Code aberto na pasta | 69 MB |
| Servidor MCP com `uv run` (antes) | | 108 MB, 3 processos |
| **Painel ligado** | API + interface | **cerca de 270 MB** |
| **Tudo ligado** | Com o MCP | **cerca de 340 MB** |
| **Desligado** | | **0 MB** |

O próprio Claude Code usa cerca de 450 MB por sessão, à parte desses números.

## Como iniciar gastando pouco

| Componente | Como | Observação |
|---|---|---|
| Backend e frontend | `scripts\iniciar.ps1` | Sem `uv run` nem `npm run`, para evitar processos intermediários e órfãos |
| Desligar | `scripts\parar.ps1` | Encerra os processos filhos também |
| MCP | Nada a fazer | O Claude Code liga e desliga, conforme `.mcp.json` |
| Coleta periódica | Agendador de Tarefas, só no modo real | Não precisa de processo ligado |

**Só o que precisar:** para o agente trabalhar, o painel é dispensável. O MCP grava direto no banco, e o painel mostra tudo quando você o abrir.

**Atualização da tela:** só com a aba visível, a cada 3 s com tarefa ativa e a cada 20 s no resto. Aba em segundo plano não consulta nada.

**Picos a evitar com a máquina cheia:** `npm run build` e `tsc` usam bem mais memória que o app em uso. Rode-os com o jogo fechado.

## Alternativas avaliadas

| Alternativa | Resultado | Decisão |
|---|---|---|
| Ligar e desligar sob demanda | Libera tudo | **Adotada** |
| Python direto no MCP | 39 MB a menos | **Adotada** |
| Evitar `uv run` e `npm run` no painel | Evita órfãos: encerrar o `npm` deixou um `node` de 110 MB vivo no MVP | **Adotada** |
| Build `standalone` do Next.js | 7 MB a menos | Rejeitada: pouco ganho, mais passos |
| `--max-old-space-size=128` | 2 MB a menos | Rejeitada |
| Trocar o Next.js por páginas servidas pela API | Eliminaria o Node (estimativa: cerca de 190 MB a menos) | **Não feita:** exige reescrever a interface |

O encerramento anterior por falta de memória não veio do app: a máquina estava com 0,8 GB livres, com `acs` (Assetto Corsa) em cerca de 4,3 GB, além de navegador, Steam, Discord e sessões do Claude.
