# O que falta para o primeiro canal real

## Já funciona, sem nenhuma credencial

- Cadastrar o canal, com o ID UC... e o perfil editorial.
- Criar recomendações, gerar títulos, aprovar briefing, usar calendário e histórico.
- Pedir ao Claude Code recomendações escritas (`submit_recommendation`) e briefings.

Nesse estado, o canal recebe só recomendações editoriais, sem números.

## Etapas

| # | O que | Quem | Bloqueia |
|---|---|---|---|
| 1 | Cadastrar o canal | Você ou eu, com seu OK | Nada: dá para fazer hoje |
| 2 | Escolher o perfil de pipeline | Você | Só descreve, por enquanto |
| 3 | **Definir onde roda a produção real** (`docs/PIPELINES.md`) | Decisão sua | Produção real |
| 4 | **Escrever o adaptador e ligar tarefa real na interface** | Eu | Produção real. Hoje, "Disponibilizar" só cria tarefa simulada |
| 5 | **Gerar roteiro a partir do briefing** | Eu, com sua revisão | Produção real: é a parte mais difícil |
| 6 | Definir `YTI_ARTIFACT_ROOTS` | Você ou eu | Entrega de arquivos reais |
| 7 | Primeiro vídeo curto, supervisionado | Juntos | Validação |
| 8 | Publicar manualmente no YouTube Studio | Você | Sempre: não há publicação no sistema |

## Opcional: dados do YouTube

Nada disso é preciso para produzir vídeos.

| O que | Para quê | Requer |
|---|---|---|
| Chave da Data API | Dados crus de concorrentes, por 30 dias | Sua chave no `.env` |
| OAuth | Analytics do próprio canal | Cliente OAuth e `authorize-channel` com a conta do canal |
| Aprovação do Google | Scores e VPH com dados reais | Extensão de cota e auditoria. Veja `docs/CONFORMIDADE.md` |

Primeira coisa a validar com a chave: se o tamanho do player distingue mesmo Shorts de vídeos 16:9. Foi implementado a partir da documentação e nunca rodou contra a API real.

## Recomendação

Comece pelo Brother Quill, com um vídeo curto, e faça o estúdio só **registrar** o que o Claude Code já faz naquele projeto: abrir a tarefa, atualizar etapas, entregar arquivos e montar o pacote. O estúdio não precisa executar comandos, e o pipeline atual continua igual.
