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
