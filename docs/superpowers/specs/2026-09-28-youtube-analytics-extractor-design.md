# YouTube Analytics Extractor — Design

- Date: 2026-09-28
- Status: Approved

## Purpose

O usuário tem um canal do YouTube e quer analisar o desempenho dos seus vídeos
fora da interface do YouTube Studio (ex: em planilhas, pandas, BI). Este
projeto é um script Python de linha de comando que lista os vídeos do canal,
permite escolher um vídeo específico ou todos, extrai um conjunto amplo de
métricas de analytics via API do Google, e salva os dados em arquivos JSON
prontos para análise posterior.

Sucesso = rodar o script, escolher vídeos (um, vários ou todos), e obter
arquivos JSON completos e corretos em `output/`, tanto por vídeo quanto
consolidados, sem precisar tocar na API manualmente.

## Escopo

Incluído:
- Autenticação OAuth2 com a conta do dono do canal (fluxo "installed app").
- Listagem de todos os vídeos do canal (via uploads playlist), com seleção
  interativa (um vídeo, múltiplos por vírgula, ou todos).
- Extração de métricas via YouTube Analytics API v2 para cada vídeo
  selecionado: totais, série diária, fontes de tráfego, dispositivos,
  geografia, demografia e retenção de audiência.
- Persistência em JSON: um arquivo por vídeo e um arquivo consolidado.
- Tratamento de erros que não trava o lote inteiro por causa de um vídeo.
- README com passo a passo de configuração de credenciais no Google Cloud.

Fora de escopo (YAGNI por enquanto):
- Interface gráfica ou web.
- Agendamento automático / execução recorrente.
- Métricas de receita/monetização (exigem escopo OAuth adicional e nem todo
  canal é monetizado).
- Exportação para CSV/Excel (usuário escolheu JSON).
- Suporte a múltiplos canais/contas na mesma execução.

## Arquitetura

Script Python standalone, sem framework web. Duas dependências externas
principais: `google-api-python-client` + `google-auth-oauthlib` para
autenticação e chamadas às APIs.

```
yt_analytics_extractor/
├── README.md
├── requirements.txt
├── .gitignore
├── main.py
├── src/
│   ├── auth.py
│   ├── youtube_data.py
│   ├── reports.py
│   ├── youtube_analytics.py
│   └── storage.py
└── output/                # gerado em runtime, git-ignored
```

### Componentes

**`auth.py`**
- O que faz: executa o fluxo OAuth2 (`InstalledAppFlow`), armazena e recarrega
  o token localmente (`token.json`), renova automaticamente quando expirado.
- Como se usa: `get_credentials() -> Credentials`.
- Depende de: `client_secret.json` (gerado pelo usuário no Google Cloud
  Console, não versionado).

**`youtube_data.py`**
- O que faz: busca a uploads playlist do canal autenticado e pagina por todos
  os vídeos, retornando metadados (id, título, data de publicação, duração,
  status de privacidade).
- Como se usa: `list_channel_videos(youtube_data_service) -> list[VideoMeta]`.
- Depende de: credenciais válidas, API `youtube.googleapis.com` (Data API v3).

**`reports.py`**
- O que faz: define, de forma declarativa, os relatórios a extrair (nome,
  métricas, dimensões, se é série temporal ou agregado único). Centraliza o
  conhecimento de quais métricas/dimensões são compatíveis entre si na
  Analytics API, para facilitar adicionar/remover relatórios depois.
- Como se usa: exporta uma lista `REPORTS` consumida por `youtube_analytics.py`.
- Depende de: nada (módulo de dados puro).

**`youtube_analytics.py`**
- O que faz: para um vídeo e uma definição de relatório, monta e executa a
  query na YouTube Analytics API (`reports().query()`), com filtro
  `video==VIDEO_ID` e intervalo de datas da publicação até hoje. Lida com
  paginação/erros de uma query individual.
- Como se usa: `run_report(analytics_service, video_id, published_at, report_def) -> dict`.
- Depende de: credenciais válidas, API `youtubeanalytics.googleapis.com`.

**`storage.py`**
- O que faz: monta o objeto JSON final de um vídeo (metadados + todos os
  relatórios) e grava em `output/por_video/<video_id>.json`; também mantém e
  regrava `output/consolidado.json` com a lista de todos os vídeos já
  processados nesta execução.
- Como se usa: `save_video_report(video_meta, reports_by_name)`,
  `save_consolidated(all_video_reports)`.
- Depende de: apenas `pathlib`/`json` da stdlib.

**`main.py` (CLI/orquestração)**
- O que faz: fluxo principal — autentica, lista vídeos, imprime menu
  numerado, lê a escolha do usuário (número, lista separada por vírgula, ou
  "todos"), e para cada vídeo selecionado roda todos os relatórios de
  `reports.py` e persiste via `storage.py`, imprimindo progresso e
  continuando em caso de erro num vídeo específico.

### Fluxo de dados

1. `auth.get_credentials()` → `Credentials`
2. Constrói os clients `youtube` (Data API v3) e `youtubeAnalytics` (v2) via
   `googleapiclient.discovery.build`.
3. `youtube_data.list_channel_videos(youtube)` → lista completa de vídeos do
   canal (com paginação da playlist de uploads).
