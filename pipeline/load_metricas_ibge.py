#!/usr/bin/env python3
"""
load_metricas_ibge.py
Carrega indicadores adicionais do IBGE SIDRA para api.metricas_municipio.

Indicadores carregados:
  Censo 2022 (estáticos, ano=2022):
    taxa_envelhecimento  — índice de envelhecimento (T9756)
    razao_sexo           — homens por 100 mulheres (T9756)
    idade_mediana        — idade mediana da população (T9515)
    taxa_alfabetizacao   — % pessoas 15+ alfabetizadas (T9543)
    domicilios_internet  — % domicílios com internet (T9936)
    media_moradores      — média de moradores por domicílio (T9877)
    pop_favelas_pct      — % pop em aglomerados subnormais (T9884 / geo.municipios)
    taxa_ocupacao        — nível de ocupação 10+ (T10268 V675)

  Censo 2022 Amostra:
    renda_domiciliar_per_capita — rendimento nominal domiciliar per capita médio (T10295)
    renda_domiciliar_mediana_pc — rendimento nominal domiciliar per capita mediano (T10295)
    renda_media_trabalho        — rendimento médio do trabalho (T10280)
    renda_mediana_trabalho      — rendimento mediano do trabalho (T10280)
    media_anos_estudo           — média de anos de estudo 11+ (T10062)
    pct_superior_completo       — % superior completo 25+ (T10142)
    taxa_deficiencia            — % com deficiência 2+ (T10128)

  PAM — Produção Agrícola Municipal (anual):
    vbp_agricola_per_capita — VBP agrícola per capita em R$ (T5457+T1612 V215)

  Censo 2022 — Raça/Etnia:
    pct_indigena   — % declarou-se indígena na raça/cor (T9606 V1000093)
    pct_quilombola — % da população quilombola (T9578 V4728)

  Censo Agropecuário 2017:
    pct_agrofamiliar — % de estabelecimentos de agricultura familiar (T6773 V183)

  CEMPRE — Cadastro Central de Empresas (anual):
    empresas_por_1k — empresas e organizações por 1k hab. (T9582 V2585)

Uso:
    python load_metricas_ibge.py               # todos os indicadores
    python load_metricas_ibge.py --skip-censo  # só PAM e demais anuais
    python load_metricas_ibge.py --skip-raca --skip-agropecuario  # pula novos
    python load_metricas_ibge.py --anos-pam 2020 2021 2022
"""

import argparse
import os
import time

import psycopg2
import requests
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

SIDRA_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"


# ─── Helpers SIDRA ───────────────────────────────────────────────────────────

def list_vars(tabela: int, periodo: str = "2022",
              classificacao: str = None) -> list[dict]:
    """
    Descobre variáveis de uma tabela SIDRA fazendo uma query allxp para um
    município de exemplo (São Paulo 3550308). Retorna lista de {id, nome}.
    """
    classif = f"&classificacao={classificacao}" if classificacao else ""
    url = (
        f"{SIDRA_BASE}/{tabela}/periodos/{periodo}/variaveis/allxp"
        f"?localidades=N6[3550308]{classif}"
    )
    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        print(f"  AVISO: probe allxp tabela {tabela} → HTTP {r.status_code}")
        return []
    variaveis = []
    for entry in r.json():
        variaveis.append({
            "id":   str(entry.get("id", entry.get("variavel_id", ""))),
            "nome": entry.get("variavel", entry.get("nome", "")),
        })
    return variaveis


def find_var_id(variaveis: list[dict], *search_terms: str) -> str | None:
    """Encontra o ID da primeira variável cujo nome contém algum dos termos (case-insensitive)."""
    for var in variaveis:
        nome = var.get("nome", "").lower()
        for term in search_terms:
            if term.lower() in nome:
                return str(var["id"])
    return None


