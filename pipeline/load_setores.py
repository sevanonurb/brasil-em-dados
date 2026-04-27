#!/usr/bin/env python3
"""
load_setores.py — Carrega malha de setores censitários IBGE Censo 2022.

Fonte: geoftp.ibge.gov.br — malhas_de_setores_censitarios/censo_2022/setores/shp/UF/
Um SHP por UF → geo.setores_censitarios (particionado)
Gera geo.setores_subdivididos via ST_Subdivide para queries espaciais rápidas.

Uso:
    python load_setores.py [--ufs AC SP RJ ...] [--workers 4] [--limpar]
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
from shapely.geometry import mapping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/"
    "censo_2022/setores/shp/UF/"
)

UF_CODIGOS = {
    "AC": 12, "AL": 27, "AM": 13, "AP": 16, "BA": 29,
    "CE": 23, "DF": 53, "ES": 32, "GO": 52, "MA": 21,
    "MG": 31, "MS": 50, "MT": 51, "PA": 15, "PB": 25,
    "PE": 26, "PI": 22, "PR": 41, "RJ": 33, "RN": 24,
    "RO": 11, "RR": 14, "RS": 43, "SC": 42, "SE": 28,
    "SP": 35, "TO": 17,
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
    """Cria todas as partições sequencialmente ANTES de iniciar workers paralelos.
    Evita deadlocks: CREATE TABLE PARTITION precisa de ExclusiveLock no pai,
    incompatível com SELECT FROM pai em threads concorrentes."""
    with conn.cursor() as cur:
        for cod_uf in cod_ufs:
            cur.execute(
                "SELECT 1 FROM pg_class WHERE relname = %s AND relnamespace = "
                "(SELECT oid FROM pg_namespace WHERE nspname = 'geo')",
                (f"setores_censitarios_{cod_uf}",),
            )
            if cur.fetchone() is None:
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS geo.setores_censitarios_{cod_uf} "
                    f"PARTITION OF geo.setores_censitarios FOR VALUES IN ({cod_uf})"
                )
                log.info("Partição geo.setores_censitarios_%d criada", cod_uf)

            cur.execute(
                "SELECT 1 FROM pg_class WHERE relname = %s AND relnamespace = "
                "(SELECT oid FROM pg_namespace WHERE nspname = 'geo')",
                (f"setores_subdivididos_{cod_uf}",),
            )
            if cur.fetchone() is None:
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS geo.setores_subdivididos_{cod_uf} "
                    f"PARTITION OF geo.setores_subdivididos FOR VALUES IN ({cod_uf})"
                )
                log.info("Partição geo.setores_subdivididos_%d criada", cod_uf)
        conn.commit()


def download_uf_shp(sigla: str) -> bytes:
    url = f"{BASE_URL}{sigla}_setores_CD2022.zip"
    log.info("[%s] Baixando %s", sigla, url)
    r = requests.get(url, timeout=120, stream=True)
    r.raise_for_status()
    data = b"".join(r.iter_content(65536))
    log.info("[%s] Baixado %.1f MB", sigla, len(data) / 1e6)
    return data


def load_uf(sigla: str, limpar: bool = False) -> dict:
    """Carrega setores de uma UF. Partições já devem existir (criadas por precreate_all_partitions)."""
    cod_uf = UF_CODIGOS[sigla]

    zip_bytes = download_uf_shp(sigla)

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmpdir)

        shp_files = [
            os.path.join(tmpdir, f)
            for f in os.listdir(tmpdir)
            if f.endswith(".shp")
        ]
        if not shp_files:
            raise FileNotFoundError(f"Nenhum .shp em {sigla}_setores_CD2022.zip")

        gdf = gpd.read_file(shp_files[0])

    # O shapefile já está em EPSG:4674
    if gdf.crs is None or gdf.crs.to_epsg() != 4674:
        gdf = gdf.set_crs("EPSG:4674", allow_override=True).to_crs("EPSG:4674")

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if limpar:
                cur.execute(
                    "DELETE FROM geo.setores_censitarios WHERE cod_uf = %s", (cod_uf,)
                )
                cur.execute(
                    "DELETE FROM geo.setores_subdivididos WHERE cod_uf = %s", (cod_uf,)
                )
                conn.commit()
                log.info("[%s] Dados anteriores removidos", sigla)

        rows = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            cd_setor = row.get("CD_SETOR")
            cd_mun   = row.get("CD_MUN")
            if cd_setor is None or cd_mun is None:
                continue  # ignora setores sem código (raro em RS/MG)
            rows.append((
                int(cd_setor),                  # cod_setor
                int(cd_mun),                    # cod_municipio (7 dígitos)
                cod_uf,                         # cod_uf
                int(row["CD_TIPO"]) if row.get("CD_TIPO") is not None else None,
                geom.wkt,                       # WKT passado como parâmetro
                float(row["AREA_KM2"]) if row.get("AREA_KM2") is not None else None,
            ))

        BATCH = 300
        inserted = 0
        with conn.cursor() as cur:
            for i in range(0, len(rows), BATCH):
                batch = rows[i : i + BATCH]
                execute_values(
                    cur,
                    """
                    INSERT INTO geo.setores_censitarios
                        (cod_setor, cod_municipio, cod_uf, tipo_setor, geom, area_km2)
                    VALUES %s
                    """,
                    batch,
                    template="(%s, %s, %s, %s, ST_GeomFromText(%s, 4674), %s)",
                )
                inserted += len(batch)
            conn.commit()

        log.info("[%s] %d setores inseridos", sigla, inserted)

        # Gera setores_subdivididos via PostGIS (ST_Subdivide max 64 vértices)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO geo.setores_subdivididos (cod_setor, cod_municipio, cod_uf, geom)
                SELECT cod_setor, cod_municipio, cod_uf,
                       (ST_Dump(ST_Subdivide(geom, 64))).geom
                FROM geo.setores_censitarios
                WHERE cod_uf = %s
                ON CONFLICT DO NOTHING
                """,
                (cod_uf,),
            )
            subdiv = cur.rowcount
            conn.commit()

        log.info("[%s] %d polígonos subdivididos gerados", sigla, subdiv)
        return {"sigla": sigla, "setores": inserted, "subdivididos": subdiv}

    finally:
        conn.close()


