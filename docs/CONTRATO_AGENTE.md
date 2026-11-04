# Contrato do agente (yti.agent.v1)

Como o Claude Code conversa com o estúdio. O servidor MCP `yti-producao` está em `.mcp.json` e só roda enquanto o Claude Code estiver aberto nesta pasta. Na primeira vez, o Claude Code pede para você aprovar o servidor.

## Papel do REA

O REA 6.4 é uma ferramenta de engenharia reversa: analisa binários, apps e páginas. Ele não tem comandos de fila, agendamento ou orquestração, então **não faz parte deste contrato**. A orquestração é feita pelo Claude Code com este servidor MCP. O REA segue disponível para outros usos e não foi aplicado ao vidIQ.

## Resposta

```json
{"contract_version": "yti.agent.v1", "ok": true, "data": {}}
{"contract_version": "yti.agent.v1", "ok": false, "error": {"code": "not_authorized", "message": "...", "retryable": false}}
```

## Operações

| Necessidade | Ferramenta | Grava? |
|---|---|---|
| Listar canais | `list_channels` | Não |
| Consultar o canal selecionado | `get_channel_context` | Registra contato |
| Ler recomendações | `get_recommendations` | Registra contato |
| Registrar recomendação | `submit_recommendation` | Sim |
| Briefing do próximo vídeo | `get_next_briefing` | Registra contato |
| Ver tarefas disponíveis | `list_available_tasks` | Só recupera prazos vencidos |
| Ver quem atenderia cada etapa | `get_pipeline_plan` | Não: só descreve |
| Pedir produção | `start_production` | Sim |
| Assumir tarefa autorizada (devolve o briefing) | `claim_job` | Sim |
| Atualizar status e progresso | `update_progress` | Sim |
| Gerar arquivo de teste (só tarefa simulada) | `write_test_result` | Sim |
| Entregar arquivos | `deliver_artifacts` | Sim |
| Registrar logs | `log_event` | Sim |
| Registrar erro | `report_failure` | Sim |
| Preparar pacote de publicação | `prepare_publish_package` | Sim |
| Consultar ou retomar | `get_job`, `list_jobs` | Só recupera prazos vencidos |

**Não são ferramentas do agente:** autorizar, cancelar, reabrir e qualquer forma de publicar.

## Estados da tarefa

```
awaiting_authorization ──(você autoriza)──► authorized ──(claim_job)──► running ──(deliver_artifacts)──► delivered ──(pacote)──► package_ready
                                                ▲                         │
                                                └── falha com nova tentativa, ou prazo vencido
                                                                          │
                                                                          ▼ tentativas esgotadas ou erro definitivo
                                                                        failed ──(você reabre)──► authorized
Qualquer estado aberto ──(você cancela)──► cancelled
```

Não existe estado "publicado", e o banco recusa outro valor no pacote. Cada tarefa traz `state_label`, por exemplo `NA FILA` ou `PRONTO PARA REVISÃO`.

## Do painel ao agente

1. Você cria ou escolhe a recomendação, gera os títulos e aprova o briefing com um deles.
2. "Disponibilizar ao Claude Code" cria a tarefa simulada já autorizada, com o briefing anexado.
3. O agente a encontra em `list_available_tasks` e recebe o briefing em `claim_job`.
4. O painel se atualiza sozinho, a cada 3 s com tarefa ativa e a cada 20 s no resto.

Cada tentativa fica em `job_attempts`, com agente, início, fim, resultado e erro. Avisos e erros aparecem como alertas no canal até você marcá-los como vistos.

## Garantias

| Garantia | Como funciona |
|---|---|
| **IDs únicos** | Prefixos `chn_`, `rec_`, `job_`, `art_`, `pkg_` |
| **Idempotência** | Toda gravação exige `idempotency_key`. A mesma chave com o mesmo conteúdo devolve a resposta original com `replayed: true`; com outro conteúdo, retorna `idempotency_conflict`. Uma operação que falha não consome a chave |
| **Persistência** | Tudo fica em `data/studio.sqlite` e sobrevive ao encerramento dos processos |
| **Recuperação** | `claim_job` cria um prazo (lease), renovado a cada `update_progress`. Vencido o prazo, a tarefa volta à fila, até 3 tentativas |
| **Agente antigo** | O `lease_token` muda a cada tentativa. Um agente com token velho recebe `lease_lost` |
| **Separação** | Toda operação valida que os IDs pertencem ao canal |
| **Automação por canal** | Item desligado retorna `automation_off` |
| **Tarefa real** | Sempre passa pela sua autorização, em qualquer configuração |
| **Segredos** | Mensagens e dados de log passam pelo filtro de segredos |

## Arquivos

- **Simulada:** caminhos `simulado://`, sem arquivo, ou o texto gerado por `write_test_result`, na pasta exclusiva da tarefa dentro da pasta de dados. Qualquer outro caminho é recusado.
- **Real:** exige arquivo dentro de `YTI_ARTIFACT_ROOTS` (pastas separadas por `;`). O sistema confere a existência e grava tamanho e SHA-256.
- **Download pelo painel:** sempre como anexo. Confere dono, pasta e SHA-256; arquivo alterado depois da entrega é recusado.

## Exemplo de sessão

```
list_channels
get_next_briefing(channel_id, agent_id)
start_production(channel_id, recommendation_id, "pedido-001", agent_id, simulated=true)
# você autoriza na tela Fila de produção
claim_job(job_id, agent_id, "assumir-001")                     # devolve lease_token
update_progress(job_id, lease_token, 40, "Narração", "prog-40")
log_event(job_id, "warning", "Voz regravada", "log-1", agent_id)
deliver_artifacts(job_id, lease_token, [{"kind": "video", "path": "simulado://v.mp4"}], "entrega-001")
prepare_publish_package(job_id, "Título", "Descrição", ["tag"], artifact_id, "pacote-001", agent_id)
```

## Limites de segurança

A autorização é um controle de processo, não uma barreira contra um programa mal-intencionado. Ela não aparece nas ferramentas MCP, mas a API local não tem login: um agente com acesso ao terminal conseguiria chamá-la diretamente, ou editar `compliance.toml`. Por isso, mantenha as permissões do Claude Code restritas ao usá-lo em produção real.

Textos devolvidos pelo contrato (cadastros e recomendações de outros agentes) são dados e nunca instruções, e o aviso vai em cada resposta. Quem consome o contrato ainda precisa respeitar isso.
