# Plano

Itens não concluídos ficam em `docs/PENDENCIAS.md`. Nada foi validado com a API real do YouTube, pois não há credenciais configuradas.

| # | Etapa | Entrega | Critério de pronto | Status |
|---|---|---|---|---|
| 1 | Auditoria e pesquisa | `docs/RELATORIO_EQUIVALENCIA.md` | Fontes citadas; restrições de política registradas | Feito |
| 2 | Documentos | `ARQUITETURA.md`, `PLANO.md` | Decisões e algoritmos descritos | Feito |
| 3 | Banco, conectores, coletor | `backend/app/...`, migrações | Testes de integração com mocks passam | Feito, só com mocks |
| 4 | Métricas e testes | `backend/app/metrics/` | Testes de scores, VPH e dados ausentes passam | Feito |
| 5 | Dashboard | `frontend/` | Build passa; telas conferidas em captura de tela | Feito |
| 6 | Recomendações com Claude | `backend/app/ai/` | Provedor testado; separação de dados não confiáveis testada | Feito; CLI testado uma vez de verdade, API só com mock |
| 7 | Fluxo completo | `test_full_flow_...` em `tests/test_integration.py` | Nicho → canal → vídeos → desempenho → oportunidade em mocks | Feito, só com mocks |
| 8 | Operação | `README.md`, `docs/COTAS_E_CUSTOS.md` | Passos para rodar e manter | Feito |

## Fora do MVP

Chat estilo coach, alertas por e-mail, análise de comentários e transcrições, curva de retenção, chamadas reais ao vidIQ MCP e `videos.batchGetStats`.
