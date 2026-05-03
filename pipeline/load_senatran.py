#!/usr/bin/env python3
"""
load_senatran.py
Carrega dados de frota veicular por município (SENATRAN/DENATRAN/RENAVAM) para
api.metricas_municipio.

Fonte: Dados Abertos do Ministério dos Transportes — RENAVAM / SENATRAN.
URL base: https://dados.transportes.gov.br/dataset/registro-nacional-de-veiculos-automotores-renavam

Os arquivos CSV mensais têm colunas: UF, MUNICIPIO (nome texto), tipo veículo, total.
Usamos dezembro de cada ano como referência.

Indicadores (anuais, por 1000 hab.):
  frota_automovel_por_1k   — automóveis / 1000 hab.
  frota_moto_por_1k        — motocicletas / 1000 hab.
  frota_caminhao_por_1k    — caminhões / 1000 hab.
  frota_onibus_por_1k      — ônibus / 1000 hab.
  frota_total_por_1k       — frota total / 1000 hab.

Geocodificação: nome do município + UF → cod_ibge_7 via geo.municipios com
normalização de texto (unaccent/lower) via unicodedata em Python.

Uso:
    python load_senatran.py                     # 2019-2024
    python load_senatran.py --anos 2022 2023    # anos específicos
    python load_senatran.py --skip-onibus       # pula ônibus
"""

import argparse
import io
import os
import time
import unicodedata

import psycopg2
import pandas as pd
import requests
from psycopg2.extras import execute_values

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

# Dados Abertos Transportes — arquivo de frota por município
# Formato: CSV mensal por competência AAAAMM
# URL padrão para dezembro de cada ano
SENATRAN_URL = (
    "https://dados.transportes.gov.br/dataset/dd7e6e94-f6e4-4e5d-89a4-e04c2e19ffe5/"
    "resource/a7e3b0a2-e0da-49c3-8c9d-f3dddffb8060/download/frota_por_municipio_e_tipo_{aaaamm}.csv"
)

# UF sigla → cod_uf IBGE
UF_COD = {
    "AC": 12, "AL": 27, "AP": 16, "AM": 13, "BA": 29, "CE": 23,
    "DF": 53, "ES": 32, "GO": 52, "MA": 21, "MT": 51, "MS": 50,
    "MG": 31, "PA": 15, "PB": 25, "PR": 41, "PE": 26, "PI": 22,
    "RJ": 33, "RN": 24, "RS": 43, "RO": 11, "RR": 14, "SC": 42,
    "SP": 35, "SE": 28, "TO": 17,
}

# Tipos de veículo no CSV → chave interna
TIPO_MAP = {
    # Automóvel
    "AUTOMOVEL":      "automovel",
    "AUTOMÓVEL":      "automovel",
    # Moto (inclui variações)
    "MOTOCICLETA":    "moto",
    "MOTONETA":       "moto",
    "CICLOMOTOR":     "moto",
    "TRICICLO":       "moto",
    "QUADRICICLO":    "moto",
    # Caminhão
    "CAMINHAO":       "caminhao",
    "CAMINHÃO":       "caminhao",
    "CAMINHONETE":    "caminhao",
    "CAMINHONETA":    "caminhao",
    # Ônibus
    "ONIBUS":         "onibus",
    "ÔNIBUS":         "onibus",
    "MICROONIBUS":    "onibus",
    "MICROÔNIBUS":    "onibus",
    "MINIBUS":        "onibus",
}


def normalize_str(s: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def build_geocode_index(conn) -> dict[tuple[str, str], int]:
    """
    Constrói índice (nome_normalizado, sigla_uf) → cod_ibge_7
    a partir de geo.municipios.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT m.nome, u.sigla, m.cod_ibge_7
            FROM geo.municipios m
            JOIN geo.ufs u ON u.cod_uf = m.cod_uf
        """)
        rows = cur.fetchall()
    index = {}
    for nome, sigla, cod in rows:
        key = (normalize_str(nome), sigla.upper())
        index[key] = cod
    print(f"  Índice de geocodificação: {len(index)} municípios")
    return index


def download_csv(ano: int) -> pd.DataFrame | None:
    """Tenta baixar CSV de dezembro do ano. Fallback para novembro se não encontrar."""
    for mes in (12, 11, 10):
        aaaamm = f"{ano}{mes:02d}"
        url = SENATRAN_URL.format(aaaamm=aaaamm)
        print(f"  GET {url} ...")
        try:
            r = requests.get(url, timeout=120)
            if r.status_code == 200:
                # Tenta separador ;, depois ,
                for sep in (";", ",", "\t"):
                    try:
                        df = pd.read_csv(io.BytesIO(r.content), sep=sep, dtype=str, encoding="latin-1")
                        if len(df.columns) >= 4:
                            return df
                    except Exception:
                        pass
                print(f"  AVISO: CSV com formato inesperado em {aaaamm}")
            elif r.status_code == 404:
                print(f"  404 para {aaaamm}, tentando mês anterior...")
            else:
                print(f"  HTTP {r.status_code} para {aaaamm}")
        except requests.exceptions.Timeout:
            print(f"  Timeout para {aaaamm}")
        time.sleep(1)
    return None


def upsert_metricas(rows: list[tuple], conn):
    """Insere/atualiza registros em api.metricas_municipio."""
    if not rows:
        print("  Sem dados para inserir.")
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
    print(f"  Upserted {len(rows):,} registros em api.metricas_municipio")


