"""
Assets Dagster para ingestão das malhas territoriais do IBGE Censo 2022.
Cobre: UFs, Municípios, Setores Censitários e aplicação de ST_Subdivide.
"""

import hashlib
import io
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pandas as pd
import psycopg2
import structlog
from dagster import (
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
)
from geoalchemy2 import Geometry, WKTElement
from shapely.validation import make_valid
from sqlalchemy import create_engine, text

log = structlog.get_logger()

# URLs oficiais das malhas IBGE Censo 2022
IBGE_MALHA_UF_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_municipais/municipio_2022/"
    "Brasil/BR/BR_UF_2022.zip"
)
IBGE_MALHA_MUNICIPIOS_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_municipais/municipio_2022/"
    "Brasil/BR/BR_Municipios_2022.zip"
)
IBGE_MALHA_SETORES_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/"
    "malhas_territoriais/malhas_de_setores_censitarios/"
    "censo_2022/Brasil/BR/BR_Setores_2022.zip"
)


def get_db_engine():
    url = (
        f"postgresql+psycopg2://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ['POSTGRES_HOST']}:5432/{os.environ['POSTGRES_DB']}"
    )
    return create_engine(url)


def validate_and_fix_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Aplica make_valid em todas as geometrias inválidas."""
    invalid_mask = ~gdf.geometry.is_valid
    invalid_count = invalid_mask.sum()

    if invalid_count > 0:
        log.warning("geometrias_invalidas", count=int(invalid_count))
        gdf.loc[invalid_mask, "geometry"] = gdf.loc[invalid_mask, "geometry"].apply(
            make_valid
        )
        # Verifica se ainda há inválidas após correção
        still_invalid = ~gdf.geometry.is_valid
        if still_invalid.sum() > 0:
            raise ValueError(
                f"{still_invalid.sum()} geometrias permaneceram inválidas após make_valid"
            )

    return gdf


@asset(
    group_name="ibge_malhas",
    description="Malha das 27 Unidades da Federação (IBGE Censo 2022)",
    compute_kind="geopandas",
)
def ibge_ufs(context: AssetExecutionContext) -> Output[gpd.GeoDataFrame]:
    import geobr

    context.log.info("Baixando malha de UFs via geobr (IBGE 2022)...")
    gdf = geobr.read_state(code_state="all", year=2020)

    context.log.info(f"UFs baixadas: {len(gdf)}")
    assert len(gdf) == 27, f"Esperado 27 UFs, obtido {len(gdf)}"

    gdf = gdf.to_crs(epsg=4674)
    gdf = validate_and_fix_geometry(gdf)

    # geobr retorna colunas padronizadas: code_state, name_state, abbrev_state, name_region
    # Fallback para shapefiles brutos do IBGE: CD_UF, NM_UF, SIGLA_UF, NM_REGIAO
    col_map = {
        "code_state": "cod_uf",   "CD_UF": "cod_uf",
        "name_state": "nome",     "NM_UF": "nome",
        "abbrev_state": "sigla",  "SIGLA_UF": "sigla",
        "name_region": "regiao",  "NM_REGIAO": "regiao",
    }
    gdf = gdf.rename(columns={k: v for k, v in col_map.items() if k in gdf.columns})

    # Garante que as colunas necessárias existem
    for col, default in [("regiao", "Desconhecida"), ("sigla", "")]:
        if col not in gdf.columns:
            gdf[col] = default

    gdf = gdf[["cod_uf", "nome", "sigla", "regiao", "geometry"]]
    gdf["cod_uf"] = pd.to_numeric(gdf["cod_uf"], errors="coerce").astype("Int32")
    gdf["area_km2"] = gdf.geometry.to_crs(epsg=5880).area / 1e6

    # Geometria simplificada para zoom baixo (~1km de tolerância)
    gdf["geom_simplified"] = gdf.geometry.simplify(0.01, preserve_topology=True)

    context.log.info(f"UFs carregadas: {len(gdf)}")
    return Output(
        gdf,
        metadata={
            "num_ufs": MetadataValue.int(len(gdf)),
            "area_total_km2": MetadataValue.float(float(gdf["area_km2"].sum())),
            "crs": MetadataValue.text(str(gdf.crs)),
        },
    )


@asset(
    group_name="ibge_malhas",
    description="Malha dos 5.570 municípios brasileiros via geobr (IBGE Censo 2022)",
    compute_kind="geopandas",
    deps=["ibge_ufs"],
)
def ibge_municipios(context: AssetExecutionContext) -> Output[gpd.GeoDataFrame]:
    import geobr

    context.log.info("Baixando malha de municípios via geobr (IBGE 2022)...")
    # geobr gerencia download, cache e retry automaticamente
    gdf = geobr.read_municipality(code_muni="all", year=2020)

    context.log.info(f"Municípios baixados: {len(gdf)}")
    assert len(gdf) >= 5500, f"Esperado >= 5500 municípios, obtido {len(gdf)}"

    gdf = gdf.to_crs(epsg=4674)
    gdf = validate_and_fix_geometry(gdf)

    # geobr usa nomes de colunas padronizados
    col_map = {
        "code_muni": "cod_ibge_7",
        "name_muni": "nome",
        "code_state": "cod_uf",
        # fallback para outros nomes possíveis
        "CD_MUN": "cod_ibge_7",
        "NM_MUN": "nome",
        "CD_UF": "cod_uf",
    }
    gdf = gdf.rename(columns={k: v for k, v in col_map.items() if k in gdf.columns})

    for col in ["cod_ibge_7", "cod_uf"]:
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce").astype("Int64")

    gdf["area_km2"] = gdf.geometry.to_crs(epsg=5880).area / 1e6
    gdf["geom_simplified"] = gdf.geometry.simplify(0.005, preserve_topology=True)

    cols = ["cod_ibge_7", "nome", "cod_uf", "area_km2", "geom_simplified", "geometry"]
    gdf = gdf[[c for c in cols if c in gdf.columns]]

    context.log.info(f"Municípios processados: {len(gdf)}")
    return Output(
        gdf,
        metadata={
            "num_municipios": MetadataValue.int(len(gdf)),
            "crs": MetadataValue.text(str(gdf.crs)),
        },
    )


@asset(
    group_name="ibge_malhas",
    description="Carga das 27 UFs no PostGIS (schema geo)",
    compute_kind="postgis",
)
def postgis_ufs(
    context: AssetExecutionContext,
    ibge_ufs: gpd.GeoDataFrame,
) -> Output[None]:
    engine = get_db_engine()

    ibge_ufs.to_postgis(
        "ufs_staging",
        engine,
        schema="geo",
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("MULTIPOLYGON", srid=4674)},
    )

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO geo.ufs (cod_uf, nome, sigla, regiao, geom, geom_simplified, area_km2)
            SELECT
                s.cod_uf::SMALLINT,
                s.nome,
                s.sigla,
                s.regiao,
                ST_Multi(ST_MakeValid(s.geometry))::geometry(MultiPolygon, 4674),
                CASE
                    WHEN s.geom_simplified IS NOT NULL
                    THEN ST_Multi(ST_MakeValid(s.geom_simplified))::geometry(MultiPolygon, 4674)
                    ELSE NULL
                END,
                s.area_km2
            FROM geo.ufs_staging s
            WHERE s.cod_uf IS NOT NULL
            ON CONFLICT (cod_uf) DO UPDATE SET
                nome           = EXCLUDED.nome,
                sigla          = EXCLUDED.sigla,
                regiao         = EXCLUDED.regiao,
                geom           = EXCLUDED.geom,
                geom_simplified = EXCLUDED.geom_simplified,
                area_km2       = EXCLUDED.area_km2,
                updated_at     = now()
        """))
        row_count = conn.execute(text("SELECT COUNT(*) FROM geo.ufs")).scalar()
        conn.execute(text("DROP TABLE IF EXISTS geo.ufs_staging"))

    context.log.info(f"UFs no PostGIS: {row_count}")
    return Output(None, metadata={"rows": MetadataValue.int(row_count)})


