# Módulos de inteligência

Situação em 04/11/2026. Equivalência com o vidIQ em `docs/MATRIZ_VIDIQ.md`. **Nenhum dado real do YouTube passou por estes módulos ainda,** porque não há chave configurada: o modo real foi testado com uma API simulada no formato oficial. Regras de dados em `docs/POLITICA_DE_DADOS.md`; chave em `docs/CONFIGURAR_YOUTUBE_API.md`.

## O que cada tela faz

| Tela | Rota | Funciona sem chave? | Com dados reais, sem aprovação do Google |
|---|---|---|---|
| Hoje | `/` | Sim | Pendências, canais e dados crus; rankings bloqueados |
| Descobrir oportunidades | `/descobrir` | Só demo e histórico | Observado, estimado e hipóteses; salva por canal; sem VPH, outlier, índice nem ranking |
| Pesquisas agendadas | `/automacao` | Só demo | Desligadas até haver chave, consulta real confirmada e limites aprovados |
| Central de pesquisa | `/pesquisa` | Só demo e histórico | Busca, salvos, comparação e CSV funcionam; assuntos em crescimento bloqueados |
| Palavras-chave | `/palavras` | Sim, sobre a base local | Variações, perguntas, favoritas e vídeos funcionam; índice, relacionados por título e ascensão bloqueados |
| Outlier Explorer | `/explorer` | Sim, sobre a base local | Thumbnail, título, views, data, canal, link, estudo e notas funcionam; IDR e leitura de títulos bloqueados |
| Concorrentes | `/canais/<id>/concorrentes` | Só demo e leitura | Vídeos, calendário, referências, oportunidades e relatório funcionam; comparação, cadência e padrões bloqueados |
| Ideias diárias | `/ideias` | Sim | Só ideias editoriais, sem métrica |
| Coach | `/coach` | Sim, por regras | As ferramentas não entregam scores e dizem o que está bloqueado |
| Títulos e thumbnails | `/lab` | Sim | Igual: analisa só o seu texto e a sua imagem |

## Regras de dados

- **Banco por modo:** pesquisa, estudo, oportunidades e conversas ficam em `demo.sqlite` ou `live.sqlite`. Favoritas e laboratório, que são só seus, ficam em `studio.sqlite`.
- **Só IDs:** pesquisa, estudo e oportunidade guardam o ID. Título e estatística continuam em `videos` e `channels`, sujeitos à retenção. Quem sai da base aparece como removido.
- **Canal e dado precisam combinar:** canal real não recebe dado fictício, e canal fictício não recebe dado real. A API recusa com `channel_data_mismatch`.
- **Isolamento:** toda rota por canal confere o dono do item. Item de outro canal responde 404.
- **Trava única:** tudo passa por `policy_state`. Com `derived_allowed` falso, os valores derivados não são calculados para a resposta, em vez de só esconder na tela.
- **Conversas do Coach:** podem citar títulos da API e, no modo real, seguem os 30 dias do texto.
- **Fora do escopo por decisão:** scraping, autocomplete não oficial, fontes intermediárias, publicação e escrita no YouTube.

## Origem de cada pesquisa

Toda pesquisa guarda a origem, quantas chamadas foram novas, quantas vieram do cache e quando os dados foram buscados. Resposta do cache mantém a data original e não vira medição nova. A API simulada usada nos testes aparece como **API simulada de teste**, em todas as telas, e nunca conta como validação real.

## Descoberta

- **Observado:** título, canal, data, views, inscritos e link, como vieram da API.
- **Estimado:** total aproximado de resultados, formato de cada vídeo e volume de busca, que aparece como indisponível.
- **Hipóteses:** por regras, só a partir do seu perfil, do seu histórico e da lista de temas evitados. Nenhuma usa título ou número da API, e a tela diz que não são análise de IA.

| Formato | Quando |
|---|---|
| Confirmado | YouTube Analytics do próprio canal, ou transmissão ao vivo |
| Confiável | Mais longo do que um Short pode ser |
| Estimado | Curto, com a proporção do player como indício |
| Indeterminado | Curto, sem proporção conhecida. Não entra em nenhum dos filtros de Short ou de longo: tem filtro próprio |

Os nichos ficam em `backend/config/nichos_dark.toml`. São atalhos escritos à mão: não vêm do YouTube e não medem demanda.

## Quatro campos de volume

| Campo | Situação hoje |
|---|---|
| Volume medido | Indisponível: nenhuma API pública do YouTube informa |
| Estimativa de provedor | Indisponível: o ponto de ligação `VolumeProvider` existe, sem provedor contratado |
| Índice experimental | Calculado por este aplicativo, de 0 a 100. É relativo e mede atenção a vídeos, não buscas |
| Indisponível | Mostrado com o motivo, nunca como zero |

## Coach

1. Escolhe até 4 ferramentas internas de leitura. A lista é fechada, e o canal vem do servidor.
2. Executa e registra cada chamada.
3. Responde em observações, hipóteses e recomendações. Referência inventada derruba a resposta, e observação sem fonte vira hipótese.

