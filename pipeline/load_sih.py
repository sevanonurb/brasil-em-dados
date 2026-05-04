#!/usr/bin/env python3
"""
load_sih.py
Carrega dados do SIH (Sistema de Informações Hospitalares) via PySUS para
api.metricas_municipio.

Grupo: "RD" — AIH Reduzida.
Campo de município: MUNIC_RES (residência do paciente, 6 dígitos DataSUS).
Campo de diagnóstico: DIAG_PRINC (CID-10 capítulo = primeiro caractere).

Indicadores (anuais, por 1000 ou 100k hab.):
  taxa_internacao_sus          — total de internações SUS / 1k hab.
  taxa_internacao_cardiovascular — capítulo I (CID I00-I99) / 100k hab.
  taxa_internacao_respiratoria   — capítulo J (CID J00-J99) / 100k hab.
  taxa_internacao_mental         — capítulo F (CID F00-F99) / 100k hab.
  media_permanencia_sus          — média de dias de internação (QT_DIARIAS / contagem)

Download por UF+ano (igual ao SIM). ATENÇÃO: arquivos grandes; use --workers 1.

Uso:
    python load_sih.py                        # 2015-2023, todas as UFs
    python load_sih.py --anos 2022 2023       # anos específicos
    python load_sih.py --ufs SP RJ            # UFs específicas
    python load_sih.py --workers 1            # padrão seguro
"""

import argparse
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import pandas as pd
from psycopg2.extras import execute_values
from pysus.online_data import SIH

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

UFS_BRASIL = [
    "AC","AL","AP","AM","BA","CE","DF","ES","GO",
    "MA","MT","MS","MG","PA","PB","PR","PE","PI",
    "RJ","RN","RS","RO","RR","SC","SP","SE","TO",
]

ANO_INICIO = 2015
ANO_FIM    = 2023

# CID-10: primeiro caractere → capítulo relevante
CAPITULOS_INTERESSE = {"I", "J", "F"}  # cardiovascular, respiratório, mental


def get_conn():
    return psycopg2.connect(**DB_PARAMS)


