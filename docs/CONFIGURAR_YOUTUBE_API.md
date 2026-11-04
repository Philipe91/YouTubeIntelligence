# Configurar a YouTube Data API

Sem chave, o aplicativo continua funcionando em modo demonstração, com dados fictícios. A chave é gratuita: criar o projeto e ativar a API não gera cobrança por si só. Confira a tela do Google antes de aceitar qualquer termo.

**Nunca cole a chave em conversas, prints, issues ou commits.** Ela fica só no arquivo `.env`, que o Git ignora.

## Passos

1. Abra o [Google Cloud Console](https://console.cloud.google.com/) e crie um projeto só para este aplicativo. A política (III.D.1.c) pede um projeto por cliente: não crie vários para somar cota.
2. Em **APIs e serviços > Biblioteca**, ative a **YouTube Data API v3**.
3. Em **APIs e serviços > Credenciais**, crie uma **chave de API**.
4. Restrinja a chave: em **Restrições de API**, permita só a YouTube Data API v3. Evite restrição por site, porque o aplicativo chama a API do seu computador, e não de um navegador.
5. Na raiz do projeto, copie `.env.example` para `.env` e preencha:

   ```
   YOUTUBE_API_KEY=sua_chave_aqui
   ```

6. Rode o teste. Ele usa no máximo 3 unidades gerais e 1 chamada de busca:

   ```powershell
   uv run --directory backend python ../scripts/validar_api_real.py --saida ../docs/evidencias
   ```

7. Para o painel usar dados reais, defina `YTI_MODE=live` no `.env` e reinicie:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\parar.ps1
   powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
   ```

8. Em **Sistema e cotas**, clique em **Testar conexão**.

Para voltar aos dados fictícios, defina `YTI_MODE=demo` e reinicie. Os dois bancos são separados: nada se mistura.

## O que cada erro significa

| Mensagem no painel | Causa | O que fazer |
|---|---|---|
| A chave foi recusada | Chave errada ou incompleta | Copie de novo para o `.env` e reinicie |
| A API não está ativada no projeto | A chave é de um projeto sem a YouTube Data API v3 | Ative no Console e espere alguns minutos |
| A restrição da chave bloqueou o pedido | Restrição por site, IP ou outra API | Ajuste as restrições da chave |
| Cota do Google esgotada | Acabou a cota do dia | Espere a meia-noite do Pacífico. O aplicativo não insiste |
| Limite local de cota atingido | Passou do limite em `backend/config/quota.toml` | Espere a virada ou ajuste `YTI_QUOTA_<BALDE>_DAILY` |
| Sem conexão com o Google | Falha de internet | Confira a rede e tente de novo |
| Resposta em formato inesperado | HTTP 200 sem conteúdo utilizável | A resposta foi descartada. Confira os detalhes |

Os formatos de chave inválida e de chave ausente foram capturados do Google em 04/11/2026. Os demais seguem a documentação e os códigos conhecidos, ainda sem confirmação com uma conta real.

## Cota

| Balde | Limite do Google | Limite local | Quanto custa |
|---|---|---|---|
| Busca (`search.list`) | 100 chamadas por dia | 90 | 1 por pesquisa nova |
| Geral (`videos`, `channels`, `playlistItems`) | 10.000 unidades por dia | 9.000 | 1 por chamada, com até 50 itens |

Fonte: [tabela oficial de custos](https://developers.google.com/youtube/v3/determine_quota_cost), lida em 04/11/2026.

- **Cache:** repetir o mesmo pedido em até 6 horas não gasta busca. Em pesquisas por período, a data de corte é arredondada para o dia, para o cache funcionar.
- **Depois de uma recusa de cota do Google,** nada é chamado até a virada do dia de cota.
- **Pesquisas automáticas** ficam desligadas até você aprovar os limites. Veja **Automação**.

## O que continua bloqueado mesmo com a chave

A chave libera dados crus: título, canal, data, views e inscritos públicos. VPH, outliers, índices e comparações continuam bloqueados, porque dependem de auditoria e aprovação do Google. Veja `docs/POLITICA_DE_DADOS.md`.