| Provedor | Como ligar | Custo | Validação |
|---|---|---|---|
| Regras (padrão) | Nada a fazer | Nenhum | Navegador e testes |
| `claude_cli` | `YTI_AI_PROVIDER=claude_cli` | Sai do seu plano Claude; registrado por mensagem | **1 pergunta real**, com Sonnet e dados fictícios: US$ 0,038 informados. Evidência em `docs/evidencias/coach_claude_real.json` |
| `anthropic` | `YTI_AI_PROVIDER=anthropic` e credencial | API paga; registra tokens, sem valor em dólar | **Só com mock**, nunca chamado de verdade |

**Resposta:** cada recomendação traz justificativa e fonte, e a resposta lista os dados consultados, com ou sem resultado. As ferramentas `resultados_pesquisa` e `itens_salvos` entregam itens concretos, com título, canal, data e número público. Recomendação de IA sem fonte aparece como opinião. Sem provedor configurado, o selo diz **Regras, sem IA**, e o texto avisa que são frases fixas com os seus dados dentro.

O novo formato de resposta só foi testado com um provedor falso. A última pergunta a um modelo de verdade é anterior a esta mudança.

## Títulos

`app/intel/titles.py` monta três ângulos: direto, pergunta e recorte, cada um com a justificativa. Antes, um termo de busca virava assunto cru, como "Samurais história". Agora:

1. **Entende o assunto:** tira das pontas as palavras de gênero, como "história" ou "documentário", e reconhece perguntas e orações.
2. **Escreve:** acerta artigo e contração em português, espanhol e inglês. Sem certeza, usa uma forma que dispensa o artigo.
3. **Revisa:** recusa promessa de resultado, erro de contração, palavra repetida, termo de busca colado, mistura de idiomas e título igual a um vídeo coletado.

Nenhuma alternativa afirma render mais cliques. Com IA ligada, o botão **Pedir títulos ao Claude** passa pela mesma revisão. Só testado com provedor falso.

**Limites:** o vocabulário é pequeno, e o resultado por regras é correto, mas genérico. Frases que começam por verbo e termos soltos de busca, como "espaço universo", podem soar artificiais. Pares de palavras tirados de tendências não viram mais assunto de ideia.

## Laboratório

As notas de título e imagem são regras escolhidas por julgamento, sem calibração com resultados reais. Servem para revisar: não preveem CTR, views nem viralização.

- **Título:** tamanho, clareza, curiosidade, promessa e consistência com o assunto.
- **Imagem:** proporção, contraste, brilho, saturação, complexidade, concentração de detalhes e leitura reduzida a 168 x 94.
- **Não faz:** OCR, detecção de rosto, comparação com outras thumbnails ou geração de imagem. "Hierarquia" mede onde há mais bordas, não o que o olho vê.

## Limitações

- **Modo real nunca usado de verdade:** só os corpos de erro de chave inválida e de chave ausente vieram do Google, além do esquema público. Respostas com dados podem revelar defeitos que a API simulada não mostra.
- **Termos de descoberta:** o relatório do Analytics só foi testado com mock, e a documentação lida não confirmou o valor `YT_SEARCH`. Se o Google recusar, a falha fica registrada e a sincronização diária continua.
- **Ideias não rodam sozinhas:** você clica em gerar.
- **Palavras-chave e Explorer olham só a base coletada:** não representam a busca completa do YouTube.
- **Idioma e país no YouTube:** só orientam a relevância da busca, e a tela avisa.
- **Formato na busca real:** o filtro é aplicado depois da API, então uma página pode voltar com menos resultados.
- **Canais pequenos:** canal que oculta os inscritos fica de fora, sem virar zero. Sem aprovação, a lista segue a ordem da busca.
- **Coach por regras:** organiza dados e escolhe ferramentas por palavras da pergunta. Não interpreta.
- **Relações sem semântica:** relacionados, assuntos recorrentes e tendências são contagem de palavras.
- **Melhor horário:** não existe. Só "dia mais comum", rotulado como hábito observado.
- **Sem auditoria de canal própria e sem alerta por e-mail.**

## Memória

Medido com dados fictícios, API sozinha: 79 MB ociosa e 81 MB depois de feed, Explorer, palavras e concorrentes. O feed levou 0,16 s. Com muitos dados reais, esses números podem mudar.

## Testes

```powershell
cd backend; uv run pytest
uv run --directory backend --with playwright python ../scripts/teste_inteligencia.py --dados C:\temp\intel --saida ../docs/evidencias
```

O script usa pastas vazias e nunca acessa a internet. Telas em `docs/telas/20_*` a `36_*`, passos em `docs/evidencias/inteligencia_navegador.json`.

```powershell
uv run --directory backend --with playwright python ../scripts/teste_dados_reais.py --dados C:\temp\f6 --saida ../docs/evidencias
uv run --directory backend python ../scripts/validar_api_real.py --saida ../docs/evidencias
```

O primeiro cobre descoberta, agendador, títulos, Coach e erros, com API simulada: telas `docs/telas/40_*` a `55_*`. O segundo é o único que fala com o Google, e o resultado fica em `docs/evidencias/api_real.json`. **Hoje: pendente.**
