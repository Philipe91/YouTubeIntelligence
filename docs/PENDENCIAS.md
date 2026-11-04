# Pendências

Situação em 04/11/2026. Para o primeiro canal real, veja `docs/PRIMEIRO_CANAL_REAL.md`.

## Depende de você

| Item | Motivo |
|---|---|
| Revisar o vídeo `job_0b0b4cd15f0b4e4f` | No painel do Brother Quill. Nada foi publicado |
| Autorizar a correção do céu no projeto original | Hoje vale só na cópia de cada tarefa. Veja `docs/INTEGRACAO_BROTHER_QUILL.md` |
| Cadastrar seus canais reais | A central já aceita |
| Decidir sobre o pedido ao Google | Sem aprovação, scores e VPH ficam bloqueados com dados reais. Veja `docs/CONFORMIDADE.md` |
| Chave da YouTube Data API e cliente OAuth | Opcionais para produzir; necessários para dados reais |

## Não validado com serviços reais

Passou em testes com mocks e nunca falou com o serviço verdadeiro:

- YouTube Data API: formato das respostas, cota, `forHandle` e **o uso do tamanho do player para separar Shorts**.
- Fluxo OAuth no navegador, incluindo o `keyring`. `run_browser_flow` não tem teste automatizado.
- YouTube Analytics: a combinação `day,creatorContentType` pode ser recusada pelo Google.
- `AnthropicProvider` e `AnthropicCoach`: chamada real, incluindo `fallbacks`.
- Busca de canais (`search_channels`), concorrentes e pesquisas no modo real: só com YouTube falso.
- Termos de descoberta (`insightTrafficSourceDetail` com `YT_SEARCH`): só com mock.
- Coach com `claude_cli`: uma pergunta real, sobre dados fictícios.

## Não implementado

| Item | Situação |
|---|---|
| Vídeo publicável | O caminho técnico funciona, mas faltam cenas sob medida, voz do canal e revisor visual. Veja `docs/INTEGRACAO_BROTHER_QUILL.md` |
| Produção real em outros perfis | `viral_replicator` e `money_printer` só descrevem |
| Vídeo acima de 20 s | Limite de segurança em `execucao.toml`, ainda não testado acima disso |
| Publicação | Fora do escopo, de propósito |
| Botão "Aprovar" para o pacote | O pacote termina em revisão; você publica no Studio |
| Escrita de recomendações com IA pelo painel | Rascunhos por regras. Para texto escrito, use o Claude Code com `submit_recommendation` |
| Editar o texto de título, hook e thumbnail | Só o título tem campo próprio, "Outro" |
| Arrastar itens no calendário | Altere a data no formulário |
| Importar histórico do YouTube | Histórico é digitado por você |
| Regra de 08/12/2025 para artistas oficiais | Não implementada |
| Classificação de Short por vídeo via Analytics | Só há totais por tipo |
| Alertas por e-mail | Só há painel |
| Provedor de volume de busca | Ponto de ligação pronto, sem provedor contratado |
| Geração automática de ideias todo dia | Só sob demanda |
| Auditoria de canal própria | Só Analytics e perguntas ao Coach |
| OCR, rostos e geração de thumbnail | Fora desta fase |
| Coach por resposta em fluxo e imagens anexadas | Sem suporte |
| Comentários e transcrições | Sem conector |
| Curva de retenção | Só a porcentagem média |
| vidIQ MCP | Só interface desligada |
| `videos.batchGetStats` | Sem uso; limite local zerado |
| Plugin vidIQ para Claude Code | Citado na página oficial; sem instruções encontradas |
| Agendamento no Windows | Documentado; a tarefa não foi criada |

## Limitações conhecidas

- **Autorização não é barreira total:** a API exige token, mas um agente com terminal irrestrito na sua conta consegue ler `data/.api_token` ou editar `compliance.toml` e `execucao.toml`.
- **Pastas de produção não são apagadas sozinhas:** cada vídeo fica em `data/producao/<tarefa>/`, com cópia do motor, narração e o MP4.
- **Aprovação não verificável:** o aplicativo não confirma nada com o Google.
- **`.mcp.json` depende do ambiente:** aponta para `backend/.venv/Scripts/python.exe`. Rode `uv sync` antes, e abra o Claude Code na raiz do projeto.
- **Arquivos de teste não são apagados:** ficam em `data/artefatos_teste/`. Remover um canal apaga os registros, mas não esses arquivos.
- **Recuperação depende de consulta:** o prazo vencido é tratado quando alguém consulta a fila, o painel ou o MCP. Não há processo vigiando em segundo plano. Sem efeito prático: ninguém vê estado antigo.
- **Recomendação com métrica aprovada:** a justificativa guarda a pontuação em texto. Se a aprovação for revogada, não há rotina que a apague.
- **Pontos em aberto da política:** não está claro se a exceção cobre um uso privado de um único operador, nem como ela se concilia com a III.E.2. Este projeto não é parecer jurídico.
- **Totais de canais próprios no modo restrito:** a média ponderada pode ser lida como métrica derivada.
- **Primeiros dias:** IDR por idade depende de snapshots acumulados.
- **Limite de 30 dias:** sem aprovação, o histórico de terceiros não passa de 30 dias.
- **Tendências e relevância por palavras:** contagem de termos, sem semântica.
- **Prioridade editorial por regras:** não mede potencial.
- **Pesos do ranking:** escolhidos por julgamento, sem calibração.
- **Atribuição:** o rodapé cita o YouTube em texto; o uso das marcas não foi implementado.