def sidra_fetch(tabela: int, variavel: int | str, classificacao: str = None,
                periodo: str = "2022") -> dict[int, float]:
    """
    Baixa dados para todos os municípios (N6[all]).
    Retorna dict {cod_municipio_7digits: valor}.
    """
    classif = f"&classificacao={classificacao}" if classificacao else ""
    url = (
        f"{SIDRA_BASE}/{tabela}/periodos/{periodo}/variaveis/{variavel}"
        f"?localidades=N6[all]{classif}"
    )
    print(f"  GET T{tabela} V{variavel} {periodo} ...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            print(f"    HTTP {r.status_code}, aguardando 10s...")
            time.sleep(10)
        except requests.exceptions.Timeout:
            print(f"    Timeout tentativa {tentativa+1}/3, aguardando 10s...")
            time.sleep(10)
    else:
        print(f"  ERRO: T{tabela} V{variavel} falhou após 3 tentativas")
        return {}

    resultado = {}
    for bloco in r.json():
        for res_item in bloco.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get(str(periodo), "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        resultado[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass
    print(f"    → {len(resultado)} municípios")
    return resultado


def upsert_metricas(rows: list[tuple], conn=None):
    """Insere/atualiza registros em api.metricas_municipio."""
    if not rows:
        print("  Sem dados para inserir.")
        return
    close_after = conn is None
    if conn is None:
        conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO api.metricas_municipio (cod_municipio, metrica, ano, valor)
                VALUES %s
                ON CONFLICT (cod_municipio, metrica, ano)
                DO UPDATE SET valor = EXCLUDED.valor
                """,
                rows,
                page_size=2000,
            )
        conn.commit()
        print(f"  Upserted {len(rows):,} registros em api.metricas_municipio")
    finally:
        if close_after:
            conn.close()


# ─── Censo 2022 — Indicadores estáticos ─────────────────────────────────────

def carregar_censo_demografico(conn):
    """T9756 — Razão de envelhecimento e razão de sexo."""
    print("\n=== T9756: Razão de envelhecimento / Razão de sexo ===")
    variaveis = list_vars(9756)
    if not variaveis:
        print("  AVISO: Sem variáveis — pulando T9756")
        return

    print(f"  Variáveis disponíveis: {[v.get('nome') for v in variaveis]}")

    # Índice/razão de envelhecimento
    var_env = find_var_id(variaveis, "envelhecimento")
    if var_env:
        dados = sidra_fetch(9756, var_env)
        rows = [(cod, "taxa_envelhecimento", 2022, v) for cod, v in dados.items()]
        upsert_metricas(rows, conn)
    else:
        print("  AVISO: Variável de envelhecimento não encontrada em T9756")

    # Razão de sexo
    var_sex = find_var_id(variaveis, "razão de sexo", "razao de sexo", "de sexo")
    if var_sex:
        dados = sidra_fetch(9756, var_sex)
        rows = [(cod, "razao_sexo", 2022, v) for cod, v in dados.items()]
        upsert_metricas(rows, conn)
    else:
        print("  AVISO: Variável de razão de sexo não encontrada em T9756")


def carregar_idade_mediana(conn):
    """T9515 V10613 — Idade mediana da população residente (Censo 2022)."""
    print("\n=== T9515: Idade mediana ===")
    url = f"{SIDRA_BASE}/9515/periodos/2022/variaveis/10613?localidades=N6[all]"
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T9515 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "idade_mediana", 2022, v) for cod, v in result.items()], conn)


def carregar_taxa_ocupacao(conn):
    """T10268 V675 — Nível de ocupação (%) das pessoas de 10 anos ou mais (Censo 2022 Amostra)."""
    print("\n=== T10268: Taxa de ocupação (10+) ===")
    url = f"{SIDRA_BASE}/10268/periodos/2022/variaveis/675?localidades=N6[all]"
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10268 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            cats = res_item.get("classificacoes", [])
            if not all(list(c.get("categoria", {}).values()) == ["Total"] for c in cats):
                continue
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "taxa_ocupacao", 2022, v) for cod, v in result.items()], conn)


def carregar_alfabetizacao(conn):
    """T9543 — Taxa de alfabetização das pessoas de 15 anos ou mais."""
    print("\n=== T9543: Taxa de alfabetização ===")
    variaveis = list_vars(9543)
    if not variaveis:
        print("  AVISO: Sem variáveis — pulando T9543")
        return

    print(f"  Variáveis disponíveis: {[v.get('nome') for v in variaveis]}")

    var_id = find_var_id(variaveis, "alfabetização", "alfabetizacao", "alfabetizada")
    if not var_id:
        # Fallback: usar qualquer variável de taxa
        var_id = find_var_id(variaveis, "taxa")
    if not var_id and variaveis:
        var_id = str(variaveis[0]["id"])

    if var_id:
        dados = sidra_fetch(9543, var_id)
        rows = [(cod, "taxa_alfabetizacao", 2022, v) for cod, v in dados.items()]
        upsert_metricas(rows, conn)
    else:
        print("  AVISO: Variável de alfabetização não encontrada em T9543")


def carregar_internet(conn):
    """
    % domicílios com acesso à internet.
    A tabela SIDRA específica para este indicador no Censo 2022 usa uma
    classificação interna de 'Domicílios particulares por acesso à internet'.
    A função tenta encontrar a variável adequada em candidatos confirmados.
    """
    print("\n=== Internet: buscando tabela SIDRA adequada ===")

    # Tabelas candidatas confirmadas para N6[all] com variável de internet
    # Atualizar com o ID correto quando confirmado via probe manual.
    candidatos = [
        # (tabela, var_busca_termo, denominador)
        # Adicionar quando o table ID correto for confirmado:
        # (XXXXX, "internet", None),
    ]

    if not candidatos:
        print("  AVISO: Tabela SIDRA para internet não confirmada — pulando.")
        print("  Para encontrar: probe tabelas 9879-9882 com classificação de internet")
        return

    for tabela, busca, _ in candidatos:
        variaveis = list_vars(tabela)
        var_id = find_var_id(variaveis, busca)
        if not var_id:
            continue
        dados = sidra_fetch(tabela, var_id)
        if dados:
            rows = [(cod, "domicilios_internet", 2022, v) for cod, v in dados.items()]
            upsert_metricas(rows, conn)
            return

    print("  Nenhuma tabela candidata funcionou para domicilios_internet")


def carregar_media_moradores(conn):
    """T9877 — Média de moradores por domicílio particular permanente."""
    print("\n=== T9877: Média de moradores ===")
    variaveis = list_vars(9877)
    if not variaveis:
        print("  AVISO: Sem variáveis — pulando T9877")
        return

    print(f"  Variáveis disponíveis: {[v.get('nome') for v in variaveis]}")

    var_id = find_var_id(variaveis, "média", "media", "moradores")
    if not var_id and variaveis:
        var_id = str(variaveis[0]["id"])

    if var_id:
        dados = sidra_fetch(9877, var_id)
        rows = [(cod, "media_moradores", 2022, v) for cod, v in dados.items()]
        upsert_metricas(rows, conn)
    else:
        print("  AVISO: Variável de moradores não encontrada em T9877")


def carregar_favelas(conn):
    """T9884 — % da população em aglomerados subnormais (favelas)."""
    print("\n=== T9884: População em aglomerados subnormais ===")
    variaveis = list_vars(9884)
    if not variaveis:
        print("  AVISO: Sem variáveis — pulando T9884")
        return

    print(f"  Variáveis disponíveis: {[v.get('nome') for v in variaveis]}")

    # Tentativa 1: % diretamente
    var_pct = find_var_id(variaveis, "%", "percentual", "proporção")
    if var_pct:
        dados = sidra_fetch(9884, var_pct)
        rows = [(cod, "pop_favelas_pct", 2022, v) for cod, v in dados.items()]
        upsert_metricas(rows, conn)
        return

    # Tentativa 2: contagem de moradores em favelas → divide por pop total
    var_count = find_var_id(variaveis, "moradores", "população", "pessoas")
    if not var_count and variaveis:
        var_count = str(variaveis[0]["id"])

    if not var_count:
        print("  AVISO: Variável de favelas não encontrada em T9884")
        return

    contagem = sidra_fetch(9884, var_count)
    if not contagem:
        return

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    rows = []
    for cod, cnt in contagem.items():
        pop = pop_map.get(cod)
        if pop and pop > 0:
            rows.append((cod, "pop_favelas_pct", 2022, cnt / pop * 100))
    print(f"  % calculado para {len(rows)} municípios")
    upsert_metricas(rows, conn)


# ─── Censo 2022 — Renda e Trabalho ───────────────────────────────────────────

def carregar_deficiencia(conn):
    """
    T10128 — Taxa de deficiência (Censo 2022 Amostra).
    V13403 = Percentual de pessoas de 2 anos ou mais com algum tipo de deficiência.
    Classificação: Total (sem filtros).
    """
    print("\n=== T10128: Taxa de deficiência ===")
    url = f"{SIDRA_BASE}/10128/periodos/2022/variaveis/13403?localidades=N6[all]"
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10128 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            cats = res_item.get("classificacoes", [])
            if not all(list(c.get("categoria", {}).values()) == ["Total"] for c in cats):
                continue
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "taxa_deficiencia", 2022, v) for cod, v in result.items()], conn)


def carregar_superior_completo(conn):
    """
    T10142 — % de pessoas de 25 anos ou mais com ensino superior completo (Censo 2022 Amostra).
    V10270 = distribuição percentual. Classificação 1568 (Nível de instrução),
    categoria 99713 = 'Superior completo'. Cor/raça = Total (86, cat 95251).
    Existência de deficiência = Total (839, cat 46583).
    """
    print("\n=== T10142: % com superior completo (25+) ===")
    url = (
        f"{SIDRA_BASE}/10142/periodos/2022/variaveis/10270"
        f"?localidades=N6[all]&classificacao=1568[99713]&classificacao=86[95251]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10142 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "pct_superior_completo", 2022, v) for cod, v in result.items()], conn)


def carregar_renda_domiciliar(conn):
    """
    T10295 — Rendimento nominal domiciliar per capita (Censo 2022 Amostra).
    V13431 = Valor médio mensal; V13534 = Valor mediano mensal.
    Classificações filtradas para Total.
    """
    print("\n=== T10295: Rendimento domiciliar per capita (Censo 2022 Amostra) ===")
    url = (
        f"{SIDRA_BASE}/10295/periodos/2022/variaveis/13431,13534"
        f"?localidades=N6[all]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10295 falhou")
        return

    media_map: dict[int, float] = {}
    mediana_map: dict[int, float] = {}
    for var_block in r.json():
        var_id = str(var_block.get("id", ""))
        for res_item in var_block.get("resultados", []):
            cats = res_item.get("classificacoes", [])
            if not all(list(c.get("categoria", {}).values()) == ["Total"] for c in cats):
                continue
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        val = float(val_str)
                        if var_id == "13431":
                            media_map[cod] = val
                        elif var_id == "13534":
                            mediana_map[cod] = val
                except (ValueError, KeyError):
                    pass

    print(f"    média → {len(media_map)} / mediana → {len(mediana_map)} municípios")
    rows = (
        [(cod, "renda_domiciliar_per_capita", 2022, v) for cod, v in media_map.items()]
        + [(cod, "renda_domiciliar_mediana_pc", 2022, v) for cod, v in mediana_map.items()]
    )
    upsert_metricas(rows, conn)


def carregar_anos_estudo(conn):
    """
    T10062 — Número médio de anos de estudo das pessoas de 11 anos ou mais (Censo 2022 Amostra).
    Variável 13285.
    """
    print("\n=== T10062: Média de anos de estudo ===")
    url = f"{SIDRA_BASE}/10062/periodos/2022/variaveis/13285?localidades=N6[all]"
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10062 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            cats = res_item.get("classificacoes", [])
            if not all(list(c.get("categoria", {}).values()) == ["Total"] for c in cats):
                continue
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    rows = [(cod, "media_anos_estudo", 2022, v) for cod, v in result.items()]
    upsert_metricas(rows, conn)


def carregar_renda_trabalho(conn):
    """
    T10280 — Rendimento nominal médio mensal do trabalho (Censo 2022 Amostra).
    Variável 13536 = Valor do rendimento nominal médio mensal de todos os trabalhos.
    Variável 13537 = Valor do rendimento nominal mediano mensal de todos os trabalhos.
    Classificação: Total (sem filtros adicionais).
    """
    print("\n=== T10280: Rendimento médio/mediano do trabalho (Censo 2022 Amostra) ===")
    url = (
        f"{SIDRA_BASE}/10280/periodos/2022/variaveis/13536,13537"
        f"?localidades=N6[all]"
    )
    print(f"  GET {url}")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            print(f"    HTTP {r.status_code}, aguardando 10s...")
            time.sleep(10)
        except requests.exceptions.Timeout:
            print(f"    Timeout tentativa {tentativa+1}/3, aguardando 10s...")
            time.sleep(10)
    else:
        print("  ERRO: T10280 falhou após 3 tentativas")
        return

    media_map: dict[int, float] = {}
    mediana_map: dict[int, float] = {}

    # Top-level structure: [{id: "13536", variavel: "...", resultados: [...]}, ...]
    for var_block in r.json():
        var_id = str(var_block.get("id", ""))
        for res_item in var_block.get("resultados", []):
            # Pegar apenas linha com todos os classificadores em "Total"
            cats = res_item.get("classificacoes", [])
            is_total = all(
                list(cat.get("categoria", {}).values()) == ["Total"]
                for cat in cats
            )
            if not is_total:
                continue
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        val = float(val_str)
                        if var_id == "13536":
                            media_map[cod] = val
                        elif var_id == "13537":
                            mediana_map[cod] = val
                except (ValueError, KeyError):
                    pass

    print(f"    média → {len(media_map)} municípios, mediana → {len(mediana_map)} municípios")

    rows = []
    for cod, v in media_map.items():
        rows.append((cod, "renda_media_trabalho", 2022, v))
    for cod, v in mediana_map.items():
        rows.append((cod, "renda_mediana_trabalho", 2022, v))
    upsert_metricas(rows, conn)


def carregar_internet(conn):
    """
    T9936 — % domicílios com conexão domiciliar à internet (Censo 2022 Amostra).
    Classificação 2072 'Existência de conexão domiciliar à Internet':
      77584 = Total, 77585 = Sim (com internet), 77586 = Não
    """
    print("\n=== T9936: Domicílios com conexão à internet ===")

    def fetch_v381(classif_param: str = "") -> dict[int, float]:
        url = (
            f"{SIDRA_BASE}/9936/periodos/2022/variaveis/381"
            f"?localidades=N6[all]{classif_param}"
        )
        print(f"  GET {url[:100]}...")
        for tentativa in range(3):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            return {}
        result: dict[int, float] = {}
        for var_block in r.json():
            for res_item in var_block.get("resultados", []):
                for serie in res_item.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val_str = serie["serie"].get("2022", "-")
                        if val_str and val_str not in ("-", "...", "X", ""):
                            result[cod] = float(val_str)
                    except (ValueError, KeyError):
                        pass
        return result

    total_map = fetch_v381()
    print(f"    Total domicílios: {len(total_map)} municípios")
    if not total_map:
        return

    # Category 77585 = "Sim" (com internet)
    com_map = fetch_v381("&classificacao=2072[77585]")
    print(f"    Com internet: {len(com_map)} municípios")
    if not com_map:
        return

    rows = []
    for cod, com in com_map.items():
        total = total_map.get(cod)
        if total and total > 0:
            rows.append((cod, "domicilios_internet", 2022, com / total * 100))
    print(f"    % calculado para {len(rows)} municípios")
    upsert_metricas(rows, conn)


# ─── Censo 2022 — População por raça/localização ─────────────────────────────

def carregar_indigena(conn):
    """
    T9606 V1000093 — % da população residente que se declarou indígena (raça/cor).
    Classificação: C86[2780]=Indígena, C2[6794]=Total, C287[100362]=Total.
    Censo 2022 — ~4825 municípios com dado.
    """
    print("\n=== T9606: % população indígena (raça/cor) ===")
    url = (
        f"{SIDRA_BASE}/9606/periodos/2022/variaveis/1000093"
        f"?localidades=N6[all]&classificacao=86[2780]|2[6794]|287[100362]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T9606 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "pct_indigena", 2022, v) for cod, v in result.items()], conn)


def carregar_quilombola(conn):
    """
    T9578 V4728 — % de pessoas quilombolas no total da população residente.
    Classificação: C2661[32776]=Total.
    Censo 2022 — ~1700 municípios com comunidades quilombolas.
    """
    print("\n=== T9578: % população quilombola ===")
    url = (
        f"{SIDRA_BASE}/9578/periodos/2022/variaveis/4728"
        f"?localidades=N6[all]&classificacao=2661[32776]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T9578 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "pct_quilombola", 2022, v) for cod, v in result.items()], conn)


# ─── Censo 2022 — Migração e Escolarização ───────────────────────────────────

def carregar_migracao(conn):
    """
    T10160 V13435 — Pessoas de 5+ anos que não residiam no município 5 anos antes.
    Classificação: C2[6794]=Total, C58[95253]=Total.
    Métrica: taxa_migracao = (imigrantes / populacao_2022) × 100.
    Censo 2022 — 5570 municípios.
    """
    print("\n=== T10160: Taxa de migração inter-municipal (Censo 2022) ===")
    url = (
        f"{SIDRA_BASE}/10160/periodos/2022/variaveis/13435"
        f"?localidades=N6[all]&classificacao=2[6794]|58[95253]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10160 falhou")
        return

    imigrantes: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        imigrantes[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    rows = []
    for cod, imig in imigrantes.items():
        pop = pop_map.get(cod)
        if pop and pop > 0:
            rows.append((cod, "taxa_migracao", 2022, imig / pop * 100))

    print(f"    {len(rows)} municípios")
    upsert_metricas(rows, conn)


def carregar_escolarizacao_1517(conn):
    """
    T10140 V12805 — Taxa de escolarização das pessoas de 15 a 17 anos de idade.
    Classificação: C86[95251]=Total raça/cor, C58[2792]=15 a 17 anos.
    Censo 2022 — 5570 municípios.
    """
    print("\n=== T10140: Taxa de escolarização 15-17 anos (Censo 2022) ===")
    url = (
        f"{SIDRA_BASE}/10140/periodos/2022/variaveis/12805"
        f"?localidades=N6[all]&classificacao=86[95251]|58[2792]"
    )
    print(f"  GET {url[:100]}...")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                break
            time.sleep(10)
        except requests.exceptions.Timeout:
            time.sleep(10)
    else:
        print("  ERRO: T10140 falhou")
        return

    result: dict[int, float] = {}
    for var_block in r.json():
        for res_item in var_block.get("resultados", []):
            for serie in res_item.get("series", []):
                try:
                    cod = int(serie["localidade"]["id"])
                    val_str = serie["serie"].get("2022", "-")
                    if val_str and val_str not in ("-", "...", "X", ""):
                        result[cod] = float(val_str)
                except (ValueError, KeyError):
                    pass

    print(f"    {len(result)} municípios")
    upsert_metricas([(cod, "taxa_escolarizacao_1517", 2022, v) for cod, v in result.items()], conn)


# ─── Censo Agropecuário 2017 — Mecanização e Crédito ─────────────────────────

def carregar_agro_mecanizacao_financiamento(conn):
    """
    Censo Agropecuário 2017:
      T6870 V1918 — Estab. com tratores (mecanização)
      T6895 V1990 — Estab. com financiamento (acesso a crédito)
    Denominador: total de estab. da T6773 V183 C829[46302].
    Métricas: pct_mecanizado, pct_financiamento (%).
    """
    print("\n=== T6870/T6895: Mecanização e Financiamento (Censo Agro 2017) ===")

    classif_total      = "829[46302]|12605[113521]"   # tipologia Total + potência Total
    classif_agro_total = "829[46302]|12559[41148]"     # tipologia Total + condição legal Total

    def fetch_n6all(tabela: int, variavel: int, classif: str) -> dict[int, float]:
        url = (
            f"{SIDRA_BASE}/{tabela}/periodos/2017/variaveis/{variavel}"
            f"?localidades=N6[all]&classificacao={classif}"
        )
        print(f"  GET T{tabela} V{variavel} ...")
        for t in range(3):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            return {}
        result: dict[int, float] = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2017", "-")
                        if val and val not in ("-", "...", "X", ""):
                            result[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        print(f"    → {len(result)} municípios")
        return result

    def fetch_6895_batched(cods: list[int]) -> dict[int, float]:
        """T6895 returns 500 for >10 municipalities — query in batches of 10."""
        BATCH = 10
        result: dict[int, float] = {}
        batches = [cods[i:i+BATCH] for i in range(0, len(cods), BATCH)]
        print(f"  GET T6895 V1990 (batches de {BATCH}, total {len(batches)}) ...")
        for i, batch in enumerate(batches):
            cod_str = ",".join(str(c) for c in batch)
            url = f"{SIDRA_BASE}/6895/periodos/2017/variaveis/1990?localidades=N6[{cod_str}]"
            for attempt in range(3):
                try:
                    r = requests.get(url, timeout=30)
                    if r.status_code == 200:
                        break
                    time.sleep(2)
                except requests.exceptions.Timeout:
                    time.sleep(2)
            else:
                continue
            try:
                d = r.json()
                if not isinstance(d, list):
                    continue
                for vb in d:
                    for ri in vb.get("resultados", []):
                        for s in ri.get("series", []):
                            try:
                                cod = int(s["localidade"]["id"])
                                val = s["serie"].get("2017", "-")
                                if val and val not in ("-", "...", "X", ""):
                                    result[cod] = float(val)
                            except (ValueError, KeyError):
                                pass
            except Exception:
                pass
            if (i + 1) % 100 == 0:
                print(f"    {i+1}/{len(batches)} lotes ({len(result)} mun. coletados)")
            time.sleep(0.3)  # be gentle with SIDRA
        print(f"    → {len(result)} municípios")
        return result

    # Total establishments (denominator — same as in carregar_censo_agropecuario)
    total_map    = fetch_n6all(6773, 183, classif_agro_total)
    tratores_map = fetch_n6all(6870, 1918, classif_total)
    # T6895 only supports up to 10 municipalities per request
    all_cods = list(total_map.keys())
    fin_map  = fetch_6895_batched(all_cods)

    rows = []
    for cod, total in total_map.items():
        if total <= 0:
            continue
        if cod in tratores_map:
            rows.append((cod, "pct_mecanizado", 2017, tratores_map[cod] / total * 100))
        if cod in fin_map:
            rows.append((cod, "pct_financiamento", 2017, fin_map[cod] / total * 100))

    n_mec = sum(1 for _, m, _, _ in rows if m == "pct_mecanizado")
    n_fin = sum(1 for _, m, _, _ in rows if m == "pct_financiamento")
    print(f"  pct_mecanizado: {n_mec} mun. | pct_financiamento: {n_fin} mun.")
    upsert_metricas(rows, conn)


# ─── CEMPRE — Cadastro Central de Empresas ────────────────────────────────────

def carregar_cempre(conn, anos: list[int]):
    """
    T9582 V2585 — Número de empresas e organizações por município.
    Classificação: C12762[0]=Total CNAE, C319[0]=Total pessoal, C12386[0]=Total ano.
    Disponível anualmente (2022-2023+). Cobertura total: 5570 municípios.
    Métrica: empresas_por_1k = (empresas / pop_2022) * 1000
    """
    print("\n=== T9582: Empresas por 1k habitantes (CEMPRE) ===")

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    for ano in anos:
        url = (
            f"{SIDRA_BASE}/9582/periodos/{ano}/variaveis/2585"
            f"?localidades=N6[all]&classificacao=12762[0]|319[0]|12386[0]"
        )
        print(f"  GET T9582 V2585 {ano} ...")
        for tentativa in range(3):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            print(f"  ERRO: T9582 {ano} falhou")
            continue

        rows = []
        for var_block in r.json():
            for res_item in var_block.get("resultados", []):
                for serie in res_item.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val_str = serie["serie"].get(str(ano), "-")
                        if val_str and val_str not in ("-", "...", "X", ""):
                            empresas = float(val_str)
                            pop = pop_map.get(cod)
                            if pop and pop > 0:
                                rows.append((cod, "empresas_por_1k", ano, empresas / pop * 1000))
                    except (ValueError, KeyError):
                        pass

        print(f"    {ano}: {len(rows)} municípios")
        upsert_metricas(rows, conn)


# ─── Censo Agropecuário 2017 ──────────────────────────────────────────────────

def carregar_censo_agropecuario(conn):
    """
    T6773 V183 — Número de estabelecimentos agropecuários (Censo Agropecuário 2017).
    Dois fetches:
      C829[46302] = Total → denominador para % agricultura familiar
      C829[46304] = Agricultura familiar - sim → numerador
    Métrica: pct_agrofamiliar = (familiar / total) * 100
    Cobertura: ~5570 municípios.
    """
    print("\n=== T6773: % Agricultura Familiar (Censo Agropecuário 2017) ===")

    classif_base = "12559[41148]|12553[46523]|834[46527]|835[46528]|12598[41141]"

    def fetch_t6773(categoria_tipologia: int) -> dict[int, float]:
        url = (
            f"{SIDRA_BASE}/6773/periodos/2017/variaveis/183"
            f"?localidades=N6[all]&classificacao=829[{categoria_tipologia}]|{classif_base}"
        )
        print(f"  GET T6773 V183 C829[{categoria_tipologia}] ...")
        for tentativa in range(3):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            print(f"  ERRO: T6773 C829[{categoria_tipologia}] falhou")
            return {}
        result: dict[int, float] = {}
        for var_block in r.json():
            for res_item in var_block.get("resultados", []):
                for serie in res_item.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val_str = serie["serie"].get("2017", "-")
                        if val_str and val_str not in ("-", "...", "X", ""):
                            result[cod] = float(val_str)
                    except (ValueError, KeyError):
                        pass
        print(f"    → {len(result)} municípios")
        return result

    total_map = fetch_t6773(46302)    # Total estabelecimentos
    familiar_map = fetch_t6773(46304) # Agricultura familiar - sim

    rows = []
    for cod, total in total_map.items():
        if total <= 0:
            continue
        familiar = familiar_map.get(cod, 0.0)
        rows.append((cod, "pct_agrofamiliar", 2017, familiar / total * 100))

    print(f"  % calculado para {len(rows)} municípios")
    upsert_metricas(rows, conn)


# ─── PAM — Produção Agrícola Municipal ───────────────────────────────────────

def carregar_mortalidade_infantil(conn, anos: list[int]):
    """
    Mortalidade infantil (óbitos < 1 ano / nascidos vivos × 1000).
    Fontes: Estatísticas do Registro Civil — IBGE.
      T2681 V343 classificacao=260[5922] → óbitos com menos de 1 ano
      T2612 V218 → nascidos vivos
    Disponível anualmente (2019-2024+).
    """
    print("\n=== Mortalidade Infantil (Registro Civil IBGE) ===")

    for ano in anos:
        # Óbitos infantis (< 1 ano)
        url_obitos = (
            f"{SIDRA_BASE}/2681/periodos/{ano}/variaveis/343"
            f"?localidades=N6[all]&classificacao=260[5922]"
        )
        print(f"  GET T2681 V343 (< 1 ano) {ano}...")
        for tentativa in range(3):
            try:
                r_ob = requests.get(url_obitos, timeout=120)
                if r_ob.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            print(f"  ERRO: T2681 {ano} falhou")
            continue

        obitos_map: dict[int, float] = {}
        for vb in r_ob.json():
            for ri in vb.get("resultados", []):
                for serie in ri.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val = serie["serie"].get(str(ano), "-")
                        if val and val not in ("-", "...", "X", ""):
                            obitos_map[cod] = float(val)
                    except (ValueError, KeyError):
                        pass

        # Nascidos vivos
        url_nasc = (
            f"{SIDRA_BASE}/2612/periodos/{ano}/variaveis/218"
            f"?localidades=N6[all]"
        )
        print(f"  GET T2612 V218 (nascidos vivos) {ano}...")
        for tentativa in range(3):
            try:
                r_na = requests.get(url_nasc, timeout=120)
                if r_na.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            print(f"  ERRO: T2612 {ano} falhou")
            continue

        nasc_map: dict[int, float] = {}
        for vb in r_na.json():
            for ri in vb.get("resultados", []):
                cats = ri.get("classificacoes", [])
                if not all(list(c.get("categoria", {}).values()) == ["Total"] for c in cats):
                    continue
                for serie in ri.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val = serie["serie"].get(str(ano), "-")
                        if val and val not in ("-", "...", "X", ""):
                            nasc_map[cod] = float(val)
                    except (ValueError, KeyError):
                        pass

        rows = []
        for cod, nascimentos in nasc_map.items():
            if nascimentos <= 0:
                continue
            obitos = obitos_map.get(cod, 0.0)
            tmi = obitos / nascimentos * 1000
            rows.append((cod, "mortalidade_infantil", ano, tmi))

        print(f"    {ano}: TMI calculada para {len(rows)} municípios"
              f" (óbitos em {len(obitos_map)}, nascimentos em {len(nasc_map)})")
        upsert_metricas(rows, conn)


def carregar_pecuaria(conn, anos: list[int]):
    """
    T74 — Valor da produção da pecuária municipal (Mil R$) per capita.
    V215 = Valor da produção. Disponível anualmente (2020-2024+).
    """
    print("\n=== T74: Pecuária — Valor da Produção per capita ===")

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    for ano in anos:
        dados = sidra_fetch(74, 215, periodo=str(ano))
        if not dados:
            continue
        rows = []
        for cod, vbp_milhares in dados.items():
            pop = pop_map.get(cod)
            if pop and pop > 0:
                rows.append((cod, "vbp_pecuaria_per_capita", ano, (vbp_milhares * 1000) / pop))
        print(f"    {ano}: per capita para {len(rows)} municípios")
        upsert_metricas(rows, conn)


def carregar_setor_pib(conn, anos: list[int]):
    """
    T5938 — Participação setorial no PIB municipal (%).
    V516 = agropecuária, V519 = indústria, V6574 = serviços excl. adm pública.
    Disponível para 2018-2021 (dado municipal com defasagem ~2 anos).
    """
    print("\n=== T5938: Participação setorial no PIB municipal ===")
    varmap = {"516": "pct_pib_agropecuaria", "519": "pct_pib_industria", "6574": "pct_pib_servicos"}

    for ano in anos:
        url = (
            f"{SIDRA_BASE}/5938/periodos/{ano}/variaveis/516,519,6574"
            f"?localidades=N6[all]"
        )
        print(f"  GET T5938 V516,519,6574 {ano} ...")
        for tentativa in range(3):
            try:
                r = requests.get(url, timeout=120)
                if r.status_code == 200:
                    break
                time.sleep(10)
            except requests.exceptions.Timeout:
                time.sleep(10)
        else:
            print(f"  ERRO: T5938 {ano} falhou")
            continue

        rows = []
        for var_block in r.json():
            var_id = str(var_block.get("id", ""))
            metrica = varmap.get(var_id)
            if not metrica:
                continue
            for res_item in var_block.get("resultados", []):
                for serie in res_item.get("series", []):
                    try:
                        cod = int(serie["localidade"]["id"])
                        val_str = serie["serie"].get(str(ano), "-")
                        if val_str and val_str not in ("-", "...", "X", ""):
                            rows.append((cod, metrica, ano, float(val_str)))
                    except (ValueError, KeyError):
                        pass

        n_by_metrica = {}
        for _, m, _, _ in rows:
            n_by_metrica[m] = n_by_metrica.get(m, 0) + 1
        print(f"    {ano}: {n_by_metrica}")
        upsert_metricas(rows, conn)


def carregar_desemprego(conn):
    """
    T9517 V1641 — Taxa de desemprego (Censo 2022).
    Fórmula: desocupados / força de trabalho × 100.
    C629: 32386=força de trabalho, 32446=desocupada.
    Cobre 5570 municípios.
    """
    print("\n=== T9517: Taxa de desemprego — Censo 2022 ===")

    params_base = "2[6794]|86[95251]|1568[120704]"

    def fetch_cat(cat_id: int) -> dict[int, float]:
        url = (
            f"{SIDRA_BASE}/9517/periodos/2022/variaveis/1641"
            f"?localidades=N6[all]&classificacao=629[{cat_id}]|{params_base}"
        )
        r = requests.get(url, timeout=120)
        result = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            result[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        return result

    forca = fetch_cat(32386)  # força de trabalho
    desoc = fetch_cat(32446)  # desocupados

    print(f"  força de trabalho: {len(forca)} mun. | desocupados: {len(desoc)} mun.")
    rows = []
    for cod, ft in forca.items():
        if ft > 0 and cod in desoc:
            rows.append((cod, "taxa_desemprego", 2022, desoc[cod] / ft * 100))
    print(f"  taxa_desemprego: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_pendular(conn):
    """
    T10329 V1013373 — % trabalhadores que trabalham em outro município (Censo 2022).
    C469[12188] = Outro município, C2[6794] = Total sexo, C386[9680] = Total renda.
    Cobre 5570 municípios.
    """
    print("\n=== T10329: Taxa de pendularidade — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/10329/periodos/2022/variaveis/1013373"
        f"?localidades=N6[all]&classificacao=469[12188]|2[6794]|386[9680]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "taxa_pendular", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  taxa_pendular: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_informalidade(conn):
    """
    T10261 V1004090 — Taxa de informalidade no trabalho (Censo 2022).
    Soma das categorias informais:
      C11913[31723] = setor privado sem carteira
      C11913[79368] = doméstico sem carteira
      C11913[45937] = conta própria sem CNPJ
      C11913[31731] = trabalhador familiar auxiliar
    Cobre 5570 municípios.
    """
    print("\n=== T10261: Taxa de informalidade — Censo 2022 ===")

    categorias_informais = [31723, 79368, 45937, 31731]
    params_base = "2[6794]|86[95251]"

    acumulador: dict[int, float] = {}
    for cat_id in categorias_informais:
        url = (
            f"{SIDRA_BASE}/10261/periodos/2022/variaveis/1004090"
            f"?localidades=N6[all]&classificacao=11913[{cat_id}]|{params_base}"
        )
        r = requests.get(url, timeout=120)
        count = 0
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            acumulador[cod] = acumulador.get(cod, 0.0) + float(val)
                            count += 1
                    except (ValueError, KeyError):
                        pass
        print(f"  C11913[{cat_id}]: {count} mun.")

    rows = [(cod, "taxa_informalidade", 2022, v) for cod, v in acumulador.items()]
    print(f"  taxa_informalidade: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_baixa_renda(conn):
    """
    T10296 V1013604 — % moradores com renda domiciliar per capita até 1/2 SM (Censo 2022).
    Soma de C386[9681] (até 1/4 SM) + C386[9682] (1/4 a 1/2 SM).
    Proxy de pobreza moderada. Cobre 5553–5570 municípios.
    """
    print("\n=== T10296: Baixa renda — Censo 2022 ===")
    params_base = "2[6794]|86[95251]"
    acum: dict[int, float] = {}

    for cat_id, label in [(9681, "≤1/4 SM"), (9682, "1/4-1/2 SM")]:
        url = (
            f"{SIDRA_BASE}/10296/periodos/2022/variaveis/1013604"
            f"?localidades=N6[all]&classificacao={params_base}|386[{cat_id}]"
        )
        r = requests.get(url, timeout=120)
        count = 0
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            acum[cod] = acum.get(cod, 0.0) + float(val)
                            count += 1
                    except (ValueError, KeyError):
                        pass
        print(f"  C386[{cat_id}] ({label}): {count} mun.")

    rows = [(cod, "pct_baixa_renda", 2022, v) for cod, v in acum.items()]
    print(f"  pct_baixa_renda: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_renda_trabalho(conn):
    """
    T10297 V13504 — % do rendimento domiciliar proveniente de trabalho (Censo 2022).
    C11308[79451] = Rendimento de todos os trabalhos (% do total).
    Alta proporção = dependência de trabalho; baixa = transferências/previdência.
    Cobre 5570 municípios.
    """
    print("\n=== T10297: % renda do trabalho — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/10297/periodos/2022/variaveis/13504"
        f"?localidades=N6[all]&classificacao=11308[79451]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "pct_renda_trabalho", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  pct_renda_trabalho: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_media_filhos(conn):
    """
    T10078 V13316/V13315 — Média de filhos nascidos vivos por mulher 12+ (Censo 2022).
    V13316 = total filhos tidos nascidos vivos, V13315 = total mulheres 12+.
    C12232[58896]=Total grupos idade, C1568[120704]=Total instrução, C12293[58898]=Total raça.
    Paridade acumulada — reflete padrão histórico de fecundidade. 5570 municípios. Média ~2.03.
    """
    print("\n=== T10078: Média de filhos por mulher — Censo 2022 ===")
    base = (
        f"{SIDRA_BASE}/10078/periodos/2022/variaveis/{{var}}"
        f"?localidades=N6[all]&classificacao=12232[58896]|1568[120704]|12293[58898]"
    )

    def fetch_var(var):
        r = requests.get(base.format(var=var), timeout=120)
        vals = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        v = s["serie"].get("2022", "-")
                        if v and v not in ("-", "...", "X", ""):
                            vals[cod] = float(v)
                    except (ValueError, KeyError):
                        pass
        return vals

    mulheres = fetch_var(13315)
    filhos   = fetch_var(13316)
    rows = [
        (cod, "media_filhos_mulher", 2022, filhos[cod] / mulheres[cod])
        for cod in mulheres
        if cod in filhos and mulheres[cod] > 0
    ]
    print(f"  media_filhos_mulher: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_monoparental(conn):
    """
    T9882 V1000800 — % domicílios monoparentais: responsável sem cônjuge com filhos (Censo 2022).
    C1887[72607] = responsável sem cônjuge com filho(s)/enteado(s), C11561[100679]=Total sexo.
    Indica vulnerabilidade familiar. 5570 municípios. Média ~14.5%.
    """
    print("\n=== T9882: % domicílios monoparentais — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/9882/periodos/2022/variaveis/1000800"
        f"?localidades=N6[all]&classificacao=1887[72607]|11561[100679]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "domicilios_monoparentais", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  domicilios_monoparentais: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_domicilios_alugados(conn):
    """
    T9929 V1000381 — % domicílios alugados (Censo 2022).
    C63[1055]=Alugado, C1986[73103]=Total moradores 15+.
    Proxy de dinamismo imobiliário e acessibilidade à moradia. 5570 municípios. Média ~15.7%.
    """
    print("\n=== T9929: % domicílios alugados — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/9929/periodos/2022/variaveis/1000381"
        f"?localidades=N6[all]&classificacao=63[1055]|1986[73103]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", "", ".."):
                        rows.append((cod, "domicilios_alugados", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  domicilios_alugados: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_chefia_feminina(conn):
    """
    T9879 V1000800 — % domicílios com pessoa responsável mulher (Censo 2022).
    C460[45902]=Total espécie, C68[9902]=Total moradores,
    C11561[100681]=Mulheres, C12237[104570]=Total raça, C11562[72593]=Total idade.
    Cobre 5570 municípios. Média ~44.9%.
    """
    print("\n=== T9879: % chefia feminina — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/9879/periodos/2022/variaveis/1000800"
        f"?localidades=N6[all]&classificacao=460[45902]|68[9902]|11561[100681]|12237[104570]|11562[72593]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "pct_chefia_feminina", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  pct_chefia_feminina: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_domicilios_maquina(conn):
    """
    T9935 V1000381 — % domicílios com máquina de lavar roupa (Censo 2022).
    C1977[73092]=Sim, C63[95826]=Total condição, C125[2932]=Total tipo.
    Proxy de capacidade de consumo / nível de renda. Cobre 5570 municípios. Média ~53.8%.
    """
    print("\n=== T9935: % domicílios com máquina de lavar — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/9935/periodos/2022/variaveis/1000381"
        f"?localidades=N6[all]&classificacao=1977[73092]|63[95826]|125[2932]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "domicilios_maquina_lavar", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  domicilios_maquina_lavar: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_superlotacao(conn):
    """
    T9933 V1000381 — % domicílios com >3 moradores por dormitório (Censo 2022).
    C1975[73090]=Mais de 3 moradores, C63[95826]=Total, C125[2932]=Total tipo.
    Indicador de precariedade habitacional. Cobre ~5484 municípios. Média ~2.3%.
    """
    print("\n=== T9933: % superlotação domiciliar — Censo 2022 ===")
    url = (
        f"{SIDRA_BASE}/9933/periodos/2022/variaveis/1000381"
        f"?localidades=N6[all]&classificacao=1975[73090]|63[95826]|125[2932]"
    )
    r = requests.get(url, timeout=120)
    rows = []
    for vb in r.json():
        for ri in vb.get("resultados", []):
            for s in ri.get("series", []):
                try:
                    cod = int(s["localidade"]["id"])
                    val = s["serie"].get("2022", "-")
                    if val and val not in ("-", "...", "X", ""):
                        rows.append((cod, "superlotacao_domiciliar", 2022, float(val)))
                except (ValueError, KeyError):
                    pass
    print(f"  superlotacao_domiciliar: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_pct_urbano(conn):
    """
    T9923 V93 — % população residente em área urbana (Censo 2022).
    C1[1]=Urbana, C1[6795]=Total.
    Indica nível de urbanização do município. Cobre 5570 municípios.
    """
    print("\n=== T9923: % população urbana — Censo 2022 ===")

    def fetch_cat(cat_id):
        url = (
            f"{SIDRA_BASE}/9923/periodos/2022/variaveis/93"
            f"?localidades=N6[all]&classificacao=1[{cat_id}]"
        )
        r = requests.get(url, timeout=120)
        result = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            result[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        print(f"    C1[{cat_id}]: {len(result)} mun.")
        return result

    total_map  = fetch_cat(6795)  # Total
    urbana_map = fetch_cat(1)     # Urbana

    rows = []
    for cod, total in total_map.items():
        if total > 0 and cod in urbana_map:
            rows.append((cod, "pct_urbano", 2022, urbana_map[cod] / total * 100))
    print(f"  pct_urbano: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_paredes_alvenaria(conn):
    """
    T9928 V381 — % domicílios com paredes de alvenaria (Censo 2022).
    C137[73073]=alvenaria com revestimento + C137[12194]=alvenaria sem revestimento.
    Proxy de qualidade habitacional. Cobre 5570 municípios.
    C63[95826]=Total condição, C125[2932]=Total tipo.
    """
    print("\n=== T9928: % domicílios com paredes de alvenaria — Censo 2022 ===")

    classif_base = "63[95826]|125[2932]"

    def fetch_cat(cat_id):
        url = (
            f"{SIDRA_BASE}/9928/periodos/2022/variaveis/381"
            f"?localidades=N6[all]&classificacao=137[{cat_id}]|{classif_base}"
        )
        r = requests.get(url, timeout=120)
        result = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            result[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        print(f"    C137[{cat_id}]: {len(result)} mun.")
        return result

    total_map    = fetch_cat(13233)  # Total
    alv_rev_map  = fetch_cat(73073)  # Alvenaria com revestimento
    alv_sem_map  = fetch_cat(12194)  # Alvenaria sem revestimento

    rows = []
    for cod, total in total_map.items():
        if total > 0:
            alv = alv_rev_map.get(cod, 0.0) + alv_sem_map.get(cod, 0.0)
            rows.append((cod, "pct_alvenaria", 2022, alv / total * 100))
    print(f"  pct_alvenaria: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_banheiro_exclusivo(conn):
    """
    T9397 V382 — % moradores em domicílios com banheiro de uso exclusivo (Censo 2022).
    C458[12032]=Tinham banheiro de uso exclusivo, C458[72117]=Total.
    C58[95253]=Total idade, C86[95251]=Total raça, C11558[46292]=Total esgoto.
    Indica qualidade sanitária habitacional. Cobre 5570 municípios.
    """
    print("\n=== T9397: % moradores com banheiro exclusivo — Censo 2022 ===")

    classif_base = "58[95253]|86[95251]|11558[46292]"

    def fetch_cat(cat_id):
        url = (
            f"{SIDRA_BASE}/9397/periodos/2022/variaveis/382"
            f"?localidades=N6[all]&classificacao=458[{cat_id}]|{classif_base}"
        )
        r = requests.get(url, timeout=120)
        result = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get("2022", "-")
                        if val and val not in ("-", "...", "X", ""):
                            result[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        print(f"    C458[{cat_id}]: {len(result)} mun.")
        return result

    total_map    = fetch_cat(72117)  # Total
    banheiro_map = fetch_cat(12032)  # Com banheiro exclusivo

    rows = []
    for cod, total in total_map.items():
        if total > 0 and cod in banheiro_map:
            rows.append((cod, "pct_banheiro_exclusivo", 2022, banheiro_map[cod] / total * 100))
    print(f"  pct_banheiro_exclusivo: {len(rows)} mun.")
    upsert_metricas(rows, conn)


def carregar_nupcialidade(conn, anos: list[int]):
    """
    Registro Civil — Taxa de nupcialidade (casamentos por 1000 hab.).
    T4406 V4993 C236[0]|C664[0]|C665[0]|C666[0]|C667[0] — total anual, todos estados civis e idades.
    N6[all] timed out; fetched UF-by-UF (N6 in N3[uf]).
    Cobre ~5000 municípios (municípios muito pequenos sem registro retornam '-').
    """
    UFS = [11,12,13,14,15,16,17,21,22,23,24,25,26,27,28,29,31,32,33,35,41,42,43,50,51,52,53]
    CLASSIF = "236[0]|664[0]|665[0]|666[0]|667[0]"

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    print("\n=== Registro Civil: Taxa de Nupcialidade (T4406) ===")
    for ano in anos:
        print(f"\n  Ano {ano}:")
        count_map: dict[int, float] = {}
        for uf in UFS:
            url = (
                f"{SIDRA_BASE}/4406/periodos/{ano}/variaveis/4993"
                f"?localidades=N6[in N3[{uf}]]&classificacao={CLASSIF}"
            )
            r = requests.get(url, timeout=60)
            if r.status_code != 200:
                print(f"    UF {uf}: HTTP {r.status_code} — pulando")
                continue
            for vb in r.json():
                for ri in vb.get("resultados", []):
                    for s in ri.get("series", []):
                        try:
                            cod = int(s["localidade"]["id"])
                            val = s["serie"].get(str(ano), "-")
                            if val and val not in ("-", "...", "X", ""):
                                count_map[cod] = float(val)
                        except (ValueError, KeyError):
                            pass
        rows = []
        for cod, n_casamentos in count_map.items():
            pop = pop_map.get(cod)
            if not pop or pop <= 0:
                continue
            rows.append((cod, "taxa_nupcialidade", ano, n_casamentos / pop * 1000))
        print(f"    taxa_nupcialidade: {len(rows)} municípios")
        upsert_metricas(rows, conn)


def carregar_divorcialidade(conn, anos: list[int]):
    """
    Registro Civil — Taxa de divorcialidade (divórcios em 1ª instância por 1000 hab.).
    T5929 V231 C270[0]|C271[0] — total anual, todos tipos de família e número de filhos.
    N6[all] funciona em ~11s.
    """
    CLASSIF = "270[0]|271[0]"

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    print("\n=== Registro Civil: Taxa de Divorcialidade (T5929) ===")
    for ano in anos:
        url = (
            f"{SIDRA_BASE}/5929/periodos/{ano}/variaveis/231"
            f"?localidades=N6[all]&classificacao={CLASSIF}"
        )
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            print(f"  Ano {ano}: HTTP {r.status_code} — pulando")
            continue
        count_map: dict[int, float] = {}
        for vb in r.json():
            for ri in vb.get("resultados", []):
                for s in ri.get("series", []):
                    try:
                        cod = int(s["localidade"]["id"])
                        val = s["serie"].get(str(ano), "-")
                        if val and val not in ("-", "...", "X", ""):
                            count_map[cod] = float(val)
                    except (ValueError, KeyError):
                        pass
        rows = []
        for cod, n_divorcios in count_map.items():
            pop = pop_map.get(cod)
            if not pop or pop <= 0:
                continue
            rows.append((cod, "taxa_divorcialidade", ano, n_divorcios / pop * 1000))
        print(f"  Ano {ano}: {len(rows)} municípios")
        upsert_metricas(rows, conn)


def carregar_pam(conn, anos: list[int]):
    """
    PAM — Valor Bruto da Produção agrícola per capita.
    T5457 V215 = lavouras permanentes + T1612 V215 = lavouras temporárias.
    Os dois são somados para dar o VBP total da lavoura (Mil Reais → R$ per capita).
    """
    print("\n=== PAM: Valor Bruto da Produção (permanentes T5457 + temporárias T1612) ===")

    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    for ano in anos:
        print(f"\n  Ano {ano}:")
        perm = sidra_fetch(5457, 215, periodo=str(ano))   # lavouras permanentes
        temp = sidra_fetch(1612, 215, periodo=str(ano))   # lavouras temporárias

        # Soma os dois (municípios com apenas um tipo de lavoura também entram)
        todos = set(perm) | set(temp)
        rows = []
        for cod in todos:
            pop = pop_map.get(cod)
            if not pop or pop <= 0:
                continue
            vbp_total = perm.get(cod, 0.0) + temp.get(cod, 0.0)
            rows.append((cod, "vbp_agricola_per_capita", ano, (vbp_total * 1000) / pop))
        print(f"    Per capita calculado para {len(rows)} municípios")
        upsert_metricas(rows, conn)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Carrega métricas IBGE em api.metricas_municipio")
    parser.add_argument("--skip-censo", action="store_true",
                        help="Pula os indicadores estáticos do Censo 2022")
    parser.add_argument("--skip-pam", action="store_true",
                        help="Pula a PAM (Produção Agrícola Municipal)")
    parser.add_argument("--anos-pam", nargs="+", type=int,
                        default=[2019, 2020, 2021, 2022, 2023],
                        help="Anos para baixar dados da PAM (padrão: 2019-2023)")
    parser.add_argument("--skip-pib-setor", action="store_true",
                        help="Pula as participações setoriais do PIB (T5938)")
    parser.add_argument("--anos-pib-setor", nargs="+", type=int,
                        default=[2018, 2019, 2020, 2021],
                        help="Anos para PIB setorial (padrão: 2018-2021)")
    parser.add_argument("--skip-pecuaria", action="store_true",
                        help="Pula a Pecuária Municipal (T74)")
    parser.add_argument("--anos-pecuaria", nargs="+", type=int,
                        default=[2020, 2021, 2022, 2023],
                        help="Anos para pecuária (padrão: 2020-2023)")
    parser.add_argument("--skip-infantil", action="store_true",
                        help="Pula a mortalidade infantil (T2681/T2612)")
    parser.add_argument("--anos-infantil", nargs="+", type=int,
                        default=[2019, 2020, 2021, 2022, 2023],
                        help="Anos para mortalidade infantil (padrão: 2019-2023)")
    parser.add_argument("--skip-cempre", action="store_true",
                        help="Pula o CEMPRE (empresas por mil hab., T9582)")
    parser.add_argument("--anos-cempre", nargs="+", type=int,
                        default=[2022, 2023],
                        help="Anos para CEMPRE (padrão: 2022-2023)")
    parser.add_argument("--skip-raca", action="store_true",
                        help="Pula os indicadores de raça/etnia (indígena, quilombola)")
    parser.add_argument("--skip-agropecuario", action="store_true",
                        help="Pula o Censo Agropecuário 2017 (% agricultura familiar)")
    parser.add_argument("--skip-agro-extra", action="store_true",
                        help="Pula mecanização e financiamento agropecuário (T6870/T6895)")
    parser.add_argument("--skip-migracao", action="store_true",
                        help="Pula a taxa de migração (T10160)")
    parser.add_argument("--skip-escolarizacao", action="store_true",
                        help="Pula a taxa de escolarização 15-17 anos (T10140)")
    parser.add_argument("--skip-desemprego", action="store_true",
                        help="Pula a taxa de desemprego (T9517)")
    parser.add_argument("--skip-pendular", action="store_true",
                        help="Pula a taxa de pendularidade (T10329)")
    parser.add_argument("--skip-informalidade", action="store_true",
                        help="Pula a taxa de informalidade (T10261)")
    parser.add_argument("--skip-baixa-renda", action="store_true",
                        help="Pula % baixa renda (T10296)")
    parser.add_argument("--skip-renda-trabalho", action="store_true",
                        help="Pula % renda do trabalho (T10297)")
    parser.add_argument("--skip-media-filhos", action="store_true",
                        help="Pula média de filhos por mulher (T10078)")
    parser.add_argument("--skip-monoparental", action="store_true",
                        help="Pula % domicílios monoparentais (T9882)")
    parser.add_argument("--skip-alugados", action="store_true",
                        help="Pula % domicílios alugados (T9929)")
    parser.add_argument("--skip-chefia-feminina", action="store_true",
                        help="Pula % chefia feminina (T9879)")
    parser.add_argument("--skip-maquina-lavar", action="store_true",
                        help="Pula % domicílios com máquina de lavar (T9935)")
    parser.add_argument("--skip-superlotacao", action="store_true",
                        help="Pula % superlotação domiciliar (T9933)")
    parser.add_argument("--skip-pct-urbano", action="store_true",
                        help="Pula % população urbana (T9923)")
    parser.add_argument("--skip-alvenaria", action="store_true",
                        help="Pula % domicílios com paredes de alvenaria (T9928)")
    parser.add_argument("--skip-banheiro", action="store_true",
                        help="Pula % moradores com banheiro exclusivo (T9397)")
    parser.add_argument("--skip-nupcialidade", action="store_true",
                        help="Pula taxa de nupcialidade (RC T4406)")
    parser.add_argument("--anos-nupcialidade", nargs="+", type=int,
                        default=[2018, 2019, 2020, 2021, 2022, 2023, 2024],
                        help="Anos para nupcialidade (padrão: 2018-2024)")
    parser.add_argument("--skip-divorcialidade", action="store_true",
                        help="Pula taxa de divorcialidade (RC T5929)")
    parser.add_argument("--anos-divorcialidade", nargs="+", type=int,
                        default=[2018, 2019, 2020, 2021, 2022, 2023, 2024],
                        help="Anos para divorcialidade (padrão: 2018-2024)")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        if not args.skip_censo:
            print("\n──── Censo 2022 — Indicadores Demográficos ────")
            carregar_censo_demografico(conn)
            carregar_idade_mediana(conn)
            carregar_alfabetizacao(conn)
            carregar_internet(conn)
            carregar_media_moradores(conn)
            carregar_favelas(conn)
            print("\n──── Censo 2022 Amostra — Trabalho ────")
            carregar_taxa_ocupacao(conn)
            print("\n──── Censo 2022 Amostra — Renda e Trabalho ────")
            carregar_renda_domiciliar(conn)
            carregar_anos_estudo(conn)
            carregar_renda_trabalho(conn)
            carregar_deficiencia(conn)
            carregar_superior_completo(conn)

        if not args.skip_raca:
            print("\n──── Censo 2022 — Raça/Etnia ────")
            carregar_indigena(conn)
            carregar_quilombola(conn)

        if not args.skip_agropecuario:
            print("\n──── Censo Agropecuário 2017 ────")
            carregar_censo_agropecuario(conn)

        if not args.skip_agro_extra:
            carregar_agro_mecanizacao_financiamento(conn)

        if not args.skip_migracao:
            print("\n──── Censo 2022 — Migração e Escolarização ────")
            carregar_migracao(conn)

        if not args.skip_escolarizacao:
            carregar_escolarizacao_1517(conn)

        if not args.skip_desemprego:
            print("\n──── Censo 2022 — Mercado de Trabalho ────")
            carregar_desemprego(conn)

        if not args.skip_pendular:
            carregar_pendular(conn)

        if not args.skip_informalidade:
            carregar_informalidade(conn)

        if not args.skip_baixa_renda:
            print("\n──── Censo 2022 — Renda e Pobreza ────")
            carregar_baixa_renda(conn)

        if not args.skip_renda_trabalho:
            carregar_renda_trabalho(conn)

        if not args.skip_media_filhos:
            print("\n──── Censo 2022 — Fecundidade ────")
            carregar_media_filhos(conn)

        if not args.skip_monoparental:
            print("\n──── Censo 2022 — Estrutura Familiar ────")
            carregar_monoparental(conn)

        if not args.skip_alugados:
            print("\n──── Censo 2022 — Condição de Ocupação ────")
            carregar_domicilios_alugados(conn)

        if not args.skip_chefia_feminina:
            print("\n──── Censo 2022 — Domicílios ────")
            carregar_chefia_feminina(conn)

        if not args.skip_maquina_lavar:
            carregar_domicilios_maquina(conn)

        if not args.skip_superlotacao:
            carregar_superlotacao(conn)

        if not args.skip_pct_urbano:
            print("\n──── Censo 2022 — Urbanização ────")
            carregar_pct_urbano(conn)

        if not args.skip_alvenaria:
            print("\n──── Censo 2022 — Qualidade Habitacional ────")
            carregar_paredes_alvenaria(conn)

        if not args.skip_banheiro:
            carregar_banheiro_exclusivo(conn)

        if not args.skip_nupcialidade:
            print("\n──── Registro Civil — Nupcialidade e Divorcialidade ────")
            carregar_nupcialidade(conn, args.anos_nupcialidade)

        if not args.skip_divorcialidade:
            if args.skip_nupcialidade:
                print("\n──── Registro Civil — Nupcialidade e Divorcialidade ────")
            carregar_divorcialidade(conn, args.anos_divorcialidade)

        if not args.skip_cempre:
            carregar_cempre(conn, args.anos_cempre)

        if not args.skip_infantil:
            carregar_mortalidade_infantil(conn, args.anos_infantil)

        if not args.skip_pecuaria:
            carregar_pecuaria(conn, args.anos_pecuaria)

        if not args.skip_pib_setor:
            carregar_setor_pib(conn, args.anos_pib_setor)

        if not args.skip_pam:
            carregar_pam(conn, args.anos_pam)

    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Execute para verificar:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,2) AS media")
    print("  FROM api.metricas_municipio GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
