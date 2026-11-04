# Testes

| Tipo | Comando | O que cobre | Executa pipeline real? |
|---|---|---|---|
| Backend | `cd backend; uv run pytest` | Pesquisa, conformidade, estúdio, contrato, autenticação, adaptador, worker | Não: executor falso |
| Tipos do frontend | `cd frontend; npx tsc --noEmit` | Tipos do painel | Não |
| Ciclo completo | Veja abaixo | Navegador, MCP real, queda e reinício, com tarefa simulada | Não |
| Produção real | Manual. Veja `docs/INTEGRACAO_BROTHER_QUILL.md` | Claude Code, worker, render e validação | **Sim** |

## Ciclo completo

Com o painel desligado, o frontend compilado e uma pasta vazia fora de `data/`:

```powershell
uv run --directory backend --with playwright python ../scripts/teste_ciclo_completo.py --dados C:\temp\ciclo --saida ../docs/evidencias
```

## Produção real

Consome memória e créditos do plano Claude, e leva alguns minutos. Confira a memória livre antes.

1. No painel, abra um canal com perfil Brother Quill, aprove um briefing e clique em **Autorizar produção real**.
2. Na raiz do projeto, abra a sessão do agente só com as ferramentas do estúdio:

   ```powershell
   claude --mcp-config .mcp.json --strict-mcp-config --allowedTools "mcp__yti-producao__*"
   ```

3. Peça para assumir a tarefa, escrever o roteiro e iniciar a produção. Acompanhe as etapas no painel.
4. Depois da entrega, peça `validate_video` e `prepare_publish_package`.
5. **Assista ao vídeo.** A validação automática confere o arquivo, não a qualidade.

## O que os testes automáticos não garantem

- Que o vídeo esteja bom. Os defeitos da primeira produção real só apareceram na inspeção dos quadros e na medição do áudio.
- Que o pipeline real continue funcionando: a suíte usa executor falso, para não renderizar nada. Mudanças em `tts.py` ou `render.mjs` só aparecem em uma produção real.
