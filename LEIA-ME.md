# Coleta diária do DJEN → Notion

Este pacote faz, todo dia útil de manhã, sem você precisar abrir nada:

1. Consulta o DJEN pela OAB 109280/RS, buscando o dia anterior.
2. Para cada comunicação nova, calcula a publicação e o início da contagem
   do prazo (art. 224, CPC), identifica se é caso do Blasco Advogados ou do
   Mário Filho Advogados, e separa as partes.
3. Lança tudo como uma nova linha no banco **📬 Prazos DJEN** do Notion,
   dentro da view "🆕 A classificar".
4. Evita duplicar: se a comunicação já foi lançada, ela é ignorada.

**O que ele NÃO faz:** não decide o tipo de ato, o prazo em dias nem a
data fatal. Isso continua exigindo que você (ou alguém do escritório) abra
cada item novo na view "🆕 A classificar", leia o teor e preencha esses três
campos manualmente. É proposital — essa é uma decisão jurídica, não um
cálculo automático.

Este guia pressupõe que você nunca usou GitHub. Vamos passo a passo.

---

## Parte 1 — Autorizar o script a escrever no seu Notion

O Notion não usa senha para isso — usa um "token de integração", uma chave
de acesso específica para esse fim.

1. Acesse **https://www.notion.so/profile/integrations** (logado com a
   sua conta do Notion).
2. Clique em **"New integration"**.
3. Dê um nome, por exemplo `Coleta DJEN`. Em "Associated workspace",
   escolha o workspace do escritório. Clique em **Save**.
4. Na tela que abrir, copie o valor em **"Internal Integration Secret"**
   (começa com `ntn_...` ou `secret_...`). Guarde esse valor — é o
   `NOTION_TOKEN` que vamos usar mais adiante. **Não compartilhe esse
   valor com ninguém nem cole em nenhum outro lugar além do indicado
   neste guia.**
5. Agora vá até o banco **📬 Prazos DJEN** no Notion. No canto superior
   direito da página, clique nos **"···"** (mais opções) → **"Conexões"**
   (ou "Connections") → procure e selecione a integração `Coleta DJEN`
   que você acabou de criar. Isso dá permissão para ela escrever ali —
   sem esse passo, o script recebe erro de permissão.

O ID do banco (`NOTION_DATABASE_ID`) já está definido para você:

```
76e2032a-f268-46d8-820d-9f878125e1fb
```

---

## Parte 2 — Criar o repositório no GitHub

O GitHub é apenas o lugar onde o código do script fica guardado, e é o
GitHub que também oferece o "relógio" que roda o script todo dia
(GitHub Actions).

1. Crie uma conta em **https://github.com/signup** se ainda não tiver.
2. Clique no **"+"** no canto superior direito → **"New repository"**.
3. Nome sugerido: `djen-notion-sync`. Marque como **Private**
   (importante — o repositório vai guardar configurações do escritório).
   Clique em **Create repository**.
4. Na página do repositório recém-criado, clique em **"uploading an
   existing file"** (ou "Add file" → "Upload files").
5. Arraste para lá **todos os arquivos e pastas** deste pacote, mantendo
   a estrutura: `djen_sync.py`, `requirements.txt`, `LEIA-ME.md`, e a
   pasta `.github/workflows/coleta-diaria.yml` (o GitHub deve manter a
   pasta `.github` automaticamente se você arrastar a estrutura completa;
   se seu navegador não permitir arrastar pastas, veja a "Alternativa"
   abaixo).
6. Clique em **"Commit changes"**.

