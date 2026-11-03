# Relatório da versão multicanal

Situação em 03/11/2026. Branch `multicanal`; o MVP está preservado em `main`, commit `5912ed5`. Capturas em `docs/telas/`.

## O que funciona de verdade

| Pedido | Situação | Evidência |
|---|---|---|
| Git e checkpoint | Feito | Commit em `main`, sem dados nem segredos |
| Medição de RAM | Feita | `docs/MEMORIA.md` |
| Auditoria de conformidade | Feita | `docs/CONFORMIDADE.md` |
| Configuração explícita de conformidade | Feita | Variável antiga ignorada, testada em API e navegador |
| Cotas por balde, configuráveis | Feito | `config/quota.toml`, testes |
| Visão geral, cadastro, remoção, página do canal | Feito | Fluxo no navegador |
| Nicho, idioma, público e contexto por canal | Feito | Fluxo no navegador |
| Concorrentes, histórico, calendário | Feito | Fluxo no navegador |
| Fila de produção | Feita, **simulada** | Autorização, falha, retomada e pacote no navegador |
| Controles de automação por canal | Feito | O contrato recusa o que estiver desligado |
| Status de autenticação do YouTube | Feito, só leitura | Testado com banco simulado; nunca com OAuth real |
| Status do Claude Code | Feito | Sinais locais: comando, `.mcp.json`, último contato |
| Contrato do agente | Feito | 14 ferramentas MCP, `docs/CONTRATO_AGENTE.md` |
| Recomendações por canal | Feito, **texto por regras** | Todos os campos pedidos |
| Funciona sem chave de API | Sim | Toda a verificação rodou sem credenciais |

## Como foi testado

| Teste | Resultado | Limite |
|---|---|---|
| Testes automáticos do backend | 225 passando | Só com APIs simuladas |
| Os 115 testes do MVP | Todos preservados | Em `test_integration.py`, 4 linhas e 1 importação mudaram para usar o novo registro de conformidade; `conftest.py` ganhou esse registro de teste |
| Navegador (Edge), fluxo completo | Aprovado, sem erro de console | Pasta de dados de teste |
| Responsividade | Sem estouro horizontal em 390 e 768 px | 12 telas |
| Modo real sem credenciais | Travas confirmadas na interface | Sem nenhuma chamada ao YouTube |
| Cliente MCP, contrato completo | Aprovado | O agente é um teste automatizado, não o Claude |
| **Claude Code real**, via `.mcp.json` | Listou canais e leu um briefing | **Só leitura**, dados fictícios, modelo Haiku, uma execução |

Defeitos que só apareceram no navegador e foram corrigidos: formulário apagado depois de erro de validação, estouro em telas estreitas, texto citando pontuação em canal sem pontuação, títulos com gramática ruim.

## O que não é real ainda

- **Pipeline de produção:** nenhum vídeo é gerado. As tarefas simuladas não renderizam nem criam arquivos, e o contrato não está ligado ao pipeline do Brother Quill.
- **Publicação:** não existe, de propósito.
- **Claude escrevendo recomendações:** a ferramenta `submit_recommendation` foi testada só com o cliente automatizado. Os rascunhos que aparecem na tela vêm de regras, sem IA.
- **REA:** não participa. Ele é uma ferramenta de engenharia reversa e não tem recursos de orquestração.
- **YouTube:** nenhuma chamada real foi feita em nenhum momento.

Pendências completas em `docs/PENDENCIAS.md`.
