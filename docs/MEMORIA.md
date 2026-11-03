# Consumo de memória

Medido em 03/11/2026 com Windows 11, 16 GB de RAM e os dados de demonstração. Conjunto de trabalho somando os processos filhos. Para repetir a medição da API: `scripts\medir_memoria.ps1`.

| Processo | Situação | RAM |
|---|---|---|
| API (Python) | Recém-ligada | 69 MB |
| API (Python) | Depois de consultas | 76 MB |
| Interface (`next start`) | Recém-ligada | 135 MB |
| Interface (`next start`) | Depois de 18 páginas | 186 MB |
| Servidor MCP | Carregado, só com o Claude Code aberto na pasta | 64 MB |
| **Total em uso** | API + interface | **cerca de 260 MB** |
| **Total desligado** | | **0 MB** |

## Conclusões

O aplicativo não foi a causa da falta de memória que encerrou os servidores: naquele momento a máquina tinha 0,8 GB livres, com `acs` (Assetto Corsa) em cerca de 4,3 GB, além de navegador, Steam, Discord e sessões do Claude.

**Picos a evitar com a máquina cheia:** `npm run build` e `tsc` usam bem mais memória que o aplicativo em uso. Rode-os com o jogo fechado.

## Alternativas avaliadas

| Alternativa | Resultado | Decisão |
|---|---|---|
| Ligar e desligar sob demanda | Libera tudo, cerca de 260 MB | **Adotada:** `scripts\iniciar.ps1` e `scripts\parar.ps1` |
| Evitar `uv run` e `npm run` | Tira processos intermediários e evita órfãos: encerrar o `npm` deixou um `node` de 110 MB vivo no MVP | **Adotada** nos scripts |
| MCP sob demanda | Sem custo com o Claude Code fechado | **Adotada** |
| Coleta periódica | Só existe no modo real, pelo Agendador de Tarefas: não precisa de processo ligado | **Adotada** |
| Build `standalone` do Next.js | 179 MB contra 186 MB: 7 MB a menos | Rejeitada: pouco ganho, mais passos |
| `--max-old-space-size=128` | 184 MB contra 186 MB | Rejeitada: sem ganho real |
| Trocar o Next.js por páginas servidas pela API | Eliminaria o Node (estimativa: cerca de 180 MB a menos) | **Não feita:** exige reescrever a interface |

Evite `npm run dev` no dia a dia: o modo de desenvolvimento costuma consumir bem mais que o build de produção. Essa afirmação não foi medida aqui.