def get_pop_map(conn) -> dict[int, float]:
    """Retorna {cod_6d: populacao_2022} (cod_6d = cod_ibge_7 // 10)."""
    with conn.cursor() as cur:
        cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
        rows = cur.fetchall()
    return {r[0] // 10: r[1] for r in rows if r[1] and r[1] > 0}


def get_cod7_map(conn) -> dict[int, int]:
    """Retorna {cod_6d: cod_ibge_7}."""
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


def processar_uf_ano(uf: str, ano: int) -> dict:
    """
    Baixa dados SIH/RD para uma UF+ano, agrega por município.
    Retorna dict com contagens e diárias para cálculo posterior.
    {
      cod6d: {
        "total": int,       # total internações
        "diarias": float,   # soma QT_DIARIAS
        "cap_I": int,       # internações cardiovasculares
        "cap_J": int,       # internações respiratórias
        "cap_F": int,       # internações mentais
      }
    }
    """
    print(f"  [{uf}] {ano}: baixando SIH/RD ...")
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = SIH.download(uf, ano, list(range(1, 13)), "RD", data_dir=tmpdir)
            # PySUS 1.x returns a single ParquetSet or a list of them
            if hasattr(result, "to_dataframe"):
                df = result.to_dataframe()
            else:
                # list of ParquetSet — concatenate all
                frames = [ps.to_dataframe() for ps in result if hasattr(ps, "to_dataframe")]
                if not frames:
                    print(f"  [{uf}] {ano}: nenhum ParquetSet retornado")
                    return {}
                df = pd.concat(frames, ignore_index=True)
        except Exception as e:
            print(f"  ERRO [{uf}] {ano}: {e}")
            return {}

    if df is None or df.empty:
        print(f"  [{uf}] {ano}: DataFrame vazio")
        return {}

    # Campo município de residência
    col_mun = None
    for cand in ("MUNIC_RES", "MUNICIP", "CO_MUN_RES"):
        if cand in df.columns:
            col_mun = cand
            break
    if col_mun is None:
        print(f"  [{uf}] {ano}: campo de município não encontrado. Cols: {list(df.columns[:15])}")
        return {}

    df[col_mun] = pd.to_numeric(df[col_mun], errors="coerce")
    df = df.dropna(subset=[col_mun])
    df[col_mun] = df[col_mun].astype(int)

    # CID-10 — primeiro caractere
    col_cid = "DIAG_PRINC" if "DIAG_PRINC" in df.columns else None
    if col_cid:
        df["capitulo"] = df[col_cid].astype(str).str.strip().str[:1].str.upper()
    else:
        df["capitulo"] = ""

    # Dias de internação
    col_diarias = "QT_DIARIAS" if "QT_DIARIAS" in df.columns else None
    if col_diarias:
        df["diarias"] = pd.to_numeric(df[col_diarias], errors="coerce").fillna(0)
    else:
        df["diarias"] = 0.0

    # Agrega por município
    agg: dict[int, dict] = {}
    for _, row in df.iterrows():
        cod6 = int(row[col_mun])
        if cod6 <= 0:
            continue
        if cod6 not in agg:
            agg[cod6] = {"total": 0, "diarias": 0.0, "cap_I": 0, "cap_J": 0, "cap_F": 0}
        agg[cod6]["total"] += 1
        agg[cod6]["diarias"] += float(row["diarias"])
        cap = str(row["capitulo"]) if pd.notna(row["capitulo"]) else ""
        if cap in CAPITULOS_INTERESSE:
            agg[cod6][f"cap_{cap}"] += 1

    print(f"  [{uf}] {ano}: {len(agg)} municípios, {sum(v['total'] for v in agg.values()):,} AIHs")
    return agg


def main():
    parser = argparse.ArgumentParser(
        description="Carrega SIH (internações SUS) em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=list(range(ANO_INICIO, ANO_FIM + 1)),
        help=f"Anos a carregar (padrão: {ANO_INICIO}-{ANO_FIM})"
    )
    parser.add_argument(
        "--ufs", nargs="+", default=UFS_BRASIL,
        help="Siglas de UF (padrão: todas)"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Downloads paralelos (padrão: 1 — DataSUS FTP tem rate-limit)"
    )
    args = parser.parse_args()

    anos = sorted(args.anos)
    ufs  = [u.upper() for u in args.ufs]

    print("Conectando ao banco...")
    conn = get_conn()
    pop_map  = get_pop_map(conn)
    cod7_map = get_cod7_map(conn)
    conn.close()
    print(f"  Pop map: {len(pop_map)} municípios")

    for ano in anos:
        print(f"\n──── SIH {ano} ────")

        # Coleta de todos dados do ano (por UF)
        agg_ano: dict[int, dict] = {}

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(processar_uf_ano, uf, ano): uf for uf in ufs}
            for fut in as_completed(futures):
                uf = futures[fut]
                try:
                    agg_uf = fut.result()
                    for cod6, dados in agg_uf.items():
                        if cod6 not in agg_ano:
                            agg_ano[cod6] = {"total": 0, "diarias": 0.0, "cap_I": 0, "cap_J": 0, "cap_F": 0}
                        for k in dados:
                            agg_ano[cod6][k] += dados[k]
                except Exception as e:
                    print(f"  ERRO [{uf}] {ano}: {e}")

        # Gera métricas
        rows = []
        for cod6, dados in agg_ano.items():
            cod7 = cod7_map.get(cod6)
            if cod7 is None:
                continue
            pop = pop_map.get(cod6)
            if not pop or pop <= 0:
                continue

            total = dados["total"]
            if total > 0:
                # Taxa total /1k hab
                rows.append((cod7, "taxa_internacao_sus", ano, total / pop * 1000))
                # Média de permanência
                rows.append((cod7, "media_permanencia_sus", ano, dados["diarias"] / total))
                # Por capítulo CID /100k hab
                for cap, metrica in [("I", "taxa_internacao_cardiovascular"),
                                      ("J", "taxa_internacao_respiratoria"),
                                      ("F", "taxa_internacao_mental")]:
                    n = dados[f"cap_{cap}"]
                    if n > 0:
                        rows.append((cod7, metrica, ano, n / pop * 100_000))

        print(f"  Ano {ano}: {len(rows)} registros gerados")

        conn = get_conn()
        try:
            upsert_metricas(rows, conn)
        finally:
            conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,2) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'taxa_internacao_%' OR metrica = 'media_permanencia_sus'")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
