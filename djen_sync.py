#!/usr/bin/env python3
"""
Coleta diária de comunicações do DJEN (Diário de Justiça Eletrônico Nacional)
e alimentação do banco "Prazos DJEN" no Notion.

Fonte da API: https://comunicaapi.pje.jus.br/swagger/index.html
Endpoint usado: GET /api/v1/comunicacao (público, sem autenticação)

Regras de negócio (definidas pelo usuário em conversa com Claude):
- Consulta feita apenas pela OAB do usuário (109280/RS).
- Se a intimação também trouxer Mário Luiz Fernandes Medeiros (OAB RS-65852)
  e/ou Fabiana Soares Prestes (OAB RS-112996) como advogados destinatários,
  o caso pertence ao Mário Filho Advogados (registrado no Notion como "MF - Cliente").
  Caso contrário, pertence ao Blasco Advogados.
- Publicação = primeiro dia útil seguinte à disponibilização (art. 224, §2º, CPC).
- Início da contagem do prazo = primeiro dia útil seguinte à publicação.
- Feriados nacionais fixos são considerados. Feriados forenses locais (TJRS,
  JFRS/TRF4, TJSC) e recesso forense (20/12 a 20/01, art. 220 CPC) NÃO são
  calculados automaticamente — ficam marcados para conferência manual.

IMPORTANTE: Este script preenche "Disponibilização", "Início da contagem" e os
dados descritivos da comunicação. Ele NUNCA preenche "Tipo de ato", "Prazo em
dias" ou "Data fatal" — esses campos exigem leitura do teor por um advogado e
ficam para preenchimento manual no Notion. O script apenas organiza a fila de
trabalho (view "🆕 A classificar").
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.parse
import urllib.error
import time

# ---------------------------------------------------------------------------
# Configuração — lida de variáveis de ambiente (definidas como Secrets no
# GitHub Actions; nunca escrever valores reais neste arquivo).
# ---------------------------------------------------------------------------

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]  # data_source_id do 📬 Prazos DJEN
NUMERO_OAB = os.environ.get("NUMERO_OAB", "109280")
UF_OAB = os.environ.get("UF_OAB", "RS")

NOTION_VERSION = "2022-06-28"
NOTION_API = "https://api.notion.com/v1"
DJEN_API = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"

# OABs que, quando aparecem junto com a do usuário na mesma comunicação,
# indicam que o caso pertence ao Mário Filho Advogados.
OABS_MARIO_FILHO = {"65852-RS", "112996-RS"}

FERIADOS_NACIONAIS_FIXOS = {
    (1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25),
}

# ---------------------------------------------------------------------------
# Cálculo de dias úteis
# ---------------------------------------------------------------------------

def eh_dia_util(data: datetime.date) -> bool:
    """Sábado, domingo ou feriado nacional fixo -> não é dia útil.
    Feriados móveis (Carnaval, Sexta-feira Santa, Corpus Christi) e feriados
    forenses locais NÃO são cobertos aqui — o campo fica sinalizado para
    conferência manual quando a data cair perto de um deles."""
    if data.weekday() >= 5:  # 5=sábado, 6=domingo
        return False
    if (data.month, data.day) in FERIADOS_NACIONAIS_FIXOS:
        return False
    return True


def proximo_dia_util(data: datetime.date) -> datetime.date:
    """Retorna o primeiro dia útil seguinte à data informada (exclusive)."""
    d = data + datetime.timedelta(days=1)
    while not eh_dia_util(d):
        d += datetime.timedelta(days=1)
    return d


def calcular_datas_prazo(disponibilizacao: datetime.date) -> tuple[datetime.date, datetime.date]:
    """
    Aplica a cadeia do art. 224, CPC:
      disponibilização -> publicação (1º dia útil seguinte)
                        -> início da contagem (1º dia útil seguinte à publicação)
    """
    publicacao = proximo_dia_util(disponibilizacao)
    inicio_contagem = proximo_dia_util(publicacao)
    return publicacao, inicio_contagem


# ---------------------------------------------------------------------------
# Classificação de escritório
# ---------------------------------------------------------------------------

def classificar_escritorio(destinatario_advogados: list[dict]) -> str:
    """
    Recebe a lista `destinatarioadvogados` retornada pelo DJEN para uma
    comunicação e decide o escritório responsável, conforme a regra definida
    pelo usuário: OAB do usuário sozinha = Blasco; acompanhada de Mário Luiz
    ou Fabiana = Mário Filho Advogados.
    """
    for item in destinatario_advogados:
        adv = item.get("advogado") or {}
        chave = f"{adv.get('numero_oab', '')}-{adv.get('uf_oab', '')}"
        if chave in OABS_MARIO_FILHO:
            return "Mário Filho Advogados"
    return "Blasco Advogados"


def separar_partes(destinatarios: list[dict]) -> tuple[str, str]:
    """Separa os destinatários em polo ativo e polo passivo, unindo os nomes
    de cada polo com "; ". O DJEN usa valores como 'A' (ativo) e 'P' (passivo)
    no campo `polo` — caso o valor não seja reconhecido, o nome entra em
    nenhum dos dois e deve ser conferido manualmente."""
    ativos, passivos = [], []
    for d in destinatarios:
        nome = d.get("nome", "").strip()
        polo = (d.get("polo") or "").upper()
        if not nome:
            continue
        if polo.startswith("A"):
            ativos.append(nome)
        elif polo.startswith("P"):
            passivos.append(nome)
    return "; ".join(ativos), "; ".join(passivos)


# ---------------------------------------------------------------------------
# Chamada à API do DJEN
# ---------------------------------------------------------------------------

def consultar_djen(data_consulta: datetime.date, tentativa: int = 1) -> list[dict]:
    """Consulta o DJEN para a OAB configurada, na data informada.
    Trata o rate limit (HTTP 429) esperando 60s e tentando novamente, como
    orientado pela própria documentação da API.

    Envia cabeçalhos de navegador porque o servidor do CNJ bloqueia
    requisições "genéricas" (sem User-Agent reconhecível) com HTTP 403 —
    isso foi observado na prática rodando a partir do GitHub Actions."""
    params = {
        "numeroOab": NUMERO_OAB,
        "ufOab": UF_OAB,
        "dataDisponibilizacaoInicio": data_consulta.isoformat(),
        "dataDisponibilizacaoFim": data_consulta.isoformat(),
        "itensPorPagina": 100,  # a API só aceita 5 ou 100
        "pagina": 1,
    }
    url = f"{DJEN_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Referer": "https://comunica.pje.jus.br/",
        "Origin": "https://comunica.pje.jus.br",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("items", [])
    except urllib.error.HTTPError as e:
        corpo_erro = ""
        try:
            corpo_erro = e.read().decode("utf-8", errors="replace")[:2000]
        except Exception:
            pass
        print(f"Erro HTTP {e.code} ao consultar o DJEN.", file=sys.stderr)
        if corpo_erro:
            print(f"Corpo da resposta: {corpo_erro}", file=sys.stderr)
        if e.code == 429 and tentativa <= 3:
            print(f"Rate limit atingido (429). Aguardando 60s — tentativa {tentativa}/3.")
            time.sleep(60)
            return consultar_djen(data_consulta, tentativa + 1)
        raise


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

def notion_request(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{NOTION_API}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ja_existe_no_notion(numero_comunicacao: str) -> bool:
    """Deduplicação: procura no banco por uma página cujo campo
    'Nº da comunicação' já tenha esse valor."""
    payload = {
        "filter": {
            "property": "Nº da comunicação",
            "rich_text": {"equals": str(numero_comunicacao)},
        },
        "page_size": 1,
    }
    result = notion_request("POST", f"/data_sources/{NOTION_DATABASE_ID}/query", payload)
    return len(result.get("results", [])) > 0


def montar_propriedades(item: dict) -> dict:
    disp_str = item.get("data_disponibilizacao") or item.get("datadisponibilizacao")
    disp_date = datetime.date.fromisoformat(disp_str[:10])
    publicacao, inicio_contagem = calcular_datas_prazo(disp_date)

    escritorio = classificar_escritorio(item.get("destinatarioadvogados", []))
    polo_ativo, polo_passivo = separar_partes(item.get("destinatarios", []))

    numero_processo = item.get("numeroprocessocommascara") or item.get("numero_processo", "")
    classe = item.get("nomeClasse", "")
    tribunal_sigla = item.get("siglaTribunal", "")
    teor_bruto = (item.get("texto") or "").replace("<", " <")
    # remoção simples de tags HTML para o resumo
    import re
    teor_limpo = re.sub(r"<[^>]+>", " ", teor_bruto)
    teor_limpo = re.sub(r"\s+", " ", teor_limpo).strip()[:1900]

    tribunal_map = {
        "TJRS": "TJRS", "TJSC": "TJSC",
        "TRF4": "JFRS/TRF4", "JFRS": "JFRS/TRF4",
    }
    tribunal = tribunal_map.get(tribunal_sigla, "Outro")

    titulo = f"{numero_processo} — {classe or 'Comunicação'}, DJEN {disp_date.strftime('%d/%m')}"

    props = {
        "Processo": {"title": [{"text": {"content": titulo[:200]}}]},
        "Nº do processo": {"rich_text": [{"text": {"content": numero_processo}}]},
        "Polo ativo": {"rich_text": [{"text": {"content": polo_ativo[:1900]}}]},
        "Polo passivo": {"rich_text": [{"text": {"content": polo_passivo[:1900]}}]},
        "Escritório": {"select": {"name": escritorio}},
        "Classe": {"rich_text": [{"text": {"content": classe}}]},
        "Tribunal": {"select": {"name": tribunal}},
        "Órgão julgador": {"rich_text": [{"text": {"content": item.get("nomeOrgao", "")[:1900]}}]},
        "Tipo de comunicação": {"select": {"name": item.get("tipoComunicacao", "Outro") or "Outro"}},
        "Meio": {"select": {"name": "DJEN"}},
        "Disponibilização": {"date": {"start": disp_date.isoformat()}},
        "Início da contagem": {"date": {"start": inicio_contagem.isoformat()}},
        "Andamento": {"select": {"name": "A verificar"}},
        "Nº da comunicação": {"rich_text": [{"text": {"content": str(item.get("numeroComunicacao") or item.get("hash", ""))}}]},
        "Teor resumido": {"rich_text": [{"text": {"content": teor_limpo}}]},
        "Inteiro teor": {"url": item.get("link") or None},
    }
    return props


def criar_pagina_notion(propriedades: dict):
    payload = {
        "parent": {"data_source_id": NOTION_DATABASE_ID},
        "properties": propriedades,
    }
    notion_request("POST", "/pages", payload)


# ---------------------------------------------------------------------------
# Execução principal
# ---------------------------------------------------------------------------

def main():
    # Por padrão, coleta o dia anterior. Exceção: o DJEN só publica de
    # segunda a sexta, então numa segunda-feira "ontem" seria domingo (sempre
    # vazio) — nesse caso buscamos a sexta-feira anterior.
    data_alvo_str = os.environ.get("DATA_ALVO")
    if data_alvo_str:
        data_alvo = datetime.date.fromisoformat(data_alvo_str)
    else:
        hoje = datetime.date.today()
        dias_atras = 3 if hoje.weekday() == 0 else 1  # 0 = segunda-feira
        data_alvo = hoje - datetime.timedelta(days=dias_atras)

    print(f"Consultando DJEN para OAB {NUMERO_OAB}/{UF_OAB} em {data_alvo.isoformat()}...")
    itens = consultar_djen(data_alvo)
    print(f"{len(itens)} comunicação(ões) encontrada(s).")

    novos, duplicados, erros = 0, 0, 0
    for item in itens:
        numero_comunicacao = item.get("numeroComunicacao") or item.get("hash", "")
        try:
            if ja_existe_no_notion(numero_comunicacao):
                duplicados += 1
                continue
            propriedades = montar_propriedades(item)
            criar_pagina_notion(propriedades)
            novos += 1
            print(f"  + lançado: {propriedades['Nº do processo']['rich_text'][0]['text']['content']}")
        except Exception as e:
            erros += 1
            print(f"  ! erro ao processar comunicação {numero_comunicacao}: {e}", file=sys.stderr)

    print(f"Resumo: {novos} novo(s), {duplicados} já existente(s), {erros} erro(s).")
    if erros > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
