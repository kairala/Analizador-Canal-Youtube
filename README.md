# YouTube Analytics Extractor

Script de linha de comando que lista os vídeos do seu canal do YouTube,
permite escolher um vídeo, vários, ou todos, e extrai um conjunto amplo de
métricas do YouTube Analytics para arquivos JSON em `output/`.

## 1. Configurar credenciais no Google Cloud

1. Acesse https://console.cloud.google.com/ e crie um novo projeto (ou use um existente).
2. No menu "APIs e Serviços" > "Biblioteca", habilite:
   - **YouTube Data API v3**
   - **YouTube Analytics API**
3. Em "APIs e Serviços" > "Tela de consentimento OAuth":
   - Tipo de usuário: **Externo**.
   - Preencha nome do app e e-mail de contato.
   - Em "Usuários de teste", adicione a sua própria conta do Google (a mesma do canal).
4. Em "APIs e Serviços" > "Credenciais" > "Criar credenciais" > "ID do cliente OAuth":
   - Tipo de aplicativo: **App para computador (Desktop app)**.
   - Baixe o JSON gerado e salve como `client_secret.json` na raiz deste projeto.

`client_secret.json` e `token.json` nunca devem ser commitados — ambos já
estão no `.gitignore`.

## 2. Instalar dependências

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Rodar o script

```bash
python main.py
```

Na primeira execução, o navegador abrirá para você logar com a conta do
Google dona do canal e autorizar o acesso somente leitura ao YouTube e ao
YouTube Analytics. O token de acesso fica salvo em `token.json` e é reusado
(e renovado automaticamente) nas próximas execuções.

O script então lista os vídeos do canal. Digite:
- um número (ex: `3`) para extrair um único vídeo;
- vários números separados por vírgula (ex: `1,4,7`);
- `todos` (ou `all`) para extrair todos os vídeos do canal.

## 4. Onde ficam os dados

```
output/
├── channel_videos.json       # snapshot de todos os vídeos do canal
├── por_video/
│   └── <video_id>.json       # metadados + todas as métricas daquele vídeo
└── consolidado.json          # todos os vídeos processados nesta execução, em um único arquivo
```

Cada arquivo por vídeo contém: totais acumulados, série diária, fontes de
tráfego, dispositivos, geografia, demografia (faixa etária/gênero) e curva
de retenção de audiência.

## 5. Rodando os testes

```bash
pytest
```

## 6. Gerar relatórios de performance com IA

Depois de extrair os dados com `python main.py`, você pode gerar relatórios
de performance escritos por IA (Claude) para os vídeos já extraídos.

### Configurar a chave da Anthropic

1. Crie uma chave em https://console.anthropic.com/ (seção "API Keys").
2. Crie um arquivo `.env` na raiz do projeto (se ainda não existir) com:
   ```
   ANTHROPIC_API_KEY=sua-chave-aqui
   ```
   `.env` já está no `.gitignore` — nunca é commitado.

### Rodar o script

```bash
python analyze.py
```

O script lista os vídeos já extraídos (em `output/por_video/`), você escolhe
um, vários (`1,4,7`) ou `todos`, e para cada um gera um relatório em Markdown
comparando o desempenho do vídeo com a média do canal, com recomendações.

Os relatórios ficam em `reports/<video_id>.md`.

**Custo**: cada vídeo analisado é uma chamada paga à API da Anthropic
(modelo Claude Opus). Rodar `todos` em um canal com muitos vídeos já
extraídos gera um custo proporcional ao número de vídeos.

## 7. App local com interface (binário)

Além dos scripts de linha de comando, o projeto tem uma versão com interface
web local, empacotável como um binário para rodar sem precisar instalar
Python.

### Rodar em modo desenvolvimento

```bash
source .venv/bin/activate
python desktop.py
```

Isso abre uma janela nativa do app. Na primeira execução, a aba de
Configuração pede o conteúdo do `client_secret.json` e a chave da API
Anthropic — diferente dos scripts `main.py`/`analyze.py`, essas credenciais
ficam salvas numa pasta de dados do usuário (fora da pasta do projeto), então
só precisam ser configuradas uma vez.

A partir daí, use as abas Extrair, Analisar e Navegar para rodar os mesmos
fluxos de `main.py`/`analyze.py` pela interface, com o progresso exibido ao
vivo.

### Gerar o binário

```bash
source .venv/bin/activate
pyinstaller build/desktop.spec --distpath dist
```

O executável fica em `dist/`. Como o PyInstaller não compila para outro
sistema operacional, o binário do Windows precisa ser gerado numa máquina
Windows — o workflow `.github/workflows/build-desktop.yml` faz isso
automaticamente numa matriz macOS + Windows via GitHub Actions
(`gh workflow run build-desktop.yml`).

No macOS, o build gera `dist/yt-data-extractor.app`. Esse app não é assinado
nem notarizado, então o Gatekeeper bloqueia a primeira abertura ("app está
danificado" ou aviso de desenvolvedor não identificado). Na primeira vez,
clique com o botão direito no app e escolha "Abrir" (em vez de dar duplo
clique) — depois disso, o Gatekeeper libera aberturas seguintes normalmente.
