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
import warnings

import psycopg2
import pandas as pd
import requests
import urllib3
from psycopg2.extras import execute_values

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PARAMS = dict(
    host=os.environ.get("POSTGRES_HOST", "localhost"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    database=os.environ.get("POSTGRES_DB", "brasil_dados"),
    user=os.environ.get("POSTGRES_USER", "brasil"),
    password=os.environ.get("POSTGRES_PASSWORD", ""),
)

# Dados Abertos Transportes — API CKAN do portal dados.transportes.gov.br
CKAN_API = "https://dados.transportes.gov.br/api/3/action"
RENAVAM_PACKAGE = "registro-nacional-de-veiculos-automotores-renavam"

# Cache de URLs por ano — preenchido em runtime via CKAN API
# Fallback para os anos cujos resource IDs são conhecidos
RESOURCE_URLS_FALLBACK = {
    2020: (
        "https://dados.transportes.gov.br/dataset/12686da0-3d71-4499-b432-d270f785c907/"
        "resource/82b85990-ae4e-4b01-a8a7-e9ad30c47112/download/frota_munic_modelo_dezembro_2020.csv"
    ),
    2021: (
        "https://dados.transportes.gov.br/dataset/12686da0-3d71-4499-b432-d270f785c907/"
        "resource/f211d37c-7f9e-4531-8f83-c6d66fb0a030/download/frota-munic-modelo-dezembro-2021.csv"
    ),
    2022: (
        "https://dados.transportes.gov.br/dataset/12686da0-3d71-4499-b432-d270f785c907/"
        "resource/9427992a-64e9-4ed2-bb78-a268bfada801/download/frota_munic_modelo_dezembro_2022.csv"
    ),
}


def get_resource_url(ano: int) -> str | None:
    """
    Obtém a URL de download do CSV de frota por município para dezembro do ano.
    Tenta o CKAN API primeiro; usa fallback se necessário.
    """
    # Fallback para anos com URL conhecida
    if ano in RESOURCE_URLS_FALLBACK:
        return RESOURCE_URLS_FALLBACK[ano]

    # Tenta descobrir via CKAN API
    try:
        r = requests.get(
            f"{CKAN_API}/package_show?id={RENAVAM_PACKAGE}",
            timeout=20, verify=False
        )
        if r.status_code != 200:
            return None
        resources = r.json()["result"]["resources"]
        target = f"12-{ano}"
        for res in resources:
            name = res.get("name", "")
            if target in name and "zip" not in name.lower():
                url = res.get("url", "")
                if url:
                    print(f"  CKAN: recurso encontrado: {name}")
                    return url
    except Exception as e:
        print(f"  AVISO: CKAN API falhou: {e}")
    return None

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
    """Baixa CSV de frota por município para dezembro do ano via CKAN API."""
    url = get_resource_url(ano)
    if url is None:
        print(f"  Sem recurso CSV disponível para {ano} no portal dados.transportes.gov.br")
        return None
    print(f"  GET {url[:100]} ...")
    try:
        r = requests.get(url, timeout=120, verify=False)
        if r.status_code == 200:
            for sep in (";", ",", "\t"):
                try:
                    df = pd.read_csv(io.BytesIO(r.content), sep=sep, dtype=str, encoding="latin-1")
                    if len(df.columns) >= 4:
                        return df
                except Exception:
                    pass
            print(f"  AVISO: CSV com formato inesperado para {ano}")
            return None
        else:
            print(f"  HTTP {r.status_code} para {ano}")
            return None
    except requests.exceptions.Timeout:
        print(f"  Timeout para {ano}")
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


# Mapeamento de colunas no formato LARGO (wide) para categorias internas
# (usado quando o CSV tem uma coluna por tipo de veículo)
WIDE_COL_MAP = {
    "AUTOMOVEL":       "automovel",
    "CAMINHAO":        "caminhao",
    "CAMINHAO TRATOR": "caminhao",
    "CAMINHONETE":     "caminhao",
    "CAMIONETA":       "caminhao",
    "MOTOCICLETA":     "moto",
    "MOTONETA":        "moto",
    "CICLOMOTOR":      "moto",
    "TRICICLO":        "moto",
    "QUADRICICLO":     "moto",
    "ONIBUS":          "onibus",
    "MICRO-ONIBUS":    "onibus",
}


def _is_wide_format(df: pd.DataFrame) -> bool:
    """Detecta se o CSV está no formato largo (uma coluna por tipo de veículo)."""
    return "AUTOMOVEL" in df.columns and ("TIPO" not in " ".join(df.columns))


def processar_ano(conn, ano: int, geo_index: dict, pop_map: dict,
                  skip_onibus: bool = False):
    """Processa um ano de dados SENATRAN — suporta formato tall (2020/2022) e wide (2021)."""
    df = download_csv(ano)
    if df is None:
        print(f"  Não foi possível obter dados de {ano}")
        return

    # Normaliza nomes de colunas
    df.columns = [str(c).strip().upper() for c in df.columns]
    # Remove BOM do primeiro nome de coluna (UTF-8 com BOM → 'Ï»¿UF' → 'UF')
    if df.columns[0].startswith("Ï"):
        df.columns = ["UF"] + list(df.columns[1:])
    print(f"  Ano {ano}: colunas = {list(df.columns)}")

    col_uf  = next((c for c in df.columns if c == "UF" or (c.startswith("UF") and len(c) <= 5)), None)
    col_mun = next((c for c in df.columns if "MUNICIPIO" in c or "MUNICÍPIO" in c), None)

    if not col_uf or not col_mun:
        print(f"  ERRO: colunas UF ou MUNICIPIO não encontradas")
        return

    if _is_wide_format(df):
        # ── Formato largo: uma coluna por tipo de veículo ──
        # Agrega por município somando as colunas relevantes
        mun_tipo: dict[tuple[int, str], float] = {}
        miss = 0
        for _, row in df.iterrows():
            uf  = str(row[col_uf]).strip().upper()
            mun = str(row[col_mun]).strip()
            key = (normalize_str(mun), uf)
            cod = geo_index.get(key)
            if cod is None:
                miss += 1
                continue
            for col_name, cat in WIDE_COL_MAP.items():
                if col_name in df.columns:
                    try:
                        val = float(str(row[col_name]).replace(".", "").replace(",", "."))
                    except (ValueError, TypeError):
                        val = 0.0
                    k = (cod, cat)
                    mun_tipo[k] = mun_tipo.get(k, 0.0) + val
        print(f"  Ano {ano} (wide): {len(set(c for c,_ in mun_tipo))} municípios, {miss} geocod. falhas")
    else:
        # ── Formato alto (tall): UF, MUNICIPIO, TIPO, QUANTIDADE ──
        col_tipo = next((c for c in df.columns if "TIPO" in c), None)
        col_qtd  = next((c for c in df.columns if "TOTAL" in c or "QTD" in c or "QUANTIDADE" in c), None)
        if not col_tipo or not col_qtd:
            print(f"  AVISO: colunas TIPO/QTD não encontradas. TIPO={col_tipo}, QTD={col_qtd}")
            return

        df[col_qtd] = pd.to_numeric(
            df[col_qtd].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce"
        ).fillna(0)

        contagens: dict[tuple[str, str, str], float] = {}
        for _, row in df.iterrows():
            uf   = str(row[col_uf]).strip().upper()
            mun  = str(row[col_mun]).strip()
            tipo = str(row[col_tipo]).strip().upper()
            qtd  = float(row[col_qtd]) if pd.notna(row[col_qtd]) else 0.0
            key_tipo = TIPO_MAP.get(tipo, "outro")
            k = (uf, mun, key_tipo)
            contagens[k] = contagens.get(k, 0.0) + qtd

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

        print(f"  Ano {ano} (tall): {len(mun_tipo)} (cod,tipo), {miss} geocodificações falhas")

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
        default=[2020, 2021, 2022],
        help="Anos a carregar (padrão: 2020-2022 — anos com CSV disponível)"
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
