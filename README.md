# YouTube Intelligence

Central local para gerenciar seus canais dark e pesquisar nichos: cadastro de canais, recomendações por canal, calendário, fila de produção integrada ao Claude Code, além de pesquisa, concorrentes, desempenho relativo e tendências. Implementação independente, sem relação com o vidIQ ou o YouTube.

**Antes de usar dados reais, leia [Modo real](#modo-real):** a política da API do YouTube bloqueia scores e VPH sem auditoria e aprovação do Google.

## Instalar uma vez

Requer [uv](https://docs.astral.sh/uv/) e Node 22 ou superior. Não precisa de credenciais.

```powershell
cd D:\projetos\YouTubeIntelligence\backend
uv sync
cd ..\frontend
npm install
npm run build
```

## Ligar e desligar

```powershell
cd D:\projetos\YouTubeIntelligence
powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
powershell -ExecutionPolicy Bypass -File scripts\parar.ps1
```

Abra <http://127.0.0.1:3000/canais>. Ligado, o aplicativo usa cerca de 260 MB; desligado, nada. Detalhes em `docs/MEMORIA.md`. Depois de alterar o frontend, rode `npm run build` de novo.

Para recriar os dados fictícios de pesquisa: `uv run python -m app.cli demo-reset`, na pasta `backend`. Isso não toca nos seus canais.

## Meus canais dark

Seus cadastros ficam em `data/studio.sqlite`, valem nos dois modos e não dependem de chave de API.

- **Canais fictícios** (`Fictício`) mostram como a central funciona. Podem ser removidos e não voltam.
- **Seus canais** (`Seu canal`) nunca recebem dados fictícios. Sem métricas liberadas, as recomendações são editoriais: perfil, ideias e histórico do canal, sem nenhum score.

Na página de cada canal: visão geral, recomendações, fila, calendário, histórico, concorrentes e configurações, incluindo automação. O calendário é interno: nada é agendado no YouTube.

## Claude Code

Abra o Claude Code nesta pasta e aprove o servidor `yti-producao` definido em `.mcp.json`. Depois, peça por exemplo: "use yti-producao para ler o briefing do canal X e propor três recomendações". O contrato completo está em `docs/CONTRATO_AGENTE.md`.

O agente lê, propõe, pede produção e entrega arquivos. Autorizar é com você, na tela Fila de produção, e **não existe publicação**.

## Testes

```powershell
cd backend
uv run pytest
cd ..\frontend
npm run typecheck
```

Os testes não acessam a rede: as APIs são simuladas.

## Modo real

### 1. Coleta de dados crus

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um projeto, ative a **YouTube Data API v3** e crie uma chave de API.
2. Copie `.env.example` para `.env` e preencha `YTI_MODE=live` e `YOUTUBE_API_KEY`.
3. Reinicie a API. O banco passa a ser `data/live.sqlite`; o demo fica em `data/demo.sqlite`.

```powershell
cd backend
uv run python -m app.cli search "história animada" --language pt --country BR
uv run python -m app.cli add-channel "@handle_do_canal"
uv run python -m app.cli collect
```

Neste estado o aplicativo mostra só dados crus e apaga dados de terceiros após 30 dias.

### 2. Liberar scores e VPH

A seção III.E.4.h da [política da API](https://developers.google.com/youtube/terms/developer-policies) proíbe métricas derivadas, sem exceção para uso privado. A seção III.L e a [política de métricas derivadas](https://developers.google.com/youtube/terms/derived-metrics-policy) abrem uma exceção para desenvolvedores auditados e aprovados:

1. Envie o [pedido de extensão de cota](https://support.google.com/youtube/contact/yt_api_form), com o caso de uso de análise e relatórios, e passe pela auditoria.
2. Com a aprovação em mãos, preencha `backend/config/compliance.toml`.

O aplicativo não consegue confirmar a aprovação: o arquivo é uma declaração sua, e qualquer campo ausente ou vencido mantém tudo bloqueado. Detalhes em `docs/CONFORMIDADE.md`.

### 3. Analytics dos seus canais

1. Ative a **YouTube Analytics API** no mesmo projeto.
2. Crie um cliente OAuth do tipo **App para computador**, baixe o JSON para fora do repositório e aponte `YOUTUBE_OAUTH_CLIENT_SECRETS` para ele.
3. Autorize com a conta do canal:

```powershell
uv run python -m app.cli authorize-channel "@seu_canal"
```

Os escopos são só de leitura. O refresh token fica no Gerenciador de Credenciais do Windows. Para desfazer: `uv run python -m app.cli revoke-channel UC...`.

### 4. Coleta contínua

Crie uma tarefa no Agendador de Tarefas do Windows, a cada 15 minutos, em `backend`:

```
uv run python -m app.cli collect
```

Cada tarefa respeita o próprio intervalo, então rodar com mais frequência não gasta mais cota. Como alternativa, deixe um terminal aberto com `uv run python -m app.cli scheduler`.

## Geração de ideias

Defina `YTI_AI_PROVIDER` no `.env`:

| Valor | O que faz | Custo |
|---|---|---|
| `none` (padrão) | Estrutura para preencher, rotulada como modelo sem IA | Nenhum |
| `claude_cli` | Usa o comando `claude` desta máquina, sem ferramentas | Conta do seu plano Claude |
| `anthropic` | API da Anthropic, exige `ANTHROPIC_API_KEY` | Por uso; veja `docs/COTAS_E_CUSTOS.md` |

Com `anthropic`, as requisições usam o fallback automático do servidor quando o modelo recusa um pedido. Para desligar, remova `fallbacks` e `betas` em `AnthropicProvider`.

Títulos e descrições de outros canais são tratados como dados não confiáveis. A saída é validada: citação de evidência inexistente, título copiado ou promessa de viralização são rejeitados.

## Manutenção

| Tarefa | Como |
|---|---|
| Ver cota e tarefas | Tela **Sistema e cotas** |
| Ajustar fórmulas e limites | `backend/config/scoring.toml`, depois reinicie a API |
| Ajustar cotas | `backend/config/quota.toml` ou `YTI_QUOTA_<BALDE>_DAILY` |
| Alterar o banco | Novo arquivo numerado em `backend/migrations/` ou `backend/migrations_studio/`; é aplicado ao iniciar |
| Apagar dados de um canal | `uv run python -m app.cli delete-channel-data UC...` |
| Backup | Copie `data/` com a API parada |
| Revisar a política | Reler as políticas do YouTube periodicamente; elas mudaram em 2026 |

## Conexão opcional com vidIQ

O aplicativo funciona sem vidIQ. Para usá-lo no Claude Code, consumindo créditos da sua conta só quando pedir:

```powershell
claude mcp add --transport http vidiq https://mcp.vidiq.com/mcp
```

## Documentos

- [Arquitetura](ARQUITETURA.md)
- [Plano](PLANO.md)
- [Relatório da versão multicanal](docs/RELATORIO_MULTICANAL.md)
- [Contrato do agente](docs/CONTRATO_AGENTE.md)
- [Conformidade](docs/CONFORMIDADE.md)
- [Memória](docs/MEMORIA.md)
- [Relatório de equivalência e auditoria](docs/RELATORIO_EQUIVALENCIA.md)
- [Cotas e custos](docs/COTAS_E_CUSTOS.md)
- [Pendências](docs/PENDENCIAS.md)
