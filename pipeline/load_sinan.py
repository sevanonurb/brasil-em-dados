#!/usr/bin/env python3
"""
load_sinan.py
Carrega dados do SINAN (Sistema de Informação de Agravos de Notificação) via PySUS
para api.metricas_municipio.

Calcula incidência (casos por 100k hab.) por município e ano para:
  incidencia_dengue        — DENG (código SINAN)
  incidencia_tuberculose   — TUBE
  incidencia_hanseniase    — HANS
  incidencia_leishmaniose  — LEIV (leishmaniose visceral)

Campo de município: ID_MUNICIP (6 dígitos DataSUS).
Conversão 6→7 dígitos: cod_ibge_7 = ID_MUNICIP * 10 (via join com geo.municipios).

ATENÇÃO: DataSUS FTP tem rate-limit. Use --workers 1 (padrão).

Uso:
    python load_sinan.py                          # 2020-2024, todas as doenças
    python load_sinan.py --anos 2022 2023         # anos específicos
    python load_sinan.py --doencas DENG TUBE      # doenças específicas
    python load_sinan.py --workers 1              # padrão seguro
"""

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import pandas as pd
from psycopg2.extras import execute_values
from pysus.online_data import SINAN

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

# Mapeamento código SINAN → nome da métrica
DOENCAS = {
    "DENG": "incidencia_dengue",
    "TUBE": "incidencia_tuberculose",
    "HANS": "incidencia_hanseniase",
    "LEIV": "incidencia_leishmaniose",
}

ANO_INICIO = 2015
ANO_FIM    = 2023


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def get_pop_map(conn) -> dict[int, float]:
    """
    Retorna {cod_ibge_7: populacao_2022} para normalização.
    Também suporta busca por cod_6d: usa cod_ibge_7 // 10 como chave alternativa.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        rows = cur.fetchall()
    # Indexa por cod_6d (cod_ibge_7 // 10) para facilitar join com SINAN
    return {r[0] // 10: r[1] for r in rows if r[1] and r[1] > 0}


def get_cod7_map(conn) -> dict[int, int]:
    """Retorna {cod_6d: cod_ibge_7} para conversão de códigos."""
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7 FROM geo.municipios")
        rows = cur.fetchall()
    return {r[0] // 10: r[0] for r in rows}


def upsert_metricas(rows: list[tuple], conn):
    """Insere/atualiza registros em api.metricas_municipio."""
    if not rows:
        return
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


def processar_doenca_ano(dis_code: str, ano: int, pop_map: dict[int, float],
                          cod7_map: dict[int, int]) -> list[tuple]:
    """
    Baixa dados SINAN para uma doença/ano, agrega por município e calcula incidência.
    Retorna lista de (cod_municipio_7d, metrica, ano, incidencia_por_100k).
    """
    metrica = DOENCAS[dis_code]
    print(f"  [{dis_code}] Baixando ano {ano}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            parquet_set = SINAN.download(dis_code, ano, data_path=tmpdir)
            df = parquet_set.to_dataframe()
        except Exception as e:
            print(f"  ERRO [{dis_code}] {ano}: {e}")
            return []

    if df is None or df.empty:
        print(f"  [{dis_code}] {ano}: DataFrame vazio")
        return []

    # Campo de município no SINAN
    col_mun = None
    for cand in ("ID_MUNICIP", "MUNICIPIO_RESIDENCIA", "MUN_RESI", "CO_MUN_NOT"):
        if cand in df.columns:
            col_mun = cand
            break

    if col_mun is None:
        print(f"  [{dis_code}] {ano}: campo de município não encontrado. Colunas: {list(df.columns[:15])}")
        return []

    df[col_mun] = pd.to_numeric(df[col_mun], errors="coerce")
    df = df.dropna(subset=[col_mun])
    df[col_mun] = df[col_mun].astype(int)

    # Agrega contagem por município (6 dígitos)
    contagem = df.groupby(col_mun).size().to_dict()

    rows = []
    for cod6, n_casos in contagem.items():
        cod7 = cod7_map.get(cod6)
        if cod7 is None:
            continue
        pop = pop_map.get(cod6)
        if not pop or pop <= 0:
            continue
        incidencia = n_casos / pop * 100_000
        rows.append((cod7, metrica, ano, incidencia))

    print(f"  [{dis_code}] {ano}: {len(rows)} municípios ({sum(contagem.values()):,} casos)")
    return rows


def carregar_doenca(conn, dis_code: str, anos: list[int], workers: int = 1):
    """Carrega todos os anos de uma doença SINAN."""
    metrica = DOENCAS[dis_code]
    print(f"\n=== SINAN: {metrica} ({dis_code}) — {anos} ===")

    pop_map  = get_pop_map(conn)
    cod7_map = get_cod7_map(conn)

    todos_rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(processar_doenca_ano, dis_code, ano, pop_map, cod7_map): ano
            for ano in anos
        }
        for fut in as_completed(futures):
            ano = futures[fut]
            try:
                rows = fut.result()
                todos_rows.extend(rows)
            except Exception as e:
                print(f"  ERRO [{dis_code}] {ano}: {e}")

    if todos_rows:
        upsert_metricas(todos_rows, conn)
        print(f"  {metrica}: {len(todos_rows):,} registros inseridos")


def main():
    parser = argparse.ArgumentParser(
        description="Carrega SINAN (agravos de notificação) em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=list(range(ANO_INICIO, ANO_FIM + 1)),
        help=f"Anos a carregar (padrão: {ANO_INICIO}-{ANO_FIM})"
    )
    parser.add_argument(
        "--doencas", nargs="+", default=list(DOENCAS.keys()),
        choices=list(DOENCAS.keys()),
        help=f"Códigos SINAN a carregar (padrão: todos — {list(DOENCAS.keys())})"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Downloads paralelos por doença (padrão: 1 — DataSUS FTP tem rate-limit)"
    )
    args = parser.parse_args()

    doencas = [d.upper() for d in args.doencas]
    invalidas = [d for d in doencas if d not in DOENCAS]
    if invalidas:
        print(f"Doenças inválidas: {invalidas}. Opções: {list(DOENCAS.keys())}")
        return

    print("Conectando ao banco...")
    conn = get_conn()

    try:
        for dis_code in doencas:
            carregar_doenca(conn, dis_code, args.anos, workers=args.workers)
            time.sleep(2)  # pausa entre doenças para evitar rate-limit FTP
    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,1) AS media_100k")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'incidencia_%'")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
