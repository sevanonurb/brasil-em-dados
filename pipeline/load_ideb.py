"""
load_ideb.py
Carrega dados do IDEB (Índice de Desenvolvimento da Educação Básica) — INEP.

Baixa planilhas Excel do portal INEP para os anos disponíveis (2005–2023, ímpares).
Extrai IDEB de anos iniciais e finais do ensino fundamental por município.

Uso:
    python load_ideb.py                  # todos os anos 2005–2023
    python load_ideb.py --anos 2019 2021 2023

URLS INEP (padrão estável):
    https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download/
    {ano}/divulgacao_anos_iniciais_municipios_{ano}.xlsx
    {ano}/divulgacao_anos_finais_municipios_{ano}.xlsx

Resultado: educacao.ideb_municipios (cod_municipio 7 dígitos IBGE, por ano)
"""

import argparse
import io
import os
import time
import urllib3

import psycopg2
import pandas as pd
import requests
from psycopg2.extras import execute_values

# O servidor do INEP (download.inep.gov.br) usa certificado sem CA reconhecida
# no bundle padrão do container. Suprime o aviso para não poluir o log.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

INEP_BASE = "https://download.inep.gov.br/educacao_basica/portal_ideb/planilhas_para_download"

# Anos em que o IDEB foi divulgado (bienal, a partir de 2005)
ANOS_IDEB = [2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021, 2023]

# Nomes alternativos para a coluna IDEB nas planilhas INEP (variam por ano)
IDEB_COL_NOMES = ["IDEB", "VL_OBSERVADO_2023", "NOTA_IDEB", "ideb"]

# Nomes alternativos para código do município (7 dígitos IBGE)
MUN_COL_NOMES = ["CO_MUNICIPIO", "id_municipio", "COD_MUN", "CODMUNICIPIO"]


def baixar_excel(url: str) -> pd.DataFrame | None:
    """Baixa arquivo Excel e retorna DataFrame, ou None em caso de erro."""
    print(f"  GET {url}")
    for tentativa in range(3):
        try:
            r = requests.get(url, timeout=120, verify=False)
            if r.status_code == 200:
                return pd.read_excel(io.BytesIO(r.content), header=9)
            if r.status_code == 404:
                print(f"  404 — arquivo não encontrado: {url}")
                return None
            print(f"  HTTP {r.status_code} — aguardando 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"  ERRO: {e}")
            time.sleep(5)
    return None


def extrair_ideb_municipios(df: pd.DataFrame, ano: int) -> dict:
    """
    Extrai dicionário cod_municipio (7 dígitos) → valor IDEB do DataFrame.
    As planilhas INEP têm estrutura variável por ano — tenta vários nomes de coluna.
    """
    if df is None or df.empty:
        return {}

    # Identifica coluna de código do município
    cod_col = None
    for nome in MUN_COL_NOMES:
        if nome in df.columns:
            cod_col = nome
            break
    if cod_col is None:
        # Tenta encontrar por conteúdo (7 dígitos numéricos)
        for col in df.columns:
            amostra = df[col].dropna().astype(str)
            if amostra.str.match(r"^\d{7}$").mean() > 0.5:
                cod_col = col
                break
    if cod_col is None:
        print(f"  AVISO: coluna de município não encontrada. Colunas: {list(df.columns[:15])}")
        return {}

    # Identifica coluna IDEB do ano específico
    ideb_col = None
    # Formato típico: coluna com o próprio ano (ex: "2023") ou "IDEB Observado"
    for nome in [str(ano), f"IDEB_{ano}", f"VL_OBSERVADO_{ano}"] + IDEB_COL_NOMES:
        if nome in df.columns:
            ideb_col = nome
            break
    if ideb_col is None:
        print(f"  AVISO: coluna IDEB não encontrada para {ano}. Colunas: {list(df.columns[:20])}")
        return {}

    df_mun = df[[cod_col, ideb_col]].copy()
    df_mun["cod"] = pd.to_numeric(df_mun[cod_col], errors="coerce")
    df_mun["ideb"] = pd.to_numeric(df_mun[ideb_col], errors="coerce")
    df_mun = df_mun.dropna(subset=["cod", "ideb"])
    # Filtra apenas municípios (7 dígitos, entre 1000001 e 9999999)
    df_mun = df_mun[df_mun["cod"].between(1000001, 9999999)]

    return {int(r.cod): float(r.ideb) for r in df_mun.itertuples(index=False)}


def carregar_ano(ano: int) -> tuple[dict, dict]:
    """Retorna (ideb_iniciais, ideb_finais) como dicts cod_municipio → valor."""
    url_iniciais = f"{INEP_BASE}/{ano}/divulgacao_anos_iniciais_municipios_{ano}.xlsx"
    url_finais   = f"{INEP_BASE}/{ano}/divulgacao_anos_finais_municipios_{ano}.xlsx"

    df_iniciais = baixar_excel(url_iniciais)
    df_finais   = baixar_excel(url_finais)

    iniciais = extrair_ideb_municipios(df_iniciais, ano)
    finais   = extrair_ideb_municipios(df_finais, ano)

    print(f"  {ano}: {len(iniciais)} municípios (iniciais), {len(finais)} (finais)")
    return iniciais, finais


def main():
    parser = argparse.ArgumentParser(description="Carrega IDEB/INEP multi-ano")
    parser.add_argument("--anos", nargs="+", type=int, default=ANOS_IDEB)
    args = parser.parse_args()

    anos = sorted(args.anos)
    print(f"Carregando IDEB — {len(anos)} anos: {anos}")

    conn = psycopg2.connect(**DB_PARAMS)
    try:
        for ano in anos:
            print(f"\nAno {ano}...")
            iniciais, finais = carregar_ano(ano)
            municipios = set(iniciais) | set(finais)

            if not municipios:
                print(f"  Sem dados para {ano}, pulando.")
                continue

            rows = [
                (cod, ano, iniciais.get(cod), finais.get(cod))
                for cod in sorted(municipios)
            ]

            with conn.cursor() as cur:
                cur.execute("DELETE FROM educacao.ideb_municipios WHERE ano = %s", (ano,))
                execute_values(
                    cur,
                    """
                    INSERT INTO educacao.ideb_municipios
                        (cod_municipio, ano, ideb_anos_iniciais, ideb_anos_finais)
                    VALUES %s
                    """,
                    rows,
                    page_size=2000,
                )
                print(f"  {len(rows):,} municípios inseridos para {ano}")
            conn.commit()
    finally:
        conn.close()

    print("\nConcluído.")


if __name__ == "__main__":
    main()