@asset(
    group_name="ibge_malhas",
    description="Carga dos municípios no PostGIS (schema geo)",
    compute_kind="postgis",
    deps=["postgis_ufs"],
)
def postgis_municipios(
    context: AssetExecutionContext,
    ibge_municipios: gpd.GeoDataFrame,
) -> Output[None]:
    engine = get_db_engine()

    # Carrega em staging primeiro, depois faz upsert
    ibge_municipios.to_postgis(
        "municipios_staging",
        engine,
        schema="geo",
        if_exists="replace",
        index=False,
        dtype={"geometry": Geometry("MULTIPOLYGON", srid=4674)},
    )

    with engine.begin() as conn:
        # Upsert na tabela principal
        conn.execute(text("""
            INSERT INTO geo.municipios (cod_ibge_7, cod_uf, nome, geom, geom_simplified, area_km2)
            SELECT
                s.cod_ibge_7,
                s.cod_uf,
                s.nome,
                ST_Multi(ST_MakeValid(s.geometry))::geometry(MultiPolygon, 4674),
                ST_Multi(ST_MakeValid(s.geom_simplified))::geometry(MultiPolygon, 4674),
                s.area_km2
            FROM geo.municipios_staging s
            ON CONFLICT (cod_ibge_7) DO UPDATE SET
                nome           = EXCLUDED.nome,
                geom           = EXCLUDED.geom,
                geom_simplified = EXCLUDED.geom_simplified,
                area_km2       = EXCLUDED.area_km2,
                updated_at     = now()
        """))

        row_count = conn.execute(
            text("SELECT COUNT(*) FROM geo.municipios")
        ).scalar()

        # Remove staging
        conn.execute(text("DROP TABLE IF EXISTS geo.municipios_staging"))

    context.log.info(f"Municípios no PostGIS: {row_count}")
    return Output(
        None,
        metadata={"rows_in_postgis": MetadataValue.int(row_count)},
    )


