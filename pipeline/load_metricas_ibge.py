#!/usr/bin/env python3
"""
load_metricas_ibge.py
Carrega indicadores adicionais do IBGE SIDRA para api.metricas_municipio.

Indicadores carregados:
  Censo 2022 (estáticos, ano=2022):
    taxa_envelhecimento  — índice de envelhecimento (T9756)
    razao_sexo           — homens por 100 mulheres (T9756)
    taxa_alfabetizacao   — % pessoas 15+ alfabetizadas (T9543)
    domicilios_internet  — % domicílios com internet (T9720 / T6803)
    media_moradores      — média de moradores por domicílio (T9877)
    pop_favelas_pct      — % pop em aglomerados subnormais (T9884 / geo.municipios)

  PAM — Produção Agrícola Municipal (anual):
    vbp_agricola_per_capita — VBP agrícola per capita em R$ (T5457 V215)

Uso:
    python load_metricas_ibge.py               # todos os indicadores
    python load_metricas_ibge.py --skip-censo  # só PAM
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


# ─── PAM — Produção Agrícola Municipal ───────────────────────────────────────

def carregar_pam(conn, anos: list[int]):
    """T5457 — Valor Bruto da Produção agrícola (lavouras permanentes)."""
    print("\n=== T5457: PAM — Valor Bruto da Produção (lavouras permanentes) ===")

    # Verificar variáveis disponíveis
    variaveis = list_vars(5457)
    var_desc = [str(v.get("id")) + "=" + v.get("nome", "") for v in variaveis[:6]]
    print(f"  Variáveis disponíveis: {var_desc}")

    var_id = find_var_id(variaveis, "valor da produção", "valor bruto", "vbp")
    if not var_id:
        var_id = find_var_id(variaveis, "valor")
    if not var_id and variaveis:
        var_id = str(variaveis[0]["id"])
        print(f"  Usando primeira variável disponível: {var_id}")

    if not var_id:
        print("  AVISO: Variável VBP não encontrada em T5457")
        return

    # VBP de lavouras temporárias também (T5457 cobre permanentes, T5457 é PAM completo)
    # Tentar também T1612 para lavouras temporárias
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        pop_map = {row[0]: row[1] for row in cur.fetchall()}

    for ano in anos:
        print(f"\n  Ano {ano}:")
        dados = sidra_fetch(5457, var_id, periodo=str(ano))
        if not dados:
            continue

        rows = []
        for cod, vbp_milhares in dados.items():
            pop = pop_map.get(cod)
            if pop and pop > 0:
                # VBP em Mil Reais → R$ per capita
                vbp_per_capita = (vbp_milhares * 1000) / pop
                rows.append((cod, "vbp_agricola_per_capita", ano, vbp_per_capita))
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
                        default=[2019, 2020, 2021, 2022],
                        help="Anos para baixar dados da PAM (padrão: 2019-2022)")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        if not args.skip_censo:
            print("\n──── Censo 2022 — Indicadores Demográficos ────")
            carregar_censo_demografico(conn)
            carregar_alfabetizacao(conn)
            carregar_internet(conn)
            carregar_media_moradores(conn)
            carregar_favelas(conn)

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