def build_spatial_indexes(conn):
    """Cria/atualiza índices espaciais e ANALYZE após carga completa."""
    log.info("Criando índices em geo.setores_censitarios...")
    with conn.cursor() as cur:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_geom "
            "ON geo.setores_censitarios USING GIST (geom)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_cod_uf "
            "ON geo.setores_censitarios (cod_uf)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_cod_municipio "
            "ON geo.setores_censitarios (cod_municipio)"
        )
        # cod_setor não é globalmente único na tabela particionada sem incluir cod_uf
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_cod_setor "
            "ON geo.setores_censitarios (cod_setor)"
        )
        log.info("Criando índices em geo.setores_subdivididos...")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_subdivididos_geom "
            "ON geo.setores_subdivididos USING GIST (geom)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_setores_subdivididos_cod_setor "
            "ON geo.setores_subdivididos (cod_setor)"
        )
        conn.commit()
    log.info("ANALYZE nas tabelas de setores...")
    with conn.cursor() as cur:
        cur.execute("ANALYZE geo.setores_censitarios")
        cur.execute("ANALYZE geo.setores_subdivididos")
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Carrega setores censitários 2022")
    parser.add_argument(
        "--ufs", nargs="+", default=list(UF_CODIGOS.keys()),
        help="Siglas das UFs (padrão: todas)"
    )
    parser.add_argument("--workers", type=int, default=3, help="Downloads paralelos")
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

    # Pré-cria TODAS as partições antes dos workers paralelos (evita deadlock)
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
                log.info(
                    "[%s] OK — %d setores, %d subdivididos",
                    res["sigla"], res["setores"], res["subdivididos"]
                )
            except Exception as exc:
                erros.append((uf, exc))
                log.error("[%s] ERRO: %s", uf, exc)

    conn = get_conn()
    try:
        build_spatial_indexes(conn)
    finally:
        conn.close()

    total_set = sum(r["setores"] for r in resultados)
    total_sub = sum(r["subdivididos"] for r in resultados)
    log.info("=" * 60)
    log.info("Concluído: %d setores, %d subdivididos", total_set, total_sub)
    if erros:
        log.error("Falhas: %s", [u for u, _ in erros])
        sys.exit(1)


if __name__ == "__main__":
    main()
