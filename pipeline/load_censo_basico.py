"""
load_censo_basico.py
Carrega os Agregados por Setor Censitário (Básico) do Censo 2022 do IBGE.
Popula geo.setores_censitarios.populacao_total e domicilios_total.

Fonte: https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/
       Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/
       Agregados_por_setores_basico_BR_20250417.zip

Dicionário:
  v0001 = Total de pessoas (populacao_total)
  v0007 = Total de Domicílios Particulares Ocupados (domicilios_total)
  CD_TIPO = tipo do setor censitário
  AREA_KM2 = área em km² (separador decimal: vírgula)
"""

import csv
import io
import logging
import os
import sys
import tempfile
import urllib.request
import zipfile

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

URL = (
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
    "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/"
    "Agregados_por_setores_basico_BR_20250417.zip"
)

LOCAL_ZIP = "/tmp/basico_BR_censo2022.zip"


def get_dsn():
    return (
        f"host={os.environ.get('POSTGRES_HOST', 'postgis')} "
        f"port={os.environ.get('POSTGRES_PORT', '5432')} "
        f"dbname={os.environ.get('POSTGRES_DB', 'brasil_dados')} "
        f"user={os.environ.get('POSTGRES_USER', 'brasil')} "
        f"password={os.environ.get('POSTGRES_PASSWORD', '')}"
    )


def download_if_needed(url: str, dest: str):
    if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
        log.info("Arquivo já existe: %s", dest)
        return
    log.info("Baixando %s ...", url)
    urllib.request.urlretrieve(url, dest)
    log.info("Download concluído: %s (%.1f MB)", dest, os.path.getsize(dest) / 1e6)


def parse_float(s: str) -> float | None:
    """Converte string com vírgula decimal para float."""
    if not s or s.strip() in (".", "", "-"):
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def parse_int(s: str) -> int | None:
    if not s or s.strip() in (".", "", "-"):
        return None
    try:
        return int(s)
    except ValueError:
        return None


def load(zip_path: str, conn):
    log.info("Lendo arquivo CSV dentro do zip...")
    with zipfile.ZipFile(zip_path) as z:
        csv_name = next(f for f in z.namelist() if f.endswith(".csv"))
        log.info("CSV: %s", csv_name)
        data = z.read(csv_name).decode("latin-1")

    reader = csv.DictReader(io.StringIO(data), delimiter=";")

    batch = []
    batch_size = 5000
    total = 0
    skipped = 0

    with conn.cursor() as cur:
        log.info("Iniciando UPDATE em geo.setores_censitarios...")

        for row in reader:
            cd_setor_str = row["CD_SETOR"].strip()
            if not cd_setor_str:
                skipped += 1
                continue

            try:
                cod_setor = int(cd_setor_str)
            except ValueError:
                skipped += 1
                continue

            pop = parse_int(row.get("v0001", ""))
            dom = parse_int(row.get("v0007", ""))
            tipo = parse_int(row.get("CD_TIPO", ""))
            area = parse_float(row.get("AREA_KM2", ""))

            batch.append((pop, dom, tipo, area, cod_setor))

            if len(batch) >= batch_size:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    UPDATE geo.setores_censitarios
                    SET populacao_total  = %s,
                        domicilios_total = %s,
                        tipo_setor       = COALESCE(%s, tipo_setor),
                        area_km2         = COALESCE(%s, area_km2)
                    WHERE cod_setor = %s
                    """,
                    batch,
                    page_size=batch_size,
                )
                total += len(batch)
                batch = []
                if total % 50_000 == 0:
                    log.info("  %d setores atualizados...", total)

        # Flush restante
        if batch:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE geo.setores_censitarios
                SET populacao_total  = %s,
                    domicilios_total = %s,
                    tipo_setor       = COALESCE(%s, tipo_setor),
                    area_km2         = COALESCE(%s, area_km2)
                WHERE cod_setor = %s
                """,
                batch,
                page_size=batch_size,
            )
            total += len(batch)

    conn.commit()
    log.info("Concluído: %d setores atualizados, %d ignorados.", total, skipped)


def main():
    download_if_needed(URL, LOCAL_ZIP)

    log.info("Conectando ao banco...")
    conn = psycopg2.connect(get_dsn())
    try:
        load(LOCAL_ZIP, conn)

        # Verifica resultado
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(populacao_total) AS com_pop,
                    SUM(populacao_total) AS pop_total,
                    ROUND(AVG(populacao_total)) AS pop_media,
                    MIN(populacao_total) AS pop_min,
                    MAX(populacao_total) AS pop_max
                FROM geo.setores_censitarios
            """)
            row = cur.fetchone()
            log.info(
                "Resultado: total=%d, com_pop=%d, pop_total=%s, média=%s, min=%s, max=%s",
                *row,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
