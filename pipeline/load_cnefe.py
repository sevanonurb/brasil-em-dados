#!/usr/bin/env python3
"""
load_cnefe.py — Carrega pontos de endereço a partir das Faces de Logradouros IBGE 2022.

Fonte: geoftp.ibge.gov.br — base_de_faces_de_logradouros_versao_2022_censo_demografico/shp/
Cada zip de UF contém um shapefile por município (LineString).
O centroide de cada face de logradouro é inserido como Point em censo.cnefe_enderecos.

Uso:
    python load_cnefe.py [--ufs AC SP RJ ...] [--workers 2] [--limpar]
"""

import argparse
import io
import logging
import os
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import geopandas as gpd
import psycopg2
import requests
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = (
    "https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/"
    "malha_de_setores_censitarios/censo_2022/"
    "base_de_faces_de_logradouros_versao_2022_censo_demografico/shp/"
)

UF_CODIGOS = {
    "AC": 12, "AL": 27, "AM": 13, "AP": 16, "BA": 29,
    "CE": 23, "DF": 53, "ES": 32, "GO": 52, "MA": 21,
    "MG": 31, "MS": 50, "MT": 51, "PA": 15, "PB": 25,
    "PE": 26, "PI": 22, "PR": 41, "RJ": 33, "RN": 24,
    "RO": 11, "RR": 14, "RS": 43, "SC": 42, "SE": 28,
    "SP": 35, "TO": 17,
}

# Mapeamento do nome do tipo de logradouro para SMALLINT
TIPO_LOG_MAP = {
    "RUA": 1, "AVENIDA": 2, "TRAVESSA": 3, "ALAMEDA": 4, "PRAÇA": 5,
    "ESTRADA": 6, "RODOVIA": 7, "VIA": 8, "VIELA": 9, "BECO": 10,
    "SERVIDÃO": 11, "LARGO": 12, "PASSAGEM": 13, "LINHA": 14,
}

def _build_dsn():
    host = os.environ.get("POSTGRES_HOST", "postgis")
    user = os.environ.get("POSTGRES_USER", "brasil")
    pw   = os.environ.get("POSTGRES_PASSWORD", "brasil")
    db   = os.environ.get("POSTGRES_DB", "brasil_dados")
    return os.environ.get("DATABASE_URL", f"postgresql://{user}:{pw}@{host}:5432/{db}")

DSN = _build_dsn()


def get_conn():
    return psycopg2.connect(DSN)


def precreate_all_partitions(conn, cod_ufs: list):
    """Cria todas as partições CNEFE antes dos workers paralelos."""
    with conn.cursor() as cur:
        for cod_uf in cod_ufs:
            cur.execute(
                "SELECT 1 FROM pg_class WHERE relname = %s AND relnamespace = "
                "(SELECT oid FROM pg_namespace WHERE nspname = 'censo')",
                (f"cnefe_enderecos_{cod_uf}",),
            )
            if cur.fetchone() is None:
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS censo.cnefe_enderecos_{cod_uf} "
                    f"PARTITION OF censo.cnefe_enderecos FOR VALUES IN ({cod_uf})"
                )
                log.info("Partição censo.cnefe_enderecos_%d criada", cod_uf)
        conn.commit()


def download_uf_zip(sigla: str) -> bytes:
    url = f"{BASE_URL}{sigla}_faces_de_logradouros_2022_shp.zip"
    log.info("[%s] Baixando %s", sigla, url)
    r = requests.get(url, timeout=300, stream=True)
    r.raise_for_status()
    data = b"".join(r.iter_content(65536))
    log.info("[%s] Baixado %.1f MB", sigla, len(data) / 1e6)
    return data