def processar_ano(conn, ano: int, geo_index: dict, pop_map: dict,
                  skip_onibus: bool = False):
    """Processa um ano de dados SENATRAN."""
    df = download_csv(ano)
    if df is None:
        print(f"  Não foi possível obter dados de {ano}")
        return

    # Normaliza nomes de colunas
    df.columns = [str(c).strip().upper() for c in df.columns]
    print(f"  Ano {ano}: colunas = {list(df.columns)}")

    # Identifica colunas: UF, MUNICIPIO, TIPO, TOTAL
    col_uf   = next((c for c in df.columns if "UF" in c and len(c) <= 5), None)
    col_mun  = next((c for c in df.columns if "MUNICIPIO" in c or "MUNICÍPIO" in c), None)
    col_tipo = next((c for c in df.columns if "TIPO" in c), None)
    col_qtd  = next((c for c in df.columns if "TOTAL" in c or "QTD" in c or "QUANTIDADE" in c), None)

    if not all([col_uf, col_mun, col_tipo, col_qtd]):
        print(f"  AVISO: colunas esperadas não encontradas. UF={col_uf}, MUN={col_mun}, TIPO={col_tipo}, QTD={col_qtd}")
        # Fallback: assume primeira coluna = UF, segunda = mun, terceira = tipo, quarta = total
        cols = list(df.columns)
        if len(cols) >= 4:
            col_uf, col_mun, col_tipo, col_qtd = cols[0], cols[1], cols[2], cols[3]
        else:
            return

    df[col_qtd] = pd.to_numeric(df[col_qtd].str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce").fillna(0)

    # Agrega por (UF, município, tipo)
    contagens: dict[tuple[str, str, str], float] = {}
    for _, row in df.iterrows():
        uf   = str(row[col_uf]).strip().upper()
        mun  = str(row[col_mun]).strip()
        tipo = str(row[col_tipo]).strip().upper()
        qtd  = float(row[col_qtd]) if pd.notna(row[col_qtd]) else 0.0
        key_tipo = TIPO_MAP.get(tipo, "outro")
        if key_tipo == "outro":
            key_tipo = "outro"
        k = (uf, mun, key_tipo)
        contagens[k] = contagens.get(k, 0.0) + qtd

    # Geocodifica e agrega por (cod_municipio, tipo)
    mun_tipo: dict[tuple[int, str], float] = {}
    miss = 0
    for (uf, mun, tipo), qtd in contagens.items():
        key = (normalize_str(mun), uf)
        cod = geo_index.get(key)
        if cod is None:
            miss += 1
            continue
        k = (cod, tipo)
        mun_tipo[k] = mun_tipo.get(k, 0.0) + qtd

    print(f"  Ano {ano}: {len(mun_tipo)} (cod,tipo), {miss} geocodificações falhas")

    # Agrega total
    totais: dict[int, float] = {}
    por_tipo: dict[str, dict[int, float]] = {
        "automovel": {}, "moto": {}, "caminhao": {}, "onibus": {}
    }

    for (cod, tipo), qtd in mun_tipo.items():
        totais[cod] = totais.get(cod, 0.0) + qtd
        if tipo in por_tipo:
            por_tipo[tipo][cod] = por_tipo[tipo].get(cod, 0.0) + qtd

    # Gera rows normalizadas por pop
    rows = []
    for cod, total in totais.items():
        pop = pop_map.get(cod)
        if not pop or pop <= 0:
            continue
        rows.append((cod, "frota_total_por_1k", ano, total / pop * 1000))

    tipo_metricas = [
        ("automovel", "frota_automovel_por_1k"),
        ("moto",      "frota_moto_por_1k"),
        ("caminhao",  "frota_caminhao_por_1k"),
    ]
    if not skip_onibus:
        tipo_metricas.append(("onibus", "frota_onibus_por_1k"))

    for tipo, metrica in tipo_metricas:
        for cod, qtd in por_tipo[tipo].items():
            pop = pop_map.get(cod)
            if pop and pop > 0:
                rows.append((cod, metrica, ano, qtd / pop * 1000))

    print(f"  Ano {ano}: {len(rows)} registros a inserir")
    upsert_metricas(rows, conn)


def main():
    parser = argparse.ArgumentParser(
        description="Carrega frota veicular SENATRAN em api.metricas_municipio"
    )
    parser.add_argument(
        "--anos", nargs="+", type=int,
        default=[2019, 2020, 2021, 2022, 2023, 2024],
        help="Anos a carregar (padrão: 2019-2024)"
    )
    parser.add_argument("--skip-onibus", action="store_true",
                        help="Pula frota de ônibus")
    args = parser.parse_args()

    print("Conectando ao banco...")
    conn = psycopg2.connect(**DB_PARAMS)

    try:
        geo_index = build_geocode_index(conn)

        with conn.cursor() as cur:
            cur.execute("SELECT cod_ibge_7, populacao_2022 FROM geo.municipios WHERE populacao_2022 > 0")
            pop_map = {r[0]: r[1] for r in cur.fetchall()}

        print(f"  Pop map: {len(pop_map)} municípios")

        for ano in args.anos:
            print(f"\n──── SENATRAN: frota veicular {ano} ────")
            processar_ano(conn, ano, geo_index, pop_map, skip_onibus=args.skip_onibus)
    finally:
        conn.close()

    print("\n=== Concluído ===")
    print("Verificar com:")
    print("  SELECT metrica, ano, COUNT(*), ROUND(AVG(valor)::numeric,1) AS media")
    print("  FROM api.metricas_municipio")
    print("  WHERE metrica LIKE 'frota_%'")
    print("  GROUP BY metrica, ano ORDER BY metrica, ano;")


if __name__ == "__main__":
    main()