4. CLI imprime a lista numerada e lê a seleção do usuário.
5. Para cada vídeo selecionado, para cada item em `reports.REPORTS`:
   `youtube_analytics.run_report(...)` → dict com o resultado daquele
   relatório.
6. Os resultados de todos os relatórios de um vídeo são agrupados num único
   objeto e passados para `storage.save_video_report(...)`.
7. Ao final do lote, `storage.save_consolidated(...)` grava/atualiza
   `output/consolidado.json` com todos os vídeos processados nesta execução.

### Relatórios extraídos (conjunto completo)

| Nome | Dimensões | Métricas principais | Formato |
|---|---|---|---|
| `totals` | (nenhuma, agregado) | views, estimatedMinutesWatched, averageViewDuration, averageViewPercentage, likes, comments, shares, subscribersGained, subscribersLost, impressions, impressionsClickThroughRate | objeto único |
| `daily` | day | mesmas métricas de `totals` | lista, uma entrada por dia |
| `traffic_sources` | insightTrafficSourceType | views, estimatedMinutesWatched | lista |
| `devices` | deviceType | views, estimatedMinutesWatched | lista |
| `geography` | country | views, estimatedMinutesWatched | lista |
| `demographics` | ageGroup, gender | viewerPercentage | lista |
| `retention` | elapsedVideoTimeRatio | audienceWatchRatio, relativeRetentionPerformance | lista (curva) |

Todas as queries são filtradas por `video==<ID>` e usam o intervalo de datas
`publishedAt` (data de publicação do vídeo) até hoje. Relatórios de quebra
(traffic/devices/geography/demographics/retention) são agregados no período
inteiro, não diários — evita explosão de volume de dados sem perder o
essencial (o usuário pode pedir granularidade diária neles depois, se sentir
falta).

## Formato dos arquivos de saída

`output/channel_videos.json` — snapshot de metadados de todos os vídeos do
canal encontrados na última listagem (referência/debug).

`output/por_video/<video_id>.json`:
```json
{
  "video": { "id": "...", "title": "...", "published_at": "...", "duration": "..." },
  "totals": { "views": 123, "...": "..." },
  "daily": [ { "date": "2026-01-01", "views": 10, "...": "..." } ],
  "traffic_sources": [ { "source": "YT_SEARCH", "views": 50 } ],
  "devices": [ { "device": "MOBILE", "views": 80 } ],
  "geography": [ { "country": "BR", "views": 100 } ],
  "demographics": [ { "age_group": "AGE_25_34", "gender": "male", "viewer_percentage": 30.5 } ],
  "retention": [ { "elapsed_ratio": 0.1, "audience_watch_ratio": 0.95 } ]
}
```

`output/consolidado.json`:
```json
{ "generated_at": "...", "videos": [ /* mesmo formato de por_video/*.json, um item por vídeo */ ] }
```

## Tratamento de erros

- Vídeo muito recente (sem dados suficientes no Analytics, defasagem ~48h):
  a API retorna resultado vazio para aquele relatório; o script salva o
  relatório como lista/objeto vazio e segue, sem travar.
- Erro de quota/rate limit (HTTP 403/429) numa chamada: retry com backoff
  exponencial (poucas tentativas); se persistir, loga o erro e pula para o
  próximo relatório/vídeo em vez de abortar o processamento de "todos".
- Token expirado: renovado automaticamente pela biblioteca
  `google-auth-oauthlib`; se o refresh token for inválido/revogado, o script
  detecta a falha de auth e orienta o usuário a apagar `token.json` e logar
  de novo.
- Entrada inválida no menu de seleção (número fora da faixa, texto
  inesperado): mensagem de erro clara e nova tentativa de leitura, sem
  encerrar o programa.

## Testes

Dado que é um script pessoal fortemente dependente de contas/API reais do
Google, o plano de testes é:

- Testes unitários (com `pytest`) para lógica pura e isolada: sanitização/
  formatação de nomes de arquivo, cálculo do intervalo de datas
  (`published_at` → hoje), montagem do objeto consolidado a partir de
  relatórios individuais, e o parsing da entrada do usuário no menu (número
  único, lista por vírgula, "todos").
- Verificação manual como critério de aceite do fluxo fim a fim: primeiro
  login/autorização, listagem de vídeos do canal real, extração de 1 vídeo
  específico, e extração em lote de "todos" os vídeos — confirmando que os
  arquivos em `output/` são gerados corretamente e no formato esperado.
- Não mockar as APIs do Google para simular testes de integração completos:
  custo/benefício não compensa para um script de uso pessoal.

## Configuração de credenciais (README)

O README incluirá passo a passo para o usuário:
1. Criar um projeto no Google Cloud Console.
2. Habilitar a "YouTube Data API v3" e a "YouTube Analytics API".
3. Configurar a tela de consentimento OAuth (tipo Externo, modo de teste,
   adicionar a própria conta Google como usuário de teste).
4. Criar credenciais OAuth do tipo "Desktop app" e baixar como
   `client_secret.json` na raiz do projeto.
5. Rodar `python main.py` pela primeira vez, que abre o navegador para
   autorizar o acesso; o token fica salvo em `token.json` para reuso.

`client_secret.json` e `token.json` entram no `.gitignore` — nunca são
versionados.