def load_uf(sigla: str, limpar: bool = False) -> dict:
    cod_uf = UF_CODIGOS[sigla]

    zip_bytes = download_uf_zip(sigla)

    conn = get_conn()
    try:
        if limpar:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM censo.cnefe_enderecos WHERE cod_uf = %s", (cod_uf,)
                )
                conn.commit()
                log.info("[%s] Dados anteriores removidos", sigla)

        total_pontos = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(tmpdir)

            # Cada zip contém uma subpasta com N shapefiles (um por município)
            shp_files = []
            for root, _dirs, files in os.walk(tmpdir):
                for f in files:
                    if f.endswith(".shp"):
                        shp_files.append(os.path.join(root, f))

            if not shp_files:
                log.warning("[%s] Nenhum .shp encontrado", sigla)
                return {"sigla": sigla, "pontos": 0}

            log.info("[%s] %d shapefiles de municípios", sigla, len(shp_files))

            BATCH = 2000
            rows_buf = []

            def flush(cur, buf):
                if not buf:
                    return 0
                execute_values(
                    cur,
                    """
                    INSERT INTO censo.cnefe_enderecos
                        (cod_setor, cod_municipio, cod_uf,
                         tipo_logradouro, especie, geom)
                    VALUES %s
                    """,
                    buf,
                    template=(
                        "(%s, %s, %s, %s, %s, "
                        "ST_SetSRID(ST_MakePoint(%s, %s), 4674))"
                    ),
                )
                return len(buf)

            with conn.cursor() as cur:
                for shp_path in shp_files:
                    # Extrai cod_municipio do nome do arquivo (7 primeiros dígitos)
                    fname = os.path.basename(shp_path)
                    try:
                        cod_mun = int(fname[:7])
                    except ValueError:
                        log.warning("[%s] Nome inesperado: %s", sigla, fname)
                        continue

                    try:
                        gdf = gpd.read_file(shp_path)
                    except Exception as e:
                        log.warning("[%s] Erro ao ler %s: %s", sigla, fname, e)
                        continue

                    if gdf.empty:
                        continue

                    # CRS: os shapefiles de faces estão em EPSG:4674 ou SIRGAS
                    if gdf.crs is not None and gdf.crs.to_epsg() != 4674:
                        gdf = gdf.to_crs("EPSG:4674")

                    for _, row in gdf.iterrows():
                        geom = row.geometry
                        if geom is None or geom.is_empty:
                            continue

                        # Centroide da face (LineString → Point)
                        pt = geom.centroid
                        if pt.is_empty:
                            continue

                        # Tipo logradouro: texto → SMALLINT
                        nm_tip = str(row.get("NM_TIP_LOG") or "").strip().upper()
                        tipo = TIPO_LOG_MAP.get(nm_tip, None)

                        # Espécie: 1=residencial se TOT_RES > 0
                        tot_res = row.get("TOT_RES")
                        especie = 1 if (tot_res is not None and float(tot_res or 0) > 0) else 2

                        # cod_setor: pode vir com sufixo 'P' (p/ aglomerado subnormal)
                        cd_setor_raw = str(row.get("CD_SETOR") or "").strip()
                        cd_setor_raw = cd_setor_raw.rstrip("P").rstrip("S")  # remove sufixo
                        try:
                            cod_setor = int(cd_setor_raw) if cd_setor_raw else None
                        except ValueError:
                            cod_setor = None

                        rows_buf.append((
                            cod_setor, cod_mun, cod_uf,
                            tipo, especie,
                            pt.x, pt.y,
                        ))

                        if len(rows_buf) >= BATCH:
                            n = flush(cur, rows_buf)
                            total_pontos += n
                            rows_buf.clear()

                # Flush restantes
                n = flush(cur, rows_buf)
                total_pontos += n
                rows_buf.clear()
                conn.commit()

        log.info("[%s] %d pontos inseridos", sigla, total_pontos)
        return {"sigla": sigla, "pontos": total_pontos}

    finally:
        conn.close()


def build_spatial_indexes(conn):
    log.info("Criando índices espaciais em censo.cnefe_enderecos...")
    with conn.cursor() as cur:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_cnefe_geom "
            "ON censo.cnefe_enderecos USING GIST (geom)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_cnefe_cod_municipio "
            "ON censo.cnefe_enderecos (cod_municipio)"
        )
        conn.commit()
    log.info("ANALYZE em censo.cnefe_enderecos...")
    with conn.cursor() as cur:
        cur.execute("ANALYZE censo.cnefe_enderecos")
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Carrega CNEFE (faces de logradouros) 2022")
    parser.add_argument(
        "--ufs", nargs="+", default=list(UF_CODIGOS.keys()),
        help="Siglas das UFs (padrão: todas)"
    )
    parser.add_argument("--workers", type=int, default=2, help="Downloads paralelos")
    parser.add_argument(
        "--limpar", action="store_true",
        help="Apaga dados existentes antes de reinserir"
    )
    args = parser.parse_args()

    ufs = [u.upper() for u in args.ufs]
    invalidas = [u for u in ufs if u not in UF_CODIGOS]
    if invalidas:
        sys.exit(f"UFs inválidas: {invalidas}")

    log.info("Carregando %d UFs com %d workers", len(ufs), args.workers)

    conn0 = get_conn()
    try:
        precreate_all_partitions(conn0, [UF_CODIGOS[u] for u in ufs])
    finally:
        conn0.close()

    resultados = []
    erros = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(load_uf, uf, args.limpar): uf for uf in ufs}
        for fut in as_completed(futures):
            uf = futures[fut]
            try:
                res = fut.result()
                resultados.append(res)
                log.info("[%s] OK — %d pontos", res["sigla"], res["pontos"])
            except Exception as exc:
                erros.append((uf, exc))
                log.error("[%s] ERRO: %s", uf, exc)

    conn = get_conn()
    try:
        build_spatial_indexes(conn)
    finally:
        conn.close()

    total = sum(r["pontos"] for r in resultados)
    log.info("=" * 60)
    log.info("Concluído: %d pontos CNEFE inseridos", total)
    if erros:
        log.error("Falhas: %s", [u for u, _ in erros])
        sys.exit(1)


if __name__ == "__main__":
    main()
