# YouTube Intelligence

Ferramenta local de inteligência competitiva para canais do YouTube: pesquisa de nicho, canais concorrentes, desempenho relativo, velocidade de views, tendências, oportunidades e geração de ideias. Implementação independente, sem relação com o vidIQ ou o YouTube.

**Antes de usar dados reais, leia [Modo real](#modo-real):** a política da API do YouTube bloqueia scores e VPH até o Google aceitar o uso analítico.

## Rodar em modo demonstração

Não precisa de credenciais, e todos os dados são fictícios. Requer [uv](https://docs.astral.sh/uv/) e Node 22 ou superior.

Terminal 1, API:

```powershell
cd D:\projetos\YouTubeIntelligence\backend
uv sync
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, interface:

```powershell
cd D:\projetos\YouTubeIntelligence\frontend
npm install
npm run build
npm run start
```

Abra <http://127.0.0.1:3000>. O Next.js coleta telemetria anônima por padrão; para desligar: `npx next telemetry disable`.

Para recriar os dados fictícios: `uv run python -m app.cli demo-reset`, na pasta `backend`.

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

A seção III.E.4.h da [política da API](https://developers.google.com/youtube/terms/developer-policies) proíbe métricas derivadas, sem exceção para uso privado. A [política de métricas derivadas](https://developers.google.com/youtube/terms/derived-metrics-policy) abre uma exceção para uso analítico:

1. Envie o [formulário da API do YouTube](https://support.google.com/youtube/contact/yt_api_form), informando o caso de uso de análise e relatórios.
2. Depois do aceite, preencha `YTI_DERIVED_METRICS_APPROVAL_REF` no `.env`.

O aplicativo não consegue verificar essa referência: preenchê-la é uma declaração sua. Com ela, estatísticas e métricas derivadas ficam até 36 meses; títulos e descrições seguem em 30 dias.

### 3. Meus canais (Analytics)

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
| Alterar o banco | Novo arquivo numerado em `backend/migrations/`; é aplicado ao iniciar |
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
- [Relatório de equivalência e auditoria](docs/RELATORIO_EQUIVALENCIA.md)
- [Cotas e custos](docs/COTAS_E_CUSTOS.md)
- [Pendências](docs/PENDENCIAS.md)