@asset(
    group_name="ibge_malhas",
    description=(
        "Gera tabela geo.setores_subdivididos via ST_Subdivide(max_vertices=255). "
        "Essencial para bounding box queries eficientes nos setores censitários."
    ),
    compute_kind="postgis",
    deps=["postgis_municipios"],
)
def postgis_setores_subdivididos(context: AssetExecutionContext) -> Output[None]:
    engine = get_db_engine()

    with engine.begin() as conn:
        # Trunca e regenera a tabela subdividida
        conn.execute(text("TRUNCATE geo.setores_subdivididos"))

        result = conn.execute(text("""
            INSERT INTO geo.setores_subdivididos
                (cod_setor, cod_municipio, cod_uf, geom)
            SELECT
                sc.cod_setor,
                sc.cod_municipio,
                sc.cod_uf,
                -- ST_Subdivide: quebra polígonos grandes em pedaços de max 255 vértices
                -- Municípios amazônicos (ex: Altamira-PA com ~180k vértices) passam
                -- de uma geometria catastrófica para centenas de polígonos simples
                (ST_Dump(ST_Subdivide(sc.geom, 255))).geom
            FROM geo.setores_censitarios sc
            WHERE ST_IsValid(sc.geom) AND NOT ST_IsEmpty(sc.geom)
        """))
        rows = conn.execute(
            text("SELECT COUNT(*) FROM geo.setores_subdivididos")
        ).scalar()

        # Análise de estatísticas para o query planner
        conn.execute(text("ANALYZE geo.setores_subdivididos"))

    context.log.info(f"Geometrias subdivididas geradas: {rows}")
    return Output(
        None,
        metadata={"rows_subdivididos": MetadataValue.int(rows)},
    )