**Alternativa mais confiável**, se arrastar pastas não funcionar no seu
navegador: instale o **GitHub Desktop** (https://desktop.github.com/),
que tem interface gráfica simples — clone o repositório vazio, copie os
arquivos deste pacote para a pasta local, e clique em "Commit" e "Push".

---

## Parte 3 — Guardar a chave do Notion com segurança no GitHub

O arquivo do script nunca deve conter a chave real — ela fica guardada
separadamente, criptografada, nos "Secrets" do repositório.

1. No repositório, vá em **Settings** (aba no topo) → no menu à esquerda,
   **Secrets and variables** → **Actions**.
2. Clique em **"New repository secret"**.
   - Nome: `NOTION_TOKEN`
   - Valor: cole a chave `ntn_...` que você copiou na Parte 1.
   - Clique em **Add secret**.
3. Repita para um segundo secret:
   - Nome: `NOTION_DATABASE_ID`
   - Valor: `76e2032a-f268-46d8-820d-9f878125e1fb`
   - Clique em **Add secret**.

---

## Parte 4 — Testar manualmente antes de confiar no agendamento

1. No repositório, clique na aba **Actions**.
2. Se aparecer um aviso pedindo para habilitar Actions, clique para
   habilitar.
3. Clique no workflow **"Coleta diária DJEN -> Notion"** na lista à
   esquerda.
4. Clique no botão **"Run workflow"** (à direita) → **"Run workflow"**
   novamente para confirmar.
5. Aguarde uns 20-30 segundos e atualize a página. Um círculo amarelo
   vira ✅ verde (sucesso) ou ❌ vermelho (erro). Clique em cima da
   execução para ver o log linha a linha — ele mostra quantas
   comunicações foram encontradas e lançadas.
6. Confira o Notion: deve ter aparecido uma nova linha (ou o log deve
   dizer "0 novo(s)" se não houve publicação da OAB naquele dia — o que
   é normal e esperado na maioria dos dias).

Se der erro, o log geralmente indica a causa (chave errada, banco não
compartilhado com a integração, etc.). Cole o erro de volta para mim que
eu ajudo a diagnosticar.

---

## Parte 5 — Deixar rodando sozinho

Não precisa fazer mais nada. O workflow já está agendado para rodar
automaticamente **de segunda a sexta, às 9h no horário de Brasília**,
sem que ninguém precise abrir o GitHub, o Notion ou qualquer outra coisa.

Se quiser mudar o horário, o arquivo `.github/workflows/coleta-diaria.yml`
tem uma linha `cron: "0 12 * * 1-5"` — o primeiro número é o minuto, o
segundo a hora, sempre em UTC (horário de Brasília + 3h). Me chame se
quiser ajustar.

---

## Parte 6 — Ver os prazos no Notion Calendar

1. Abra o **Notion Calendar** (app separado do Notion, mesma conta).
2. No painel lateral, procure por "Adicionar calendário" ou o ícone de
   `+` ao lado de "Notion Calendars".
3. Selecione o banco **📬 Prazos DJEN**.
4. Quando perguntado qual propriedade de data usar, escolha **"Data
   fatal"** — assim só aparecem no calendário os itens que já têm prazo
   calculado e conferido, não a fila bruta de coleta.

---

## Limitações que valem registrar

- **Feriados forenses locais e recesso (20/12 a 20/01) não são calculados
  automaticamente.** O script só considera sábados, domingos e feriados
  nacionais fixos. Publicações próximas a essas datas precisam de
  conferência manual da "Início da contagem".
- **O script nunca decide prazo em dias nem data fatal.** Isso é
  intencional — é a parte que exige leitura jurídica do teor.
- **Uma execução por dia útil, sobre o dia anterior.** Se o script ficar
  fora do ar por algum motivo (GitHub instável, por exemplo) por mais de
  um dia, rode manualmente pela aba Actions com "Run workflow", ajustando
  se necessário a data via o campo `DATA_ALVO` (veja a Parte 7 abaixo).

## Parte 7 — Rodar para uma data específica (recuperar um dia perdido)

Na tela de "Run workflow" (Parte 4), o GitHub também permite passar uma
entrada. Se quiser reprocessar um dia específico manualmente, me avise —
posso ajustar o workflow para aceitar uma data como parâmetro na própria
tela do GitHub, sem precisar editar código.
